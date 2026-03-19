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
    conn.commit(); conn.close()

# --- 2. HJÄLPFUNKTIONER (Mail & Tickers) ---
def send_verification_email(receiver_email, code):
    try:
        sender = st.secrets["EMAIL_USER"]
        password = st.secrets["EMAIL_PASS"]
        msg = MIMEText(f"Din unika verifieringskod för Vakthunden ULTRA: {code}")
        msg['Subject'] = '🔑 Verifiera ditt konto'; msg['From'] = sender; msg['To'] = receiver_email
        server = smtplib.SMTP('smtp.mail.me.com', 587)
        server.starttls(); server.login(sender, password)
        server.sendmail(sender, receiver_email, msg.as_string()); server.quit()
        return True
    except: return False

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

# --- 3. ANALYS-MOTOR (Insider-data) ---
@st.cache_data(ttl=900)
def hämta_insider_data(dagar):
    try:
        start_date = (dt.now() - td(days=dagar)).strftime('%Y-%m-%d')
        url = f"https://marknadssok.fi.se/Publiceringsklient/sv-SE/Search/Search?SearchFunctionType=Insyn&button=export&Format=CSV&From={start_date}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=40)
        if r.status_code != 200: return pd.DataFrame()
        df = pd.read_csv(io.StringIO(r.content.decode('utf-16le')), sep=';')
        df.columns = df.columns.str.strip()
        def clean_val(v): return float(re.sub(r'[^\d,]', '', str(v)).replace(',', '.')) if pd.notna(v) else 0
        df['Kurs_Num'] = df['Pris'].apply(clean_val)
        df['Volym_Num'] = df['Volym'].apply(clean_val)
        df['Kurs'] = df['Kurs_Num'].apply(lambda x: f"{x:,.2f} kr".replace(',', ' '))
        df['Värde'] = (df['Volym_Num'] * df['Kurs_Num']).apply(lambda x: f"{x:,.0f} kr".replace(',', ' '))
        return df.sort_values('Publiceringsdatum', ascending=False)
    except: return pd.DataFrame()

# --- 4. UI SETUP ---
st.set_page_config(page_title="Vakthunden ULTRA", layout="wide")
init_db()

if 'auth' not in st.session_state:
    st.session_state.auth = {'in': False, 'user': None, 'role': 'user', 'prem': False, 'ver': False}

# --- 5. SIDOPANEL ---
with st.sidebar:
    st.title("🐺 VAKTHUNDEN")
    if not st.session_state.auth['in']:
        menu = st.radio("MENY", ["Logga in", "Skapa konto"])
        u = st.text_input("Användarnamn")
        if menu == "Skapa konto":
            em = st.text_input("E-post")
            p1 = st.text_input("Lösenord", type="password")
            if st.button("Registrera"):
                conn = sqlite3.connect('vakthunden.db'); c = conn.cursor()
                code = str(random.randint(100000, 999999))
                c.execute('SELECT COUNT(*) FROM users'); role = 'admin' if c.fetchone()[0] == 0 else 'user'
                try:
                    c.execute('INSERT INTO users(username, email, password, role, verification_code) VALUES (?,?,?,?,?)', (u, em, make_hashes(p1), role, code))
                    conn.commit(); conn.close()
                    send_verification_email(em, code)
                    st.success("Konto skapat! Kolla din mail.")
                except: st.error("Namnet upptaget.")
        else:
            p = st.text_input("Lösenord", type="password")
            if st.button("Logga in"):
                conn = sqlite3.connect('vakthunden.db'); c = conn.cursor()
                c.execute('SELECT password, role, is_premium, is_verified FROM users WHERE username =?', (u,))
                data = c.fetchone(); conn.close()
