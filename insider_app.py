import streamlit as st
import pandas as pd
import requests, io, yfinance as yf, sqlite3, hashlib, random
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS users(
            username TEXT PRIMARY KEY, 
            email TEXT, 
            password TEXT, 
            role TEXT DEFAULT 'user', 
            is_premium INTEGER DEFAULT 0, 
            is_verified INTEGER DEFAULT 1, 
            verification_code TEXT
        )
    """)
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
        
        # NY IDIOTSÄKER RENSNINGS-FUNKTION (Inga specialtecken)
        def cln(v): 
            if pd.isna(v): 
                return 0
            s = str(v)
            s_clean = "".join([c for c in s if c.isdigit() or c == ','])
            if not s_clean:
                return 0
            return float(s_clean.replace(',', '.'))
            
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
                        if c.fetchone()[0] == 0:
                            role = 'admin'
                        else:
                            role = 'user'
                            
                        c.execute(
                            "INSERT INTO users(username, email, password, role, verification_code) VALUES (?,?,?,?,?)", 
                            (u, em, make_hashes(p1), role, "BYPASSED")
                        )
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

# --- 4. HUVUDINNEHÅLL (INLOGGAD) ---
if st.session_state.auth['in']:
    st.title("VAKTHUNDEN ULTRA")
    
    tabs = st.tabs(["🏠 ÖVERSIKT", "🎯 MARKNADSSKANNER", "📊 INSIDER ANALYS", "🛠️ ADMIN PANEL"])

    # FLIK 0: ÖVERSIKT
    with tabs[0]:
        st.subheader(f"Välkommen till kommandocentralen, {st.session_state.auth['user']}. 🐺")
        st.write("Här har du en snabb överblick över din terminal och systemets status.")
        
        st.write("") 
        c1, c2, c3 = st.columns(3)
        c1.metric("Systemstatus", "ONLINE", "Optimerad")
        c2.metric("Aktiv Behörighet", st.session_state.auth['role'].upper(), "Verifierad")
        c3.metric("Databasanslutning", "AKTIV", "Lokal SQLite")
        
        st.write("---")
        st.markdown("### Tillgängliga Moduler")
        st.markdown("**🎯 MARKNADSSKANNER:** Kör vår RSI-algoritm på dina utvalda tillgångar för att snabbt identifiera överköpta eller översålda lägen. Lägg till egna Web3-projekt eller aktier.")
        st.markdown("**📊 INSIDER ANALYS:** Följ de stora pengarna. Verktyget skrapar kontinuerligt Finansinspektionen efter de senaste insidertransaktionerna på den svenska marknaden.")
        
        if st
