import streamlit as st
import pandas as pd
import requests, io, yfinance as yf, sqlite3, hashlib, re
import plotly.graph_objects as go
from datetime import datetime as dt, timedelta as td

st.set_page_config(page_title="Vakthunden ULTRA", layout="wide")

def make_hashes(p):
    return hashlib.sha256(str.encode(p)).hexdigest()

def check_hashes(p, h):
    return make_hashes(p) == h

def init_db():
    conn = sqlite3.connect('vakthunden.db')
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, email TEXT, password TEXT, role TEXT DEFAULT 'user', is_premium INTEGER DEFAULT 0, is_verified INTEGER DEFAULT 1, verification_code TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS user_tickers(username TEXT, ticker TEXT)")
    conn.commit()
    conn.close()

init_db()

def load_user_tickers(u):
    conn = sqlite3.connect('vakthunden.db')
    c = conn.cursor()
    c.execute("SELECT ticker FROM user_tickers WHERE username = ?", (u,))
    res = [row[0] for row in c.fetchall()]
    conn.close()
    return res

def save_user_tickers(u, tickers):
    conn = sqlite3.connect('vakthunden.db')
    c = conn.cursor()
    c.execute("DELETE FROM user_tickers WHERE username = ?", (u,))
    for t in tickers:
        c.execute("INSERT INTO user_tickers VALUES (?, ?)", (u, t))
    conn.commit()
    conn.close()

@st.cache_data(ttl=300)
def get_market_overview():
    tickers = {"OMXS30": "^OMX", "NASDAQ": "^IXIC", "S&P 500": "^GSPC", "Bitcoin": "BTC-USD"}
    res = {}
    for n, t in tickers.items():
        try:
            hist = yf.Ticker(t).history(period="5d")
            if len(hist) >= 2:
                curr = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                res[n] = {"val": curr, "pct": ((curr - prev) / prev) * 100}
            else:
                res[n] = None
        except:
            res[n] = None
    return res

@st.cache_data(ttl=900)
def get_news():
    try:
        return [n for n in yf.Ticker("SPY").news[:5] if 'title' in n and 'link' in n]
    except:
        return []

@st.cache_data(ttl=900)
def hämta_insider_data(dagar):
    try:
        start = (dt.now() - td(days=dagar)).strftime('%Y-%m-%d')
        url = f"https://marknadssok.fi.se/Publiceringsklient/sv-SE/Search/Search?SearchFunctionType=Insyn&button=export&Format=CSV&From={start}"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
        if r.status_code != 200:
            return pd.DataFrame()
        df = pd.read_csv(io.StringIO(r.content.decode('utf-16le')), sep=';')
        df.columns = df.columns.str.strip()
        def cln(v):
            if pd.isna(v): return 0
            s_clean = "".join([c for c in str(v) if c.isdigit() or c == ','])
            if not s_clean: return 0
            return float(s_clean.replace(',', '.'))
        df['Kurs_Num'] = df['Pris'].apply(cln)
        df['Volym_Num'] = df['Volym'].apply(cln)
        df['Kurs'] = df['Kurs_Num'].apply(lambda x: f"{x:,.2f} kr".replace(',', ' '))
        df['Värde'] = (df['Volym_Num'] * df['Kurs_Num']).apply(lambda x: f"{x:,.0f} kr".replace(',', ' '))
        return df.sort_values('Publiceringsdatum', ascending=False)
    except:
        return pd.DataFrame()

if 'auth' not in st.session_state:
    st.session_state.auth = {'in': False, 'user': None, 'role': 'user', 'prem': False}

with st.sidebar:
    st.title("🐺 VAKTHUNDEN")
    if not st.session_state.auth['in']:
        action = st.radio("Välj:", ["Logga in", "Skapa konto"], index=0)
        u = st.text_input("Användarnamn").strip()
        if action == "Skapa konto":
            em = st.text_input("E-post").strip()
            p1 = st.text_input("Lösenord", type="password")
            if st.button("Skapa Konto", type="primary") and u and em and p1:
                conn = sqlite3.connect('vakthunden.db')
                c = conn.cursor()
                if c.execute("SELECT username FROM users WHERE username = ?", (u,)).fetchone():
                    st.error("Namnet är taget.")
                else:
                    role = 'admin' if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0 else 'user'
                    c.execute("INSERT INTO users(username, email, password, role) VALUES (?,?,?,?)", (u, em, make_hashes(p1), role))
                    conn.commit()
                    st.session_state.auth = {'in': True, 'user': u, 'role': role, 'prem': False}
                    st.rerun()
                conn.close()
        else:
            p = st.text_input("Lösenord", type="password")
            if st.button("Logga in", type="primary"):
                conn = sqlite3.connect('vakthunden.db')
                c = conn.cursor()
                data = c.execute("SELECT password, role, is_premium FROM users WHERE username =?", (u,)).fetchone()
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

if st.session_state.auth['in']:
    st.title("VAKTHUNDEN ULTRA")
    
    # Skapar flikarna dynamiskt. Admin-panelen existerar enbart om rollen är admin.
    is_admin = st.session_state.auth['role'] == 'admin'
    tab_names = ["🏠 ÖVERSIKT", "🎯 MARKNADSSKANNER", "📊 INSIDER ANALYS"]
    if is_admin:
        tab_names.append("🛠️ ADMIN PANEL")
        
    tabs = st.tabs(tab_names)

    with tabs[0]:
        st.subheader(f"Välkommen, {st.session_state.auth['user']}. 🐺")
        st.write("Din dagliga överblick över marknadsläget och de senaste rörelserna.")
        st.write("---")
        with st.spinner("Hämtar live-kurser..."):
            m_data = get_market_overview()
        c1, c2, c3, c4 = st.columns(4)
        
        # Uppstädad funktion som inte triggar Streamlits Magic
        def disp_metric(col, title, data, pre=""):
            if data:
                col.metric(title, f"{pre}{data['val']:,.2f}", f"{data['pct']:+.2f}%")
            else:
                col.metric(title, "N/A", "N/A")
                
        disp_metric(c1, "OMXS30", m_data.get("OMXS30"))
        disp_metric(c2, "NASDAQ", m_data.get("NASDAQ"))
        disp_metric(c3, "S&P 500", m_data.get("S&P 500"))
        disp_metric(c4, "Bitcoin", m_data.get("Bitcoin"), "$")
        
        st.write("---")
        st.markdown("### 📰 Senaste Marknadsnyheterna")
        with st.spinner("Laddar nyheter..."):
            news = get_news()
            if news: 
                for n in news:
                    st.markdown(f"🔹 **[{n['title']}]({n['link']})**")
            else:
                st.info("Inga nyheter just nu.")

    with tabs[1]:
        st.subheader("Algoritmisk Marknadsbevakning (RSI)")
        std = ["BTC-USD", "ETH-USD", "SOL-USD", "LINK-USD", "AVAX-USD", "ADA-USD", "MSTR", "COIN", "TSLA", "AAPL", "MSFT", "NVDA", "INVE-B.ST", "VOLV-B.ST"]
        saved = load_user_tickers(st.session_state.auth['user'])
        valda = st.multiselect("Välj tillgångar:", list(set(std + saved)), saved if saved else ["BTC-USD"])
        ny_t = st.text_input("Lägg till egen Ticker:").upper().strip()
        
        if st.button("Lägg till") and ny_t and ny_t not in valda:
            valda.append(ny_t)
            save_user_tickers(st.session_state.auth['user'], valda)
            st.rerun()
            
        c1, c2 = st.columns(2)
        if c1.button("Spara lista"):
            save_user_tickers(st.session_state.auth['user'], valda)
            st.toast("Sparat!")
            
        if c2.button("🚀 Kör full scan", type="primary"):
            res = []
            with st.spinner("Analyserar..."):
                for t in valda:
                    try:
                        d = yf.Ticker(t).history(period="1y")['Close']
                        if len(d) > 14:
                            delta = d.diff()
                            g = delta.where(delta > 0, 0).rolling(14).mean()
                            l = -delta.where(delta < 0, 0).rolling(14).mean()
                            rsi = 100 - (100 / (1 + (g / l))).iloc[-1]
                            res.append({"Ticker": t, "RSI": round(rsi, 1), "Signal": "KÖP" if rsi < 35 else ("SÄLJ" if rsi > 70 else "VÄNTA")})
                    except:
                        continue 
            if res:
                st.dataframe(pd.DataFrame(res).sort_values("RSI"), use_container_width=True, hide_index=True)
            else:
                st.warning("Rate limit blockad.")

    with tabs[2]:
        st.subheader("Svenskt Insider Flow")
        c_l, c_r = st.columns([2, 1])
        with c_l:
            df_i = hämta_insider_data(30)
            if not df_i.empty:
                st.dataframe(df_i[['Publiceringsdatum', 'Emittent', 'Person i ledande ställning', 'Kurs', 'Värde']].head(30), use_container_width=True, hide_index=True)
            else:
                st.info("Ingen data.")
        with c_r:
            s = st.text_input("Snabbsök Graf:", "INVE-B.ST")
            if s:
                try:
                    h = yf.Ticker(s).history(period="6mo")
                    if not h.empty:
                        fig = go.Figure(data=[go.Scatter(x=h.index, y=h['Close'])])
                        fig.update_layout(template="simple_white", height=350, margin=dict(l=0,r=0,t=0,b=0))
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Hittar ej data.")
                except:
                    st.warning("Rate Limit.")

    if is_admin:
        with tabs[3]:
            st.subheader("Admin Panel")
            conn = sqlite3.connect('vakthunden.db')
            st.dataframe(pd.read_sql_query("SELECT username, email, role, is_premium FROM users", conn), use_container_width=True, hide_index=True)
            t = st.text_input("Uppgradera användare:")
            if st.button("GE PREMIUM"):
                conn.execute("UPDATE users SET is_premium = 1 WHERE username = ?", (t,))
                conn.commit()
                st.success(f"{t} uppgraderad!")
                st.rerun()
            conn.close()

else:
    st.markdown("<h1 style='text-align: center; font-size: 4em;'>🐺 VAKTHUNDEN ULTRA</h1><p style='text-align: center; font-size: 1.5em; color: gray;'>Algoritmisk marknadsbevakning och insideranalys.</p><hr>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.subheader("🎯 Algoritmisk RSI")
    c1.write("Skanna marknaden i realtid efter överköpta och översålda lägen.")
    c2.subheader("📊 Insider Flow")
    c2.write("Följ smarta pengar direkt från Finansinspektionen.")
    c3.subheader("⚡ Web3-redo")
    c3.write("Förbered din portfölj för decentraliserad finansiering.")
    st.info("🔒 **SYSTEMET ÄR LÅST:** Skapa konto eller logga in i sidomenyn.")

# --- SLUT PÅ KODEN ---
