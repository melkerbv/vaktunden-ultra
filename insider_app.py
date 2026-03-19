import streamlit as st
import pandas as pd
import requests, io, yfinance as yf, sqlite3, hashlib, re, random
import plotly.graph_objects as go
from datetime import datetime as dt, timedelta as td

# --- DESIGN & TEMA (DI INSPIRERAD) ---
st.set_page_config(page_title="Vakthunden Terminal", layout="wide")

# Nollställer standardtemat och injekterar stilren CSS (Svart på Vitt)
st.markdown("""
<style>
    /* Bakgrund och text */
    .stApp {
        background-color: #ffffff;
        color: #1a1a1a !important;
    }
    h1, h2, h3 {
        color: #1a1a1a !important;
        font-family: 'Playfair Display', serif; /* Stilren serif-font för rubriker */
        letter-spacing: -0.5px;
    }
    
    /* Sidomenyn (mörkgrå) */
    .css-163utf5, .css-78536 {
        background-color: #f7f7f7 !important;
        color: #1a1a1a !important;
    }

    /* Gör all text tydlig (inga bleka gråa färger) */
    .stTextInput>div>div>input, .stMarkdown, .stSubheader, .stDivider, .stRadio>label, .stSelectbox>label {
        color: #1a1a1a !important;
    }

    /* Fix för TABS-rubriker (Gör dem tydliga och stora) */
    button[data-baseweb="tab"] {
        color: #1a1a1a !important;
        font-size: 1.1em !important;
        font-weight: 600 !important;
        background-color: transparent !important;
        border: none !important;
    }
    button[data-baseweb="tab"]:focus {
        background-color: transparent !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #003366 !important; /* Subtil DI-blå färg för aktiv flik */
        border-bottom: 2px solid #003366 !important;
    }

    /* Stilrena knappar (Svarta) */
    .stButton>button {
        background-color: #1a1a1a !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 4px;
        transition: all 0.2s;
    }
    .stButton>button:hover {
        background-color: #333333 !important;
        color: #ffffff !important;
        transform: scale(1.02);
    }
    
    /* Tydligare datatabeller */
    .stDataFrame {
        border: 1px solid #e0e0e0;
    }

</style>
""", unsafe_allow_html=True)

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
                 is_verified INTEGER DEFAULT 1, verification_code TEXT)''')
    c.execute('CREATE TABLE IF NOT EXISTS user_tickers(username TEXT, ticker TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- 2. DATABAS-HJÄLPARE ---
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

# --- 3. ANALYS-MOTOR (FI-SCRAPER) ---
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

# --- 4. SESSION HANTERING ---
if 'auth' not in st.session
