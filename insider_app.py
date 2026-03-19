import streamlit as st
import pandas as pd
import yfinance as yf
import sqlite3
import hashlib

st.set_page_config(page_title="Vakthunden ULTRA", layout="wide")

# --- SÄKERHET ---
def make_hashes(p): return hashlib.sha256(str.encode(p)).hexdigest()
def check_hashes(p, h): return make_hashes(p) == h

def init_db():
    conn = sqlite3.connect('vakthunden.db')
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, email TEXT, password TEXT, role TEXT DEFAULT 'user')")
    c.execute("CREATE TABLE IF NOT EXISTS holdings(username TEXT, ticker TEXT, amount REAL, buy_price REAL)")
    
    # FIX: Tvinga tillägg av kolumnen 'currency' om den saknas i en gammal databas
    try:
        c.execute("ALTER TABLE holdings ADD COLUMN currency TEXT DEFAULT 'SEK'")
    except:
        pass # Kolumnen finns redan
        
    conn.commit()
    conn.close()

init_db()

# --- DATABASFUNKTIONER ---
def get_holdings(u):
    conn = sqlite3.connect('vakthunden.db')
    df = pd.read_sql_query("SELECT ticker, amount, buy_price, currency FROM holdings WHERE username = ?", conn, params=(u,))
    conn.close()
    return df

def add_holding(u, t, a, p, cur):
    conn = sqlite3.connect('vakthunden.db')
    c = conn.cursor()
    c.execute("INSERT INTO holdings (username, ticker, amount, buy_price, currency) VALUES (?, ?, ?, ?, ?)", (u, t.upper(), a, p, cur))
    conn.commit()
    conn.close()

def delete_holding(u, t):
    conn = sqlite3.connect('vakthunden.db')
    c = conn.cursor()
    c.execute("DELETE FROM holdings WHERE username = ? AND ticker = ?", (u, t))
    conn.commit()
    conn.close()

# --- SESSION ---
if 'auth' not in st.session_state:
    st.session_state.auth = {'in': False, 'user': None, 'role': 'user'}

# --- SIDEBAR ---
with st.sidebar:
    st.title("🐺 VAKTHUNDEN")
    if not st.session_state.auth['in']:
        action = st.radio("Meny", ["Logga in", "Skapa konto"])
        u = st.text_input("Användarnamn")
        p = st.text_input("Lösenord", type="password")
        if st.button("Kör"):
            conn = sqlite3.connect('vakthunden.db'); c = conn.cursor()
            if action == "Skapa konto":
                if u and p:
                    role = 'admin' if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0 else 'user'
                    c.execute("INSERT INTO users(username, password, role) VALUES (?,?,?)", (u, make_hashes(p), role))
                    conn.commit(); st.session_state.auth = {'in': True, 'user': u, 'role': role}; st.rerun()
            else:
                d = c.execute("SELECT password, role FROM users WHERE username =?", (u,)).fetchone()
                if d and check_hashes(p, d[0]): st.session_state.auth = {'in': True, 'user': u, 'role': d[1]}; st.rerun()
                else: st.error("Fel inloggning")
            conn.close()
    else:
        st.write(f"Inloggad som: **{st.session_state.auth['user']}**")
        if st.button("Logga ut"): st.session_state.auth = {'in': False}; st.rerun()

# --- HUVUDSIDA ---
if st.session_state.auth['in']:
    tabs = st.tabs(["🏠 ÖVERSIKT", "💰 PORTFÖLJ", "🎯 SCANNER"])
    
    with tabs[1]:
        st.header("Portföljhantering")
        
        with st.expander("➕ Lägg till innehav"):
            c1, c2, c3, c4 = st.columns(4)
            t_input = c1.text_input("Ticker (t.ex. SEB-A.ST eller BTC-USD)")
            a_input = c2.number_input("Antal", min_value=0.0)
            p_input = c3.number_input("Inköpspris", min_value=0.0)
            cur_input = c4.selectbox("Valuta", ["SEK", "USD"])
            if st.button("Spara"):
                add_holding(st.session_state.auth['user'], t_input, a_input, p_input, cur_input)
                st.success("Sparat!"); st.rerun()

        df = get_holdings(st.session_state.auth['user'])
        if not df.empty:
            total_sek = 0
            total_usd = 0
            
            for _, row in df.iterrows():
                try:
                    t_info = yf.Ticker(row['ticker']).fast_info
                    price = t_info['lastPrice']
                    
                    # Fix för SEK-aktier som ibland visas i ören
                    if ".ST" in row['ticker'] and price > 1000: price = price / 100
                    
                    value = price * row['amount']
                    profit = value - (row['buy_price'] * row['amount'])
                    
                    col1, col2, col3, col4 = st.columns([1,1,1,1])
                    col1.write(f"**{row['ticker']}**")
                    col2.metric("Pris", f"{price:.2f} {row['currency']}")
                    col3.metric("Värde", f"{value:,.0f} {row['currency']}")
                    col4.metric("Vinst/Förlust", f"{profit:,.0f} {row['currency']}", f"{(profit/(row['buy_price']*row['amount'])*100):+.2f}%")
                    st.divider()
                        
                    if row['currency'] == "SEK": total_sek += value
                    else: total_usd += value
                except:
                    st.error(f"Kunde inte hämta data för {row['ticker']}")

            st.subheader("Total sammanställning")
            st.info(f"💰 Totalt SEK: **{total_sek:,.0f}** | 💵 Totalt USD: **{total_usd:,.0f}**")
            
            st.write("---")
            del_ticker = st.selectbox("Ta bort innehav:", df['ticker'].tolist())
            if st.button("Radera markerad"):
                delete_holding(st.session_state.auth['user'], del_ticker)
                st.rerun()
        else:
            st.write("Tom portfölj.")

else:
    st.title("VAKTHUNDEN ULTRA")
    st.write("Logga in för att hantera din portfölj.")
