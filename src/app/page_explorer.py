"""Trang 2 - OLAP Explorer: slice/dice, pivot, roll-up/cube, drill-down."""
import plotly.express as px
import streamlit as st

from src import olap
from src.app.common import SEQ_BLUE, SERIES, chart

DIM_LABELS = {
    "cycle_label": "Chu kỳ", "period_group": "Giai đoạn", "source_system": "Nguồn dữ liệu",
    "sex": "Giới tính", "race": "Chủng tộc", "race_group": "Nhóm chủng tộc",
    "education": "Học vấn", "education_level": "Mức học vấn", "income_band": "Thu nhập",
    "age_group": "Nhóm tuổi (10 năm)", "life_stage": "Giai đoạn đời",
    "bmi_category": "Phân loại BMI", "weight_status": "Tình trạng cân nặng",
    "bp_category": "Phân loại huyết áp", "bp_group": "Nhóm huyết áp",
    "chol_category": "Phân loại cholesterol", "cvd_group": "Nhóm CVD", "profile_label": "Chi tiết bệnh CVD",
}


def _fmt(d):
    return DIM_LABELS.get(d, d)


def _filters_ui() -> dict:
    flt = {}
    with st.expander("Slice & Dice - bộ lọc", expanded=False):
        cols = st.columns(3)
        for i, dim in enumerate(["cycle_label", "sex", "age_group", "race_group", "income_band",
                                 "weight_status", "bp_group", "cvd_group", "source_system"]):
            vals = cols[i % 3].multiselect(_fmt(dim), olap.distinct_values(dim), key=f"flt_{dim}")
            if vals:
                flt[dim] = vals
    return flt


def render() -> None:
    st.header("OLAP Explorer")
    st.caption("Truy vấn đa chiều trên mô hình sao: chọn chiều (hàng/cột), thước đo, lọc, roll-up và drill-down.")
    flt = _filters_ui()
    tab_pivot, tab_cube, tab_drill, tab_sql = st.tabs(["Pivot", "Roll-up / Cube", "Drill-down", "SQL"])

    # ---------------------------------------------------------------- Pivot
    with tab_pivot:
        c1, c2, c3, c4 = st.columns(4)
        row = c1.selectbox("Hàng", list(olap.DIMENSIONS), index=list(olap.DIMENSIONS).index("age_group"), format_func=_fmt)
        col_opts = [d for d in olap.DIMENSIONS if d != row]
        col = c2.selectbox("Cột", col_opts, index=col_opts.index("bmi_category"), format_func=_fmt)
        measure = c3.selectbox("Thước đo", list(olap.MEASURES), index=1)
        min_n = c4.number_input("Cỡ mẫu tối thiểu / ô", 0, 1000, 30, step=10,
                                help="Ẩn các ô có ít người để tránh tỷ lệ thiếu ổn định")
        pv = olap.pivot(row, col, measure, flt, min_n=int(min_n))
        if pv.empty:
            st.info("Không có ô nào đủ cỡ mẫu.")
        else:
            fig = px.imshow(pv, text_auto=".1f", aspect="auto", color_continuous_scale=SEQ_BLUE,
                            labels=dict(x=_fmt(col), y=_fmt(row), color=measure))
            chart(fig, height=max(320, 48 * len(pv)), legend=False)
            with st.expander("Bảng số liệu"):
                st.dataframe(pv.round(2), width="stretch")

    # ------------------------------------------------------------ Roll-up / Cube
    with tab_cube:
        c1, c2 = st.columns([2, 1])
        dims = c1.multiselect("Các chiều (thứ tự = từ tổng quát -> chi tiết)",
                              list(olap.DIMENSIONS), default=["life_stage", "age_group"], format_func=_fmt)
        mode = c2.radio("Chế độ", ["rollup", "cube", "flat"], horizontal=True,
                        help="ROLLUP: tổng phụ theo cấp; CUBE: tổng phụ mọi tổ hợp; flat: GROUP BY thường")
        meas = st.multiselect("Thước đo", list(olap.MEASURES), default=["People (n)", "CVD prevalence (%)"])
        if dims and meas:
            df = olap.aggregate(dims, meas, flt, mode=mode)
            st.dataframe(df, width="stretch", hide_index=True, height=420)
            st.download_button("Tải CSV", df.to_csv(index=False).encode("utf-8-sig"), "olap_result.csv")
        else:
            st.info("Chọn ít nhất 1 chiều và 1 thước đo.")

    # ------------------------------------------------------------- Drill-down
    with tab_drill:
        c1, c2 = st.columns(2)
        hier = c1.selectbox("Phân cấp", list(olap.HIERARCHIES))
        meas = c2.multiselect("Thước đo ", list(olap.MEASURES), default=["People (n)", "CVD prevalence (%)"], key="dm")
        levels = olap.HIERARCHIES[hier]
        st.markdown(f"**Cấp 1:** {_fmt(levels[0])}  →  **Cấp 2:** {_fmt(levels[1])}")
        top = olap.drill(hier, 0, meas or ["People (n)"], flt)
        first = meas[0] if meas else "People (n)"
        fig = px.bar(top, x=levels[0], y=first, color_discrete_sequence=[SERIES[0]],
                     labels={levels[0]: _fmt(levels[0])})
        chart(fig, height=300, legend=False)
        parent = st.selectbox(f"Drill-down vào {_fmt(levels[0])}:", ["(tất cả)"] + top[levels[0]].tolist())
        sub = olap.drill(hier, 1, meas or ["People (n)"], flt, None if parent == "(tất cả)" else parent)
        if parent != "(tất cả)":
            st.markdown(f"Chi tiết **{parent}** theo {_fmt(levels[1])}")
        else:
            sub = sub.copy()
        fig = px.bar(sub, x=levels[1], y=first, color=levels[0] if parent == "(tất cả)" else None,
                     color_discrete_sequence=SERIES, labels={levels[1]: _fmt(levels[1])})
        chart(fig, height=340, legend=parent == "(tất cả)")
        st.dataframe(sub, width="stretch", hide_index=True)

    # -------------------------------------------------------------------- SQL
    with tab_sql:
        st.caption("Truy vấn tự do (chỉ SELECT) trên bảng phẳng `olap_exam`, view `v_nutrition` và các bảng dim/fact.")
        q = st.text_area("SQL", "SELECT cycle_label, age_group, count(*) AS n, round(avg(has_cvd)*100,1) AS cvd_pct\n"
                                "FROM olap_exam GROUP BY cycle_label, age_group ORDER BY 1, 2", height=130)
        if st.button("Chạy truy vấn", type="primary"):
            ql = q.strip().lower()
            if not ql.startswith(("select", "with")) or ";" in ql.rstrip(";") or " into " in f" {ql} ":
                st.error("Chỉ cho phép 1 câu SELECT/WITH (không dùng INTO).")
            else:
                try:
                    st.dataframe(olap.sql(q), width="stretch", hide_index=True)
                except Exception as e:  # lỗi cú pháp SQL của người dùng
                    st.error(str(e))
