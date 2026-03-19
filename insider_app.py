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

# --- 2. MAIL-MOTOR (iCloud) ---
def send_verification_email(receiver_email, code):
    try:
        sender = st.secrets["EMAIL_USER"]
        password = st.secrets["EMAIL_PASS"]
        msg = MIMEText(f"Din verifieringskod: {code}")
        msg['Subject'] = '🔑 Verifiera Vakthunden'; msg['From'] = sender; msg['To'] = receiver_email
        server = smtplib.SMTP('smtp.mail.me.com', 587)
        server.starttls(); server.login(sender, password)
        server.sendmail(sender, receiver_email, msg.as_string()); server.quit()
        return True
    except Exception as e:
        st.error(f"Mail-fel: {e}")
        return False

# --- 3. ANALYS-MOTOR ---
@st.cache_data(ttl=600)
def hämta_insider_data(dagar):
    try:
        start_date = (dt.now() - td(days=dagar)).strftime('%Y-%m-%d')
        url = f"https://marknadssok.fi.se/Publiceringsklient/sv-SE/Search/Search?SearchFunctionType=Insyn&button=export&Format=CSV&From={start_date}"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
        df = pd.read_csv(io.StringIO(r.content.decode('utf-16le')), sep=';')
        df.columns = df.columns.str.strip()
        def clean_val(v): return float(re.sub(r'[^\d,]', '', str(v)).replace(',', '.')) if pd.notna(v) else 0
        df['Kurs'] = df['Pris'].apply(clean_val)
        df['Värde'] = (df['Volym'].apply(clean_val) * df['Kurs']).apply(lambda x: f"{x:,.0f} kr".replace(',', ' '))
        return df.sort_values('Publiceringsdatum', ascending=False)
    except: return pd.DataFrame()

# --- 4. APP SETUP ---
st.set_page_config(page_title="Vakthunden ULTRA", layout="wide")
init_db()

if 'auth' not in st.session_state:
    st.session_state.auth = {'in': False, 'user': None, 'role': 'user', 'prem': False, 'ver': False}

# --- 5. SIDOPANEL (HÄR ÄR FIXEN!) ---
with st.sidebar:
    st.title("🐺 VAKTHUNDEN")
    
    if not st.session_state.auth['in']:
        # TYDLIG MENY FÖR REGISTRERING
        menu = st.radio("VÄLJ HANDLING:", ["Logga in", "Skapa konto"], index=1) 
        st.divider()
        
        u = st.text_input("Användarnamn")
        if menu == "Skapa konto":
            em = st.text_input("Din E-post")
            p1 = st.text_input("Välj Lösenord", type="password")
            p2 = st.text_input("Bekräfta Lösenord", type="password")
            if st.button("Skapa Mitt Konto"):
                if p1 == p2 and "@" in em and u:
                    conn = sqlite3.connect('vakthunden.db'); c = conn.cursor()
                    code = str(random.randint(100000, 999999))
                    c.execute('SELECT COUNT(*) FROM users'); role = 'admin' if c.fetchone()[0] == 0 else 'user'
                    try:
                        c.execute('INSERT INTO users(username, email, password, role, verification_code) VALUES (?,?,?,?,?)', (u, em, make_hashes(p1), role, code))
                        conn.commit(); conn.close()
                        if send_verification_email(em, code):
                            st.success("Konto skapat! Kolla din mail.")
                            st.info("Logga in nu.")
                    except: st.error("Namnet är upptaget.")
                else: st.error("Kolla lösenord och mail.")
        else:
            p = st.text_input("Lösenord", type="password")
            if st.button("Kör Inloggning"):
                conn = sqlite3.connect('vakthunden.db'); c = conn.cursor()
                c.execute('SELECT password, role, is_premium, is_verified FROM users WHERE username =?', (u,))
                data = c.fetchone(); conn.close()
                if data and check_hashes(p, data[0]):
                    st.session_state.auth = {'in': True, 'user': u, 'role': data[1], 'prem': bool(data[2]), 'ver': bool(data[3])}
                    st.rerun()
                else: st.error("Fel uppgifter.")
    else:
        st.success(f"Inloggad: {st.session_state.auth['user']}")
        if st.button("Logga ut"): st.session_state.auth['in'] = False; st.rerun()

# --- 6. HUVUDTERMINAL ---
if st.session_state.auth['in']:
    if not st.session_state.auth['ver']:
        st.warning("⚠️ VERIFIERA DIN E-POST")
        code_in = st.text_input("Skriv koden från mailet:")
        if st.button("Verifiera Nu"):
            conn = sqlite3.connect('vakthunden.db'); c = conn.cursor()
            c.execute('SELECT verification_code FROM users WHERE username = ?', (st.session_state.auth['user'],))
            res = c.fetchone()
            if res and res[0] == code_in:
                c.execute('UPDATE users SET is_verified = 1 WHERE username = ?', (st.session_state.auth['user'],))
                conn.commit(); conn.close()
                st.session_state.auth['ver'] = True; st.rerun()
            else: st.error("Fel kod.")
    else:
        st.markdown("<h1 style='text-align:center; color:#00ffcc;'>VAKTHUNDEN <span style='color:white'>TERMINAL</span></h1>", unsafe_allow_html=True)
        t = st.tabs(["🎯 SKANNER", "📊 ANALYS", "🛠️ ADMIN"])
        with t[1]:
            st.subheader("Insider Flow")
            df = hämta_insider_data(30)
            if not df.empty: st.dataframe(df[['Publiceringsdatum', 'Emittent', 'Person i ledande ställning', 'Kurs', 'Värde']].head(50), use_container_width=True)
else:
    st.info("Välkommen till Vakthunden ULTRA. Skapa ett konto eller logga in i sidomenyn för att starta.")
