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
                        role = 'admin' if c.fetchone()[0] == 0 else
