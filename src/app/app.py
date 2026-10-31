"""Điểm vào giao diện:  streamlit run src/app/app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # để import được `src.*`

import streamlit as st

from src import config, db

st.set_page_config(page_title="CVD Data Warehouse & DSS", page_icon="", layout="wide")

if not db.warehouse_ready():
    st.error("Không kết nối được kho dữ liệu MySQL hoặc chưa nạp dữ liệu. Kiểm tra file `.env` "
             "(MYSQL_HOST/PORT/USER/PASSWORD/DATABASE) rồi chạy: `python -m src.etl.run_etl`.")
    st.stop()

from src.app import page_dss, page_explorer, page_overview, page_risk, page_warehouse  # noqa: E402

PAGES = {
    "Tổng quan": page_overview.render,
    "OLAP Explorer": page_explorer.render,
    "Phân tích yếu tố nguy cơ": page_risk.render,
    "Hệ hỗ trợ quyết định (DSS)": page_dss.render,
    "Kho dữ liệu & ETL": page_warehouse.render,
}

with st.sidebar:
    st.title("CVD DW & DSS")
    st.caption("Kho dữ liệu và hệ hỗ trợ quyết định cho phân tích bệnh tim mạch (NHANES, 2011-2023)")
    _wanted = st.query_params.get("page")  # deep-link: ?page=<số thứ tự trang>, dùng khi chụp màn hình
    _idx = int(_wanted) if _wanted and _wanted.isdigit() and int(_wanted) < len(PAGES) else 0
    choice = st.radio("Trang", list(PAGES), index=_idx, label_visibility="collapsed")
    st.divider()
    st.caption("CO4031 - Data Warehouse & DSS, HK261")

PAGES[choice]()
