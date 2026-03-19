import streamlit as st
import pandas as pd
import requests, io, yfinance as yf, sqlite3, hashlib
import plotly.graph_objects as go
from datetime import datetime as dt, timedelta as td

st.set_page_config(page_title="Vakthunden ULTRA", layout="wide")

def make_hashes(p): return hashlib.sha256(str.encode(p)).hexdigest()
def check_hashes(p, h): return make_hashes(p) == h

def init_db():
    conn = sqlite3.connect('vakthunden.db')
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, email TEXT, password TEXT, role TEXT DEFAULT 'user', is_premium INTEGER DEFAULT 0)")
    # Ny tabell för portfölj-innehav
    c.execute("CREATE TABLE IF NOT EXISTS holdings(username TEXT, ticker TEXT, amount REAL, buy_price REAL)")
    conn.commit()
    conn.close()

init_db()

def get_holdings(u):
    conn = sqlite3.connect('vakthunden.db')
    df = pd.read_sql_query("SELECT ticker, amount, buy_price FROM holdings WHERE username = ?", conn, params=(u,))
    conn.close()
    return df

def add_holding(u, t, a, p):
    conn = sqlite3.connect('vakthunden.db')
    c = conn.cursor()
    c.execute("INSERT INTO holdings VALUES (?, ?, ?, ?)", (u, t.upper(), a, p))
    conn.commit()
    conn.close()

def delete_holding(u, t):
    conn = sqlite3.connect('vakthunden.db')
    c = conn.cursor()
    c.execute("DELETE FROM holdings WHERE username = ? AND ticker = ?", (u, t))
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
                curr, prev = hist['Close'].iloc[-1], hist['Close'].iloc[-2]
                res[n] = {"val": curr, "pct": ((curr - prev) / prev) * 100}
        except: res[n] = None
    return res

if 'auth' not in st.session_state:
    st.session_state.auth = {'in': False, 'user': None, 'role': 'user'}

with st.sidebar:
    st.title("🐺 VAKTHUNDEN")
    if not st.session_state.auth['in']:
        action = st.radio("Välj:", ["Logga in", "Skapa konto"])
        u = st.text_input("Användarnamn").strip()
        if action == "Skapa konto":
            em = st.text_input("E-post")
            p1 = st.text_input("Lösenord", type="password")
            if st.button("Skapa Konto", type="primary") and u and p1:
                conn = sqlite3.connect('vakthunden.db'); c = conn.cursor()
                if c.execute("SELECT username FROM users WHERE username = ?", (u,)).fetchone(): st.error("Taget.")
                else:
                    role = 'admin' if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0 else 'user'
                    c.execute("INSERT INTO users(username, email, password, role) VALUES (?,?,?,?)", (u, em, make_hashes(p1), role))
                    conn.commit(); st.session_state.auth = {'in': True, 'user': u, 'role': role}; st.rerun()
                conn.close()
        else:
            p = st.text_input("Lösenord", type="password")
            if st.button("Logga in", type="primary"):
                conn = sqlite3.connect('vakthunden.db'); c = conn.cursor()
                d = c.execute("SELECT password, role FROM users WHERE username =?", (u,)).fetchone(); conn.close()
                if d and check_hashes(p, d[0]): st.session_state.auth = {'in': True, 'user': u, 'role': d[1]}; st.rerun()
                else: st.error("Fel lösenord.")
    else:
        st.success(f"Inloggad: {st.session_state.auth['user']}")
        if st.button("Logga ut"): st.session_state.auth = {'in': False}; st.rerun()

if st.session_state.auth.get('in'):
    st.title("VAKTHUNDEN ULTRA")
    tabs_list = ["🏠 ÖVERSIKT", "💰 MIN PORTFÖLJ", "🎯 SKANNER", "📊 INSIDER"]
    if st.session_state.auth['role'] == 'admin': tabs_list.append("🛠️ ADMIN")
    tabs = st.tabs(tabs_list)

    with tabs[0]:
        st.subheader("Marknadsläget")
        m_data = get_market_overview()
        cols = st.columns(4)
        for i, (name, d) in enumerate(m_data.items()):
            if d: cols[i].metric(name, f"{d['val']:,.2f}", f"{d['pct']:+.2f}%")

    with tabs[1]:
        st.subheader("Ditt Innehav")
        with st.expander("➕ Lägg till nytt innehav"):
            c1, c2, c3 = st.columns(3)
            new_t = c1.text_input("Ticker (t.ex. AAPL eller BTC-USD)").upper()
            new_a = c2.number_input("Antal", min_value=0.0, step=0.1)
            new_p = c3.number_input("Inköpspris (per st)", min_value=0.0)
            if st.button("Spara till portfölj"):
                add_holding(st.session_state.auth['user'], new_t, new_a, new_p)
                st.success(f"Lagt till {new_t}"); st.rerun()

        df_h = get_holdings(st.session_state.auth['user'])
        if not df_h.empty:
            results = []
            total_value = 0
            for _, row in df_h.iterrows():
                try:
                    curr_p = yf.Ticker(row['ticker']).fast_info['lastPrice']
                    val = curr_p * row['amount']
                    cost = row['buy_price'] * row['amount']
                    pnl = val - cost
                    pnl_pct = (pnl / cost * 100) if cost > 0 else 0
                    results.append({
                        "Ticker": row['ticker'], "Antal": row['amount'], 
                        "Inköp": f"{row['buy_price']:.2f}", "Live": f"{curr_p:.2f}",
                        "Värde": f"{val:,.0f}", "Vinst/Förlust": f"{pnl:,.0f}", "Utv %": f"{pnl_pct:+.2f}%"
                    })
                    total_value += val
                except: continue
            
            st.metric("Totalt Portföljvärde", f"{total_value:,.0f} SEK/USD")
            st.table(pd.DataFrame(results))
            
            del_t = st.selectbox("Ta bort innehav:", df_h['ticker'].tolist())
            if st.button("Ta bort markerad"):
                delete_holding(st.session_state.auth['user'], del_t)
                st.rerun()
        else:
            st.info("Portföljen är tom. Lägg till din första tillgång ovan!")

    with tabs[2]:
        st.write("Marknadsskanner (RSI) är redo.")
        if st.button("Kör analys"): st.write("Analyserar tickers...")

    with tabs[3]:
        st.write("Insiderdata laddas från FI...")
        
    if st.session_state.auth['role'] == 'admin':
        with tabs[-1]:
            st.write("Adminverktyg")

else:
    st.markdown("<h1 style='text-align: center;'>🐺 VAKTHUNDEN</h1><p style='text-align: center;'>Logga in för att se din portfölj.</p>", unsafe_allow_html=True)
