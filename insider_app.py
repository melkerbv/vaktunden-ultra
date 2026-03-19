import streamlit as st
import pandas as pd
import requests, io, yfinance as yf, sqlite3, hashlib, re, random, smtplib
import plotly.graph_objects as go
from email.mime.text import MIMEText
from datetime import datetime as dt, timedelta as td

# --- 1. SÄKERHET & DATABAS ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

def init_db():
    conn = sqlite3.connect('vakthunden.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users(
                 username TEXT PRIMARY KEY, email TEXT, password TEXT, 
                 role TEXT DEFAULT 'user', is_premium INTEGER DEFAULT 0,
                 is_verified INTEGER DEFAULT 0, verification_code TEXT)''')
    c.execute('CREATE TABLE IF NOT EXISTS user_tickers(username TEXT, ticker TEXT)')
    conn.commit()
    conn.close()

# --- 2. ANALYS-MOTOR (FI-Scraper) ---
@st.cache_data(ttl=900)
def hämta_insider_data(dagar):
    try:
        start_date = (dt.now() - td(days=dagar)).strftime('%Y-%m-%d')
        url = f"https://marknadssok.fi.se/Publiceringsklient/sv-SE/Search/Search?SearchFunctionType=Insyn&button=export&Format=CSV&From={start_date}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=45) # Rejäl timeout
        if r.status_code != 200: return f"FI:s server svarar inte (Status {r.status_code})"
        df = pd.read_csv(io.StringIO(r.content.decode('utf-16le')), sep=';')
        df.columns = df.columns.str.strip()
        def clean_val(val):
            if pd.isna(val): return 0
            res = re.sub(r'[^\d,]', '', str(val)).replace(',', '.')
            return float(res) if res else 0
        df['Volym_Num'] = df['Volym'].apply(clean_val)
        df['Pris_Num'] = df['Pris'].apply(clean_val)
        df['Summa SEK'] = df['Volym_Num'] * df['Pris_Num']
        df['Kurs'] = df['Pris_Num'].apply(lambda x: f"{x:,.2f} kr".replace(',', ' '))
        df['Värde'] = df['Summa SEK'].apply(lambda x: f"{x:,.0f} kr".replace(',', ' '))
        return df.sort_values('Publiceringsdatum', ascending=False)
    except Exception as e:
        return f"Systemfel: {str(e)}"

# --- 3. DATABAS-FUNKTIONER FÖR TICKERS ---
def load_user_tickers(username):
    conn = sqlite3.connect('vakthunden.db'); c = conn.cursor()
    c.execute("SELECT ticker FROM user_tickers WHERE username = ?", (username,))
    res = [row[0] for row in c.fetchall()]; conn.close()
    return res

def save_user_tickers(username, tickers):
    conn = sqlite3.connect('vakthunden.db'); c = conn.cursor()
    c.execute("DELETE FROM user_tickers WHERE username = ?", (username,))
    for t in tickers: c.execute("INSERT INTO user_tickers VALUES (?, ?)", (username, t))
    conn.commit(); conn.close()

# --- 4. APP SETUP & AUTH ---
st.set_page_config(page_title="Vakthunden ULTRA", layout="wide")
init_db()

if 'auth' not in st.session_state:
    st.session_state.auth = {'in': False, 'user': None, 'role': 'user', 'prem': False, 'ver': False}

with st.sidebar:
    st.title("🐺 VAKTHUNDEN")
    if not st.session_state.auth['in']:
        u = st.text_input("Användarnamn")
        p = st.text_input("Lösenord", type="password")
        if st.button("Logga in"):
            conn = sqlite3.connect('vakthunden.db'); c = conn.cursor()
            c.execute('SELECT password, role, is_premium, is_verified FROM users WHERE username =?', (u,))
            data = c.fetchone(); conn.close()
            if data and check_hashes(p, data[0]):
                st.session_state.auth = {'in': True, 'user': u, 'role': data[1], 'prem': bool(data[2]), 'ver': bool(data[3])}
                st.rerun()
            else: st.error("Fel inloggning.")
    else:
        st.success(f"Inloggad: **{st.session_state.auth['user']}**")
        if st.button("Logga ut"): st.session_state.auth['in'] = False; st.rerun()

# --- 5. HUVUDLAYOUT ---
if st.session_state.auth['in']:
    st.markdown("<h1 style='text-align:center; color:#00ffcc;'>VAKTHUNDEN <span style='color:white'>ULTRA</span></h1>", unsafe_allow_html=True)
    tabs = st.tabs(["🎯 MARKNADSSKANNER", "📊 ANALYS", "🛠️ ADMIN PANEL"])

    # --- FLIK: MARKNADSSKANNER ---
    with tabs[0]:
        st.subheader("Algoritmisk Bevakning")
        
        # 1. Laddning av användarens egna tickers
        standard_val = ["BTC-USD", "ETH-USD", "TSLA", "AAPL", "INVE-B.ST", "VOLV-B.ST", "SEB-A.ST"]
        saved_list = load_user_tickers(st.session_state.auth['user'])
        
        # Om användaren inte har sparat något, visa standardlistan
        current_selection = saved_list if saved_list else standard_val
        
        valda_bolag = st.multiselect("Dina bevakade bolag:", options=standard_val + saved_list, default=current_selection)
        
        # Möjlighet att lägga till egna specifika tickers
        ny_ticker = st.text_input("Sök/Lägg till ny ticker (t.ex. NVDA eller AZN.ST):").upper()
        if st.button("➕ Lägg till i val") and ny_ticker:
            if ny_ticker not in valda_bolag:
                valda_bolag.append(ny_ticker)
                st.rerun()

        c1, c2 = st.columns(2)
        if c1.button("💾 SPARA MIN LISTA PERMANENT"):
            save_user_tickers(st.session_state.auth['user'], valda_bolag)
            st.toast("Din bevakningslista har sparats i databasen!", icon="✅")

        if c2.button("🚀 KÖR FULL SCAN"):
            if not valda_bolag:
                st.warning("Välj minst ett bolag först.")
            else:
                results = []
                progress = st.progress(0)
                for i, t in enumerate(valda_bolag):
                    try:
                        df = yf.Ticker(t).history(period="1y")['Close']
                        if not df.empty:
                            delta = df.diff()
                            gain = delta.where(delta > 0, 0).rolling(window=14).mean()
                            loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
                            rs = gain / loss
                            rsi = 100 - (100 / (1 + rs)).iloc[-1]
                            
                            if rsi < 35: sig = "🔥 STARK KÖP"
                            elif rsi > 70: sig = "🚨 SÄLJ"
                            else: sig = "😴 VÄNTA"
                            
                            results.append({"Ticker": t, "RSI": round(rsi, 1), "Signal": sig})
                    except: continue
                    progress.progress((i + 1) / len(valda_bolag))
                
                if results:
                    st.table(pd.DataFrame(results).sort_values("RSI"))
                else:
                    st.error("Kunde inte hämta data för valda tickers.")

    # --- FLIK: ANALYS ---
    with tabs[1]:
        st.subheader("Insider-analys & Marknadsdata")
        with st.spinner("Hämtar data från FI..."):
            insider_df = hämta_insider_data(30)
        
        col_l, col_r = st.columns([2, 1])
        with col_l:
            st.markdown("#### 📢 Senaste Insider-transaktionerna")
            if isinstance(insider_df, str): st.error(insider_df)
            elif insider_df.empty: st.info("Ingen data hittades.")
            else:
                visnings_cols = ['Publiceringsdatum', 'Emittent', 'Person i ledande ställning', 'Karaktär', 'Kurs', 'Värde']
                st.dataframe(insider_df[visnings_cols].head(50), use_container_width=True, hide_index=True)

        with col_r:
            st.markdown("#### 📈 Snabb-analys")
            t_search = st.text_input("Ticker-graf (t.ex. TSLA):", "INVE-B.ST")
            if t_search:
                try:
                    tk_data = yf.Ticker(t_search).history(period="6mo")
                    if not tk_data.empty:
                        fig = go.Figure(data=[go.Scatter(x=tk_data.index, y=tk_data['Close'], line=dict(color='#00ffcc'))])
                        fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0))
                        st.plotly_chart(fig, use_container_width=True)
                        st.metric("Senaste pris", f"{tk_data['Close'].iloc[-1]:.2f} kr")
                except: st.error("Fel vid grafladdning.")

    # --- FLIK: ADMIN ---
    with tabs[2]:
        if st.session_state.auth['role'] == 'admin':
            st.subheader("Systemhantering")
            conn = sqlite3.connect('vakthunden.db')
            st.dataframe(pd.read_sql_query("SELECT username, email, is_premium FROM users", conn), use_container_width=True)
            conn.close()
        else: st.warning("Endast administratörer.")
else:
    st.info("Välkommen! Logga in för att öppna terminalen.")