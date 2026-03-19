import streamlit as st
import pandas as pd
import requests, io, yfinance as yf, sqlite3, hashlib, re, random
import plotly.graph_objects as go
from datetime import datetime as dt, timedelta as td

# --- 1. SÄKERHET & DATABAS ---
st.set_page_config(page_title="Vakthunden ULTRA", layout="wide")

def make_hashes(password): 
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text): 
    return make_hashes(password) == hashed_text

def init_db():
    conn = sqlite3.connect('vakthunden.db')
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, email TEXT, password TEXT, role TEXT DEFAULT 'user', is_premium INTEGER DEFAULT 0, is_verified INTEGER DEFAULT 1, verification_code TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS user_tickers(username TEXT, ticker TEXT)")
    conn.commit()
    conn.close()

init_db()

def load_user_tickers(username):
    conn = sqlite3.connect('vakthunden.db')
    c = conn.cursor()
    c.execute("SELECT ticker FROM user_tickers WHERE username = ?", (username,))
    res = [row[0] for row in c.fetchall()]
    conn.close()
    return res

def save_user_tickers(username, tickers):
    conn = sqlite3.connect('vakthunden.db')
    c = conn.cursor()
    c.execute("DELETE FROM user_tickers WHERE username = ?", (username,))
    for t in tickers: 
        c.execute("INSERT INTO user_tickers VALUES (?, ?)", (username, t))
    conn.commit()
    conn.close()

@st.cache_data(ttl=900)
def hämta_insider_data(dagar):
    try:
        start = (dt.now() - td(days=dagar)).strftime('%Y-%m-%d')
        url = f"https://marknadssok.fi.se/Publiceringsklient/sv-SE/Search/Search?SearchFunctionType=Insyn&button=export&Format=CSV&From={start}"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
        if r.status_code != 200: return pd.DataFrame()
        
        df = pd.read_csv(io.StringIO(r.content.decode('utf-16le')), sep=';')
        df.columns = df.columns.str.strip()
        
        def cln(v): return float(re.sub(r'[^\d,]', '', str(v)).replace(',', '.')) if pd.notna(v) else 0
        df['Kurs_Num'] = df['Pris'].apply(cln)
        df['Volym_Num'] = df['Volym'].apply(cln)
        df['Kurs'] = df['Kurs_Num'].apply(lambda x: f"{x:,.2f} kr".replace(',', ' '))
        df['Värde'] = (df['Volym_Num'] * df['Kurs_Num']).apply(lambda x: f"{x:,.0f} kr".replace(',', ' '))
        
        return df.sort_values('Publiceringsdatum', ascending=False)
    except: 
        return pd.DataFrame()

# --- 2. SESSION HANTERING ---
if 'auth' not in st.session_state:
    st.session_state.auth = {'in': False, 'user': None, 'role': 'user', 'prem': False}

# --- 3. SIDOPANEL ---
with st.sidebar:
    st.title("🐺 VAKTHUNDEN")
    if not st.session_state.auth['in']:
        action = st.radio("Välj alternativ:", ["Logga in", "Skapa konto"], index=0)
        st.divider()
        u = st.text_input("Användarnamn").strip()
        
        if action == "Skapa konto":
            em = st.text_input("E-post").strip()
            p1 = st.text_input("Lösenord", type="password")
            if st.button("Skapa Mitt Konto", type="primary"):
                if u and em and p1:
                    conn = sqlite3.connect('vakthunden.db')
                    c = conn.cursor()
                    c.execute("SELECT username FROM users WHERE username = ?", (u,))
                    if c.fetchone():
                        st.error("Namnet är taget. Välj ett annat eller logga in.")
                    else:
                        c.execute("SELECT COUNT(*) FROM users")
                        role = 'admin' if c.fetchone()[0] == 0 else 'user'
                        c.execute("INSERT INTO users(username, email, password, role, verification_code) VALUES (?,?,?,?,?)", (u, em, make_hashes(p1), role, "BYPASSED"))
                        conn.commit()
                        conn.close()
                        st.session_state.auth = {'in': True, 'user': u, 'role': role, 'prem': False}
                        st.rerun()
                else: 
                    st.warning("Fyll i alla fält.")
        else:
            p = st.text_input("Lösenord", type="password")
            if st.button("Logga in", type="primary"):
                conn = sqlite3.connect('vakthunden.db')
                c = conn.cursor()
                c.execute("SELECT password, role, is_premium FROM users WHERE username =?", (u,))
                data = c.fetchone()
                conn.close()
                if data and check_hashes(p, data[0]):
                    st.session_state.auth = {'in': True, 'user': u, 'role': data[1], 'prem': bool(data[2])}
                    st.rerun()
                else: 
                    st.error("Fel inloggning.")
    else:
        st.success(f"Inloggad: {st.session_state.auth['user']}")
        if st.button("Logga ut"):
            st.session_state.auth = {'in': False, 'user': None, 'role': 'user', 'prem': False}
            st.rerun()

# --- 4. HUVUDINNEHÅLL ---
if st.session_state.auth['in']:
    st.title("VAKTHUNDEN ULTRA")
    tabs = st.tabs(["MARKNADSSKANNER", "INSIDER ANALYS", "ADMIN PANEL"])

    # FLIK 1: SKANNER
    with tabs[0]:
        st.subheader("Algoritmisk Marknadsbevakning (RSI)")
        standard = ["BTC-USD", "ETH-USD", "SOL-USD", "LINK-USD", "AVAX-USD", "ADA-USD", "MSTR", "COIN", "TSLA", "AAPL", "MSFT", "NVDA", "INVE-B.ST", "VOLV-B.ST", "SEB-A.ST"]
        saved = load_user_tickers(st.session_state.auth['user'])
        alla_alternativ = list(set(standard + saved))
        
        col_m, col_n = st.columns([2, 1])
        with col_m: 
            valda = st.multiselect("Välj tillgångar att bevaka:", options=alla_alternativ, default=saved if saved else ["BTC-USD", "ETH-USD"])
        with col_n:
            ny_t = st.text_input("Lägg till egen Ticker:").upper().strip()
            if st.button("Lägg till") and ny_t:
                if ny_t not in valda: 
                    valda.append(ny_t)
                    save_user_tickers(st.session_state.auth['user'], valda)
                    st.rerun()
                    
        c1, c2 = st.columns(2)
        if c1.button("Spara bevakningslista"): 
            save_user_tickers(st.session_state.auth['user'], valda)
            st.toast("Databas uppdaterad!")
            
        if c2.button("🚀 Kör full scan", type="primary"):
            res = []
            with st.spinner("Analyserar marknadsdata..."):
                for t in valda:
                    try:
                        d = yf.Ticker(t).history(period="1y")['Close']
                        if len(d) > 14:
                            delta = d.diff()
                            g = delta.where(delta > 0, 0).rolling(14).mean()
                            l = -delta.where(delta < 0, 0).rolling(14).mean()
                            rsi = 100 - (100 / (1 + (g / l))).iloc[-1]
                            res.append({"Ticker": t, "RSI": round(rsi, 1), "Signal": "KÖP" if rsi < 35 else ("SÄLJ" if rsi > 70 else "VÄNTA")})
                    except Exception: 
                        continue 
            if res: 
                st.dataframe(pd.DataFrame(res).sort_values("RSI"), use_container_width=True, hide_index=True)
            else: 
                st.warning("Kunde inte hämta data för dessa tillgångar. Yahoo Finance kan ha en tillfällig blockad.")

    # FLIK 2: ANALYS
    with tabs[1]:
        st.subheader("Svenskt Insider Flow")
        col_l, col_r = st.columns([2, 1])
        with col_l:
            df_i = hämta_insider_data(30)
            if not df_i.empty: 
                st.dataframe(df_i[['Publiceringsdatum', 'Emittent', 'Person i ledande ställning', 'Kurs', 'Värde']].head(30), use_container_width=True, hide_index=True)
            else: 
                st.info("Ingen data från Finansinspektionen just nu.")
        with col_r:
            search = st.text_input("Snabbsök Graf:", "INVE-B.ST")
            if search:
                try:
                    h = yf.Ticker(search).history(period="6mo")
                    if not h.empty:
                        fig = go.Figure(data=[go.Scatter(x=h.index, y=h['Close'])])
                        fig.update_layout(template="simple_white", height=350, margin=dict(l=0,r=0,t=0,b=0)) 
                        st.plotly_chart(fig, use_container_width=True)
                    else: 
                        st.warning("Kunde inte hitta prisdata för den tickern.")
                except Exception: 
                    st.warning("Yahoo Finance blockerar tillfälligt hämtning av grafer (Rate Limit).")

    # FLIK 3: ADMIN
    with tabs[2]:
        if st.session_state.auth['role'] == 'admin':
            st.subheader("Admin Control Panel")
            conn = sqlite3.connect('vakthunden.db')
            users = pd.read_sql_query("SELECT username, email, role, is_premium FROM users", conn)
            st.dataframe(users, use_container_width=True, hide_index=True)
            
            target = st.text_input("Användarnamn att uppgradera:")
            if st.button("GE PREMIUM-STATUS"):
                conn.execute("UPDATE users SET is_premium = 1 WHERE username = ?", (target,))
                conn.commit()
                st.success(f"{target} är nu Premium!")
                st.rerun()
            conn.close()
        else: 
            st.warning("Åtkomst nekad. Detta område kräver Admin-behörighet.")

else:
    st.markdown("""
    <div style='text-align: center; margin-top: 100px;'>
        <h1 style='font-size: 3.5em;'>VAKTHUNDEN</h1>
        <p style='font-size: 1.2em;'>Algoritmisk marknadsbevakning och insideranalys.</p>
        <div style='margin-top: 40px; padding: 20px; border: 1px solid #ddd; border-radius: 8px; display: inline-block; background-color: #f9f9f9;'>
            <p style='margin: 0;'><b>SYSTEM LÅST</b></p>
            <p style='font-size: 0.9em; margin-top: 5px;'>Ange autentiseringsuppgifter i sidomenyn för åtkomst till terminalen.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
