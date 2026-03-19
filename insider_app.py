import streamlit as st
import pandas as pd
import yfinance as yf
import sqlite3
import hashlib
import plotly.graph_objects as go
from datetime import datetime as dt, timedelta as td

st.set_page_config(page_title="Vakthunden ULTRA", layout="wide")

# --- DATABASE & SECURITY ---
def make_hashes(p): return hashlib.sha256(str.encode(p)).hexdigest()
def check_hashes(p, h): return make_hashes(p) == h

def init_db():
    conn = sqlite3.connect('vakthunden.db'); c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, password TEXT, role TEXT DEFAULT 'user')")
    c.execute("CREATE TABLE IF NOT EXISTS holdings(username TEXT, ticker TEXT, amount REAL, buy_price REAL, currency TEXT)")
    try: c.execute("ALTER TABLE holdings ADD COLUMN currency TEXT DEFAULT 'SEK'")
    except: pass
    conn.commit(); conn.close()

init_db()

# --- HELPERS ---
def get_holdings(u):
    conn = sqlite3.connect('vakthunden.db')
    df = pd.read_sql_query("SELECT ticker, amount, buy_price, currency FROM holdings WHERE username = ?", conn, params=(u,))
    conn.close(); return df

def add_holding(u, t, a, p, cur):
    conn = sqlite3.connect('vakthunden.db'); c = conn.cursor()
    c.execute("INSERT INTO holdings (username, ticker, amount, buy_price, currency) VALUES (?, ?, ?, ?, ?)", (u, t.upper().strip(), a, p, cur))
    conn.commit(); conn.close()

def delete_holding(u, t):
    conn = sqlite3.connect('vakthunden.db'); c = conn.cursor()
    c.execute("DELETE FROM holdings WHERE username = ? AND ticker = ?", (u, t))
    conn.commit(); conn.close()

@st.cache_data(ttl=300)
def get_market_data():
    indices = {"OMXS30": "^OMX", "S&P 500": "^GSPC", "NASDAQ": "^IXIC", "Bitcoin": "BTC-USD"}
    res = {}
    for name, ticker in indices.items():
        try:
            h = yf.Ticker(ticker).history(period="2d")
            if len(h) > 1:
                curr, prev = h['Close'].iloc[-1], h['Close'].iloc[-2]
                res[name] = {"val": curr, "pct": ((curr - prev) / prev) * 100}
        except: res[name] = None
    return res

# --- SESSION ---
if 'auth' not in st.session_state: st.session_state.auth = {'in': False, 'user': None, 'role': 'user'}

with st.sidebar:
    st.title("🐺 VAKTHUNDEN")
    if not st.session_state.auth['in']:
        choice = st.radio("Meny", ["Logga in", "Skapa konto"])
        u = st.text_input("Användarnamn")
        p = st.text_input("Lösenord", type="password")
        if st.button("Kör"):
            conn = sqlite3.connect('vakthunden.db'); c = conn.cursor()
            if choice == "Skapa konto":
                role = 'admin' if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0 else 'user'
                c.execute("INSERT INTO users(username, password, role) VALUES (?,?,?)", (u, make_hashes(p), role))
                conn.commit(); st.session_state.auth = {'in': True, 'user': u, 'role': role}; st.rerun()
            else:
                d = c.execute("SELECT password, role FROM users WHERE username = ?", (u,)).fetchone()
                if d and check_hashes(p, d[0]): st.session_state.auth = {'in': True, 'user': u, 'role': d[1]}; st.rerun()
                else: st.error("Fel inloggning")
            conn.close()
    else:
        st.success(f"Inloggad: {st.session_state.auth['user']}")
        if st.button("Logga ut"): st.session_state.auth = {'in': False}; st.rerun()

# --- MAIN ---
if st.session_state.auth['in']:
    t1, t2, t3 = st.tabs(["🏠 ÖVERSIKT", "💰 PORTFÖLJ", "🎯 SCANNER"])

    with t1:
        st.subheader("Marknadsläget")
        m_data = get_market_data()
        cols = st.columns(4)
        for i, (name, d) in enumerate(m_data.items()):
            if d: cols[i].metric(name, f"{d['val']:,.2f}", f"{d['pct']:+.2f}%")
        st.divider()
        st.subheader("Finansnyheter")
        try:
            for n in yf.Ticker("SPY").news[:5]: st.markdown(f"🔹 **[{n['title']}]({n['link']})**")
        except: st.write("Nyheter tillfälligt otillgängliga.")

    with t2:
        st.header("Din Portfölj")
        with st.expander("➕ Lägg till innehav"):
            c1, c2, c3, c4 = st.columns(4)
            tick = c1.text_input("Ticker (t.ex. INVE-B.ST eller BTC-USD)")
            amnt = c2.number_input("Antal", min_value=0.0)
            b_pr = c3.number_input("Inköpspris", min_value=0.0)
            curr = c4.selectbox("Valuta", ["SEK", "USD"])
            if st.button("Spara"):
                add_holding(st.session_state.auth['user'], tick, amnt, b_pr, curr)
                st.rerun()

        df = get_holdings(st.session_state.auth['user'])
        if not df.empty:
            s_tot, u_tot = 0, 0
            for _, row in df.iterrows():
                try:
                    price = yf.Ticker(row['ticker']).fast_info['lastPrice']
                    if ".ST" in row['ticker'] and price > 1000: price /= 100
                    val = price * row['amount']
                    pnl = val - (row['buy_price'] * row['amount'])
                    pnl_p = (pnl/(row['buy_price']*row['amount'])*100) if row['buy_price']>0 else 0
                    c1, c2, c3, c4 = st.columns([1,1,1,1])
                    c1.write(f"**{row['ticker']}**")
                    c2.metric("Pris", f"{price:.2f}")
                    c3.metric("Värde", f"{val:,.0f} {row['currency']}")
                    c4.metric("PNL", f"{pnl:,.0f}", f"{pnl_p:+.2f}%")
                    if row['currency'] == "SEK": s_tot += val
                    else: u_tot += val
                except: st.error(f"Kunde inte hämta data för {row['ticker']}. Använd t.ex. INVE-B.ST")
            st.divider()
            st.info(f"Sammanlagt: {s_tot:,.0f} SEK | {u_tot:,.0f} USD")
            target = st.selectbox("Radera innehav:", df['ticker'].tolist())
            if st.button("Radera"): delete_holding(st.session_state.auth['user'], target); st.rerun()
        else: st.info("Portföljen är tom.")

    with t3:
        st.subheader("RSI Scanner")
        watch = st.text_area("Tickers (komma-separerade):", "AAPL,TSLA,BTC-USD,INVE-B.ST,VOLV-B.ST")
        if st.button("Skanna nu"):
            res = []
            for t in [x.strip().upper() for x in watch.split(",")]:
                try:
                    d = yf.Ticker(t).history(period="1y")['Close']
                    if len(d) > 14:
                        delta = d.diff(); up = delta.clip(lower=0).rolling(14).mean(); down = -delta.clip(upper=0).rolling(14).mean()
                        rsi = 100 - (100 / (1 + (up/down))).iloc[-1]
                        res.append({"Ticker": t, "RSI": round(rsi, 2), "Status": "KÖP" if rsi < 30 else ("SÄLJ" if rsi > 70 else "NEUTRAL")})
                except: continue
            st.table(pd.DataFrame(res)) if res else st.warning("Ingen data hittades.")

else:
    st.title("VAKTHUNDEN ULTRA")
    st.write("Logga in i sidomenyn för att använda terminalen.")
