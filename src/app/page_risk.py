"""Trang 3 - Phân tích nguyên nhân (root-cause): yếu tố nguy cơ và dinh dưỡng."""
import plotly.express as px
import streamlit as st

from src import olap
from src.app.common import SEQ_BLUE, SERIES, chart


def render() -> None:
    st.header("Phân tích yếu tố nguy cơ")
    tab_rf, tab_nut = st.tabs(["Yếu tố nguy cơ & CVD", "Dinh dưỡng (2017-2023)"])

    with tab_rf:
        st.subheader("Tuổi tác chi phối, nhưng cân nặng và huyết áp làm khác biệt trong cùng nhóm tuổi")
        c1, c2 = st.columns(2)
        factor = c1.selectbox("Yếu tố so sánh", ["weight_status", "bp_group", "chol_category", "income_band", "race_group"],
                              format_func={"weight_status": "Tình trạng cân nặng", "bp_group": "Nhóm huyết áp",
                                           "chol_category": "Cholesterol", "income_band": "Thu nhập",
                                           "race_group": "Nhóm chủng tộc"}.get)
        stage = c2.multiselect("Giới hạn nhóm tuổi", olap.distinct_values("life_stage"),
                               default=olap.distinct_values("life_stage"))
        flt = {"life_stage": stage, "source_system": ["NHANES_XPT"]}
        d = olap.aggregate(["age_group", factor], ["CVD prevalence (%)", "People (n)"], flt, min_n=40)
        d = d[d[factor] != "Unknown"]
        fig = px.line(d, x="age_group", y="CVD prevalence (%)", color=factor, markers=True,
                      color_discrete_sequence=SERIES, labels={"age_group": "Nhóm tuổi"},
                      hover_data={"People (n)": ":,"},
                      category_orders={"age_group": [v for v in olap.distinct_values("age_group") if v != "Unknown"]})
        fig.update_traces(line_width=2, marker_size=8)
        chart(fig)
        st.caption("Chỉ dùng nguồn XPT (2011-2018), nơi có đủ biến nhân khẩu học. Ô < 40 người bị ẩn.")

        st.subheader("Bản đồ nhiệt: tuổi × huyết áp")
        pv = olap.pivot("age_group", "bp_category", "CVD prevalence (%)", {"source_system": ["NHANES_XPT"]}, min_n=40)
        pv = pv.drop(columns=[c for c in pv.columns if c == "Unknown"], errors="ignore")
        fig = px.imshow(pv, text_auto=".1f", aspect="auto", color_continuous_scale=SEQ_BLUE,
                        labels=dict(color="CVD (%)", x="Phân loại huyết áp", y="Nhóm tuổi"))
        chart(fig, height=360, legend=False)
        st.info("Lưu ý diễn giải: nhóm tăng huyết áp mức 2 ở người cao tuổi có tỷ lệ CVD cao nhưng người đang điều trị "
                "tốt thường có huyết áp 'bình thường' - dữ liệu cắt ngang không có thông tin thuốc, nên không suy ra nhân quả.")

    with tab_nut:
        st.caption("Nguồn Nhanes_cvd_raw.csv: lượng ăn vào 24 giờ (một ngày hồi tưởng) - biến động theo ngày, chỉ nên so sánh theo nhóm.")
        n = olap.sql("SELECT count(*) AS n FROM fact_nutrition").iloc[0, 0]
        st.write(f"**{n:,}** người có dữ liệu dinh dưỡng.")
        c1, c2 = st.columns(2)
        group = c1.selectbox("Nhóm theo", ["bp_group", "cvd_group", "weight_status", "age_group", "cycle_label"],
                             format_func={"bp_group": "Nhóm huyết áp", "cvd_group": "Nhóm CVD", "weight_status": "Cân nặng",
                                          "age_group": "Tuổi", "cycle_label": "Chu kỳ"}.get)
        nutrient = c2.selectbox("Chất dinh dưỡng", {
            "sodium_mg": "Natri (mg)", "potassium_mg": "Kali (mg)", "na_k_ratio": "Tỷ lệ Na/K",
            "fiber_g": "Chất xơ (g)", "saturated_fat_g": "Chất béo bão hoà (g)", "sugar_g": "Đường (g)",
            "dietary_chol_mg": "Cholesterol ăn vào (mg)"}, format_func=lambda k: {
            "sodium_mg": "Natri (mg)", "potassium_mg": "Kali (mg)", "na_k_ratio": "Tỷ lệ Na/K",
            "fiber_g": "Chất xơ (g)", "saturated_fat_g": "Chất béo bão hoà (g)", "sugar_g": "Đường (g)",
            "dietary_chol_mg": "Cholesterol ăn vào (mg)"}[k])
        df = olap.sql(f"""SELECT {group} AS grp, avg({nutrient}) AS avg_v, count(*) AS n
                          FROM v_nutrition WHERE {group} <> 'Unknown' GROUP BY {group} HAVING count(*) >= 50 ORDER BY grp""")
        fig = px.bar(df, x="grp", y="avg_v", color_discrete_sequence=[SERIES[0]],
                     labels={"grp": "", "avg_v": "Trung bình"}, hover_data={"n": ":,"})
        chart(fig, height=340, legend=False)
        st.subheader("Tỷ lệ ăn mặn (>= 2.300 mg natri/ngày) và ăn ít xơ (< 25 g)")
        df = olap.sql("""SELECT bp_group, round(avg(high_sodium)*100,1) AS "High sodium (%)",
                                round(avg(low_fiber)*100,1) AS "Low fiber (%)", count(*) AS n
                         FROM v_nutrition WHERE bp_group <> 'Unknown' GROUP BY bp_group ORDER BY bp_group""")
        st.dataframe(df, width="stretch", hide_index=True)
