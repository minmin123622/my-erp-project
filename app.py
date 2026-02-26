import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

# ၁။ Page Setup
st.set_page_config(page_title="Enterprise ERP Unified", layout="wide", page_icon="🏗️")

# --- Database Core ---
def init_db():
    with sqlite3.connect('construction_erp.db') as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT UNIQUE, unit TEXT, status TEXT DEFAULT 'active')")
        cursor.execute("CREATE TABLE IF NOT EXISTS sites (id INTEGER PRIMARY KEY AUTOINCREMENT, site_name TEXT UNIQUE, status TEXT DEFAULT 'Active')")
        cursor.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            v_no TEXT UNIQUE,
            site_name TEXT,
            type TEXT, 
            product_id INTEGER, 
            quantity REAL, 
            price REAL,
            status TEXT DEFAULT 'Normal', 
            remark TEXT, 
            created_by TEXT, 
            timestamp TEXT)""")
        
        # Default Admin
        cursor.execute("SELECT * FROM users WHERE username='admin'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin123', 'admin')")
        conn.commit()

init_db()

# --- Functions ---
def execute_db(q, p=()):
    with sqlite3.connect('construction_erp.db') as conn:
        conn.execute(q, p); conn.commit()

def run_query(q, p=()):
    with sqlite3.connect('construction_erp.db') as conn:
        return pd.read_sql_query(q, conn, params=p)

# --- Auth ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    _, center, _ = st.columns([1, 1.5, 1])
    with center:
        st.header("🔐 Secure Login")
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Log In"):
            res = run_query("SELECT role FROM users WHERE username=? AND password=?", (u, p))
            if not res.empty:
                st.session_state.logged_in, st.session_state.username, st.session_state.role = True, u, res.iloc[0]['role']
                st.rerun()
    st.stop()

# --- SIDEBAR: Input ---
st.sidebar.title(f"👤 {st.session_state.username.upper()}")
if st.sidebar.button("🚪 Log Out"):
    st.session_state.logged_in = False
    st.rerun()

st.sidebar.divider()
sites_df = run_query("SELECT site_name FROM sites WHERE status='Active'")
prods_df = run_query("SELECT id, name FROM products WHERE status='active'")

if not sites_df.empty and not prods_df.empty:
    with st.sidebar.form("daily_entry", clear_on_submit=True):
        v_no = f"V-{datetime.now().strftime('%y%m%d%H%M%S')}"
        st.info(f"Voucher: {v_no}")
        site = st.selectbox("Project Site ရွေးပါ", sites_df['site_name'].tolist())
        t_type = st.radio("အမျိုးအစား", ["Purchase (In)", "Usage (Out)"])
        p_id = st.selectbox("ပစ္စည်း", prods_df['id'].tolist(), format_func=lambda x: prods_df[prods_df['id']==x]['name'].values[0].upper())
        qty = st.number_input("အရေအတွက်", min_value=0.1, step=0.1)
        price = st.number_input("Unit Price", min_value=0.0) if t_type == "Purchase (In)" else 0
        remark = st.text_area("Remark (မှတ်ချက်)")
        
        if st.form_submit_button("Confirm & Save"):
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            execute_db("""INSERT INTO transactions (v_no, site_name, type, product_id, quantity, price, remark, created_by, timestamp) 
                          VALUES (?,?,?,?,?,?,?,?,?)""", (v_no, site, t_type, p_id, qty, price, remark, st.session_state.username, now))
            st.sidebar.success(f"ဘောင်ချာ {v_no} သွင်းပြီးပါပြီ")
            st.rerun()

# --- MAIN DASHBOARD ---
st.title("🏗️ Project Control Center")

# Analytics
df_stock = run_query("""
    SELECT p.id, p.name as Product, p.unit as Unit,
    COALESCE((SELECT SUM(quantity) FROM transactions WHERE product_id=p.id AND type='Purchase (In)' AND status!='Deleted'), 0) - 
    COALESCE((SELECT SUM(quantity) FROM transactions WHERE product_id=p.id AND type='Usage (Out)' AND status!='Deleted'), 0) as Balance,
    COALESCE((SELECT AVG(price) FROM transactions WHERE product_id=p.id AND type='Purchase (In)' AND status!='Deleted'), 0) as AvgPrice
    FROM products p WHERE status='active'
""")
df_stock['Value'] = df_stock['Balance'] * df_stock['AvgPrice']

# KPI Row
k1, k2, k3 = st.columns(3)
k1.metric("Stock Value (Total)", f"{df_stock['Value'].sum():,.0f} MMK")
k2.metric("Active Sites", len(sites_df))
k3.metric("Low Stock Items", len(df_stock[df_stock['Balance'] < 10]))

tab1, tab2, tab3 = st.tabs(["📊 Inventory Monitor", "🔎 Voucher Search", "⚙️ Admin Settings"])

with tab1:
    c1, c2 = st.columns([2, 1])
    with c1:
        if not df_stock.empty:
            fig = px.bar(df_stock, x='Product', y='Balance', color='Balance', text_auto=True)
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.dataframe(df_stock[['Product', 'Balance', 'Unit']], hide_index=True)

with tab2:
    search = st.text_input("🔎 Voucher နံပါတ် သို့မဟုတ် Site အမည်ဖြင့် ရှာရန်", "")
    hist_query = """SELECT t.v_no, t.site_name, t.type, p.name as Product, t.quantity, t.status, t.remark, t.timestamp 
                    FROM transactions t JOIN products p ON t.product_id=p.id"""
    if search:
        hist_df = run_query(hist_query + f" WHERE t.v_no LIKE '%{search}%' OR t.site_name LIKE '%{search}%'")
    else:
        hist_df = run_query(hist_query + " ORDER BY t.id DESC LIMIT 20")
    st.dataframe(hist_df, use_container_width=True)

with tab3:
    if st.session_state.role == 'admin':
        col_site, col_prod = st.columns(2)
        with col_site:
            st.subheader("🏗️ Manage Sites")
            new_s = st.text_input("Project Site အမည်သစ်")
            if st.button("Add Site"):
                execute_db("INSERT OR IGNORE INTO sites (site_name) VALUES (?)", (new_s,))
                st.rerun()
            st.table(run_query("SELECT site_name, status FROM sites"))
        with col_prod:
            st.subheader("📦 Manage Products")
            pn = st.text_input("ပစ္စည်းအမည်")
            pu = st.text_input("Unit")
            if st.button("Add Product"):
                execute_db("INSERT OR IGNORE INTO products (name, unit) VALUES (?,?)", (pn.lower(), pu))
                st.rerun()