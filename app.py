import streamlit as st
import yfinance as yf
import pandas as pd
import sqlite3
import numpy as np
import plotly.graph_objects as go
import easyocr
from PIL import Image

# --- 1. 初始化資料庫 ---
def init_db():
    conn = sqlite3.connect('portfolio.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS inventory
                 (ticker TEXT, shares REAL, cost REAL, date TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 2. 介面設定與標題 ---
st.set_page_config(page_title="台美股助手", layout="centered")
st.title("📱 我的投資小幫手")

# --- 3. 手動新增庫存 ---
with st.expander("➕ 手動新增庫存股"):
    with st.form("add_stock_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            new_ticker = st.text_input("代號 (台股加 .TW)").upper()
            new_shares = st.number_input("股數", min_value=0.01)
        with col2:
            new_cost = st.number_input("成交單價", min_value=0.01)
            new_date = st.date_input("買入日期")
        
        if st.form_submit_button("存入資料庫"):
            conn = sqlite3.connect('portfolio.db')
            c = conn.cursor()
            c.execute("INSERT INTO inventory VALUES (?, ?, ?, ?)", 
                      (new_ticker, new_shares, new_cost, str(new_date)))
            conn.commit()
            conn.close()
            st.success(f"已成功加入 {new_ticker}！")

# --- 4. 截圖自動匯入 (OCR) ---
@st.cache_resource
def load_ocr():
    return easyocr.Reader(['ch_tra', 'en'])

with st.expander("📸 上傳截圖辨識"):
    uploaded_file = st.file_uploader("從手機相簿選擇圖片", type=["png", "jpg", "jpeg"])
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, use_container_width=True)
        if st.button("開始辨識"):
            with st.spinner("AI 辨識中..."):
                reader = load_ocr()
                result = reader.readtext(np.array(image), detail=0)
                st.info(", ".join(result))

# --- 5. 定期定額推算 ---
with st.expander("💰 定期定額複利推算"):
    monthly = st.number_input("每月投入金額", value=10000, step=1000)
    years = st.slider("投資年期", 1, 40, 10)
    targets = st.text_input("比較標的 (逗號隔開)", "保守型, 穩健型, 積極型")
    
    targets_list = [t.strip() for t in targets.split(",")]
    rates = {}
    cols = st.columns(len(targets_list))
    for i, t in enumerate(targets_list):
        rates[t] = cols[i].number_input(f"{t} 預期年化(%)", value=5.0 + (i*2), step=0.5)

    if st.button("推算比較"):
        months = years * 12
        x_axis = np.arange(months + 1)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x_axis, y=x_axis*monthly, name="總成本", line=dict(dash='dash', color='gray')))

        for name, rate in rates.items():
            m_rate = (1 + rate/100)**(1/12) - 1
            y_vals = [0]
            val = 0
            for _ in range(months):
                val = (val + monthly) * (1 + m_rate)
                y_vals.append(val)
            fig.add_trace(go.Scatter(x=x_axis, y=y_vals, name=f"{name} ({rate}%)"))
            
        fig.update_layout(hovermode="x unified", legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)

# --- 6. 20 年回測 ---
with st.expander("⏳ 20 年長線回測"):
    target_stock = st.text_input("輸入回測代號", "2330.TW")
    if st.button("開始回測"):
        hist = yf.download(target_stock, period="20y")
        if not hist.empty:
            p_start, p_end = hist['Close'].iloc[0], hist['Close'].iloc[-1]
            total_ret = (p_end / p_start - 1) * 100
            cagr = ((p_end / p_start) ** (1/(len(hist)/252)) - 1) * 100
            st.metric("20 年總報酬", f"{total_ret:.1f}%", f"年化: {cagr:.2f}%")
            st.line_chart(hist['Close'])
        else:
            st.error("查無資料")

# --- 7. 持股儀表板 ---
st.subheader("📊 持股診斷儀表板")
conn = sqlite3.connect('portfolio.db')
df_inv = pd.read_sql_query("SELECT * FROM inventory", conn)
conn.close()

if not df_inv.empty:
    summary = df_inv.groupby('ticker').agg({'shares': 'sum', 'cost': 'mean'}).reset_index()
    prices = [yf.Ticker(t).history(period="1d")['Close'].iloc[-1] for t in summary['ticker']]
    summary['市價'] = prices
    summary['總市值'] = (summary['shares'] * summary['市價']).round(0)
    summary['報酬率'] = (((summary['市價'] - summary['cost']) / summary['cost']) * 100).round(2)
    
    st.metric("總資產價值", f"${summary['總市值'].sum():,.0f}")
    for _, row in summary.iterrows():
        color = "green" if row['報酬率'] >= 0 else "red"
        st.markdown(f"**{row['ticker']}** | 市值: ${row['總市值']:,.0f} | 報酬: :{color}[{row['報酬率']}%]")
else:
    st.info("目前尚無庫存資料。")
