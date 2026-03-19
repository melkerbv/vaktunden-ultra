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
                if data and check_hashes(p, data[0]):
                    st.session_state.auth = {'in': True, 'user': u, 'role': data[1], 'prem': bool(data[2]), 'ver': bool(data[3])}
                    st.rerun()
                else: st.error("Fel inloggning.")
    else:
        st.success(f"Inloggad: {st.session_state.auth['user']}")
        if st.button("Logga ut"): st.session_state.auth['in'] = False; st.rerun()

# --- 6. HUVUDINNEHÅLL ---
if st.session_state.auth['in']:
    if not st.session_state.auth['ver']:
        st.warning("📩 Verifiera ditt konto")
        code_in = st.text_input("Skriv koden från mailet:")
        if st.button("Aktivera"):
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
        tabs = st.tabs(["🎯 SKANNER", "📊 ANALYS", "🛠️ ADMIN"])

        # --- FLIK 1: SKANNER ---
        with tabs[0]:
            st.subheader("RSI Algoritmisk Bevakning")
            standard = ["BTC-USD", "ETH-USD", "SOL-USD", "TSLA", "AAPL", "INVE-B.ST", "VOLV-B.ST"]
            saved = load_user_tickers(st.session_state.auth['user'])
            valda = st.multiselect("Dina bolag:", options=list(set(standard + saved)), default=saved if saved else ["BTC-USD"])
            
            c1, c2 = st.columns(2)
            if c1.button("💾 SPARA LISTA"):
                save_user_tickers(st.session_state.auth['user'], valda)
                st.toast("Sparat!")
            
            if c2.button("🚀 KÖR SCAN"):
                res = []
                for t in valda:
                    try:
                        d = yf.Ticker(t).history(period="1y")['Close']
                        delta = d.diff(); g = delta.where(delta > 0, 0).rolling(14).mean(); l = -delta.where(delta < 0, 0).rolling(14).mean()
                        rsi = 100 - (100 / (1 + (g / l))).iloc[-1]
                        res.append({"Ticker": t, "RSI": round(rsi, 1), "Signal": "🔥 KÖP" if rsi < 35 else ("🚨 SÄLJ" if rsi > 70 else "😴 VÄNTA")})
                    except: continue
                st.table(pd.DataFrame(res))

        # --- FLIK 2: ANALYS ---
        with tabs[1]:
            st.subheader("Insider Flow & Marknadsdata")
            col_l, col_r = st.columns([2, 1])
            with col_l:
                df_i = hämta_insider_data(30)
                if not df_i.empty:
                    st.dataframe(df_i[['Publiceringsdatum', 'Emittent', 'Person i ledande ställning', 'Kurs', 'Värde']].head(40), use_container_width=True, hide_index=True)
            with col_r:
                search = st.text_input("Ticker-graf:", "TSLA")
                if search:
                    h = yf.Ticker(search).history(period="6mo")
                    fig = go.Figure(data=[go.Scatter(x=h.index, y=h['Close'], line=dict(color='#00ffcc'))])
                    fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,t=0,b=0))
                    st.plotly_chart(fig, use_container_width=True)

        # --- FLIK 3: ADMIN ---
        with tabs[2]:
            if st.session_state.auth['role'] == 'admin':
                st.subheader("Användarhantering")
                conn = sqlite3.connect('vakthunden.db')
                users = pd.read_sql_query("SELECT username, email, role, is_premium FROM users", conn)
                st.dataframe(users, use_container_width=True)
                target = st.text_input("Uppgradera användare:")
                if st.button("GE PREMIUM"):
                    conn.execute("UPDATE users SET is_premium = 1 WHERE username = ?", (target,))
                    conn.commit(); st.success(f"{target} uppgraderad!"); st.rerun()
                conn.close()
            else: st.warning("Endast för Admin.")
else:
    st.info("🐺 Välkommen! Logga in eller skapa ett konto för att låsa upp terminalen.")
