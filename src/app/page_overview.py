"""Trang 1 - Tổng quan: KPI, xu hướng theo chu kỳ, phân bố theo tuổi/giới/nhóm."""
import plotly.express as px
import streamlit as st

from src import olap
from src.app.common import SERIES, chart, kpi_row


def render() -> None:
    st.header("Tổng quan sức khoẻ tim mạch")
    st.caption("Nguồn: NHANES (CDC)")

    c1, c2 = st.columns(2)
    sexes = c1.multiselect("Giới tính", ["Male", "Female", "Unknown"], default=["Male", "Female", "Unknown"],
                           help="Unknown = nguồn CSV 2017-2023 không có biến giới tính")
    stages = c2.multiselect("Nhóm tuổi", olap.distinct_values("life_stage"), default=olap.distinct_values("life_stage"))
    flt = {"sex": sexes, "life_stage": stages}

    tot = olap.aggregate([], ["People (n)", "CVD prevalence (%)", "Hypertension prevalence (%)",
                              "Obesity prevalence (%)", "Avg systolic BP"], flt)
    if tot.empty or tot.iloc[0, 0] == 0:
        st.warning("Không có dữ liệu cho bộ lọc này.")
        return
    t = tot.iloc[0]
    kpi_row([
        ("Số người", f"{int(t['People (n)']):,}", "Số bản ghi khám trong kho dữ liệu"),
        ("Tỷ lệ mắc CVD", f"{t['CVD prevalence (%)']:.1f}%", "Suy tim, mạch vành, đau thắt ngực, nhồi máu hoặc đột quỵ (tự khai báo)"),
        ("Tăng huyết áp", f"{t['Hypertension prevalence (%)']:.1f}%", "SBP>=130 hoặc DBP>=80 (ACC/AHA 2017)"),
        ("Béo phì", f"{t['Obesity prevalence (%)']:.1f}%", "BMI >= 30"),
        ("SBP trung bình", f"{t['Avg systolic BP']:.0f} mmHg", None),
    ])

    st.subheader("Xu hướng theo chu kỳ khảo sát")
    trend = olap.aggregate(["cycle_label"], ["CVD prevalence (%)", "Hypertension prevalence (%)",
                                             "Obesity prevalence (%)"], flt, min_n=100)
    long = trend.melt("cycle_label", var_name="Chỉ số", value_name="Tỷ lệ (%)")
    fig = px.line(long, x="cycle_label", y="Tỷ lệ (%)", color="Chỉ số", markers=True,
                  color_discrete_sequence=SERIES, labels={"cycle_label": "Chu kỳ"})
    fig.update_traces(line_width=2, marker_size=8)
    chart(fig)
    st.caption("Lưu ý: '2017-2018' (file XPT) và '2017-Mar 2020' (CSV) có chung một phần thời gian khảo sát "
               "nên không cộng gộp số người giữa hai chu kỳ này; so sánh tỷ lệ thì hợp lệ.")

    left, right = st.columns(2)
    with left:
        st.subheader("Mắc CVD theo tuổi & giới")
        d = olap.aggregate(["age_group", "sex"], ["CVD prevalence (%)"], {**flt, "sex": [s for s in sexes if s != "Unknown"] or ["Male", "Female"]}, min_n=50)
        fig = px.line(d, x="age_group", y="CVD prevalence (%)", color="sex", markers=True,
                      color_discrete_map={"Male": SERIES[0], "Female": SERIES[1]},
                      labels={"age_group": "Nhóm tuổi"},
                      category_orders={"age_group": [v for v in olap.distinct_values("age_group") if v != "Unknown"]})
        fig.update_traces(line_width=2, marker_size=8)
        chart(fig, height=340)
    with right:
        st.subheader("Các loại bệnh tim mạch")
        d = olap.sql("""SELECT 'Heart failure' AS c, sum(v.chf='Yes') AS n FROM fact_health_exam f JOIN dim_cvd_profile v USING(cvd_profile_key)
                        UNION ALL SELECT 'Coronary disease', sum(v.chd='Yes') FROM fact_health_exam f JOIN dim_cvd_profile v USING(cvd_profile_key)
                        UNION ALL SELECT 'Angina', sum(v.angina='Yes') FROM fact_health_exam f JOIN dim_cvd_profile v USING(cvd_profile_key)
                        UNION ALL SELECT 'Heart attack', sum(v.heart_attack='Yes') FROM fact_health_exam f JOIN dim_cvd_profile v USING(cvd_profile_key)
                        UNION ALL SELECT 'Stroke', sum(v.stroke='Yes') FROM fact_health_exam f JOIN dim_cvd_profile v USING(cvd_profile_key)
                        ORDER BY n""")
        fig = px.bar(d, x="n", y="c", orientation="h", color_discrete_sequence=[SERIES[0]],
                     labels={"n": "Số người", "c": ""}, text="n")
        fig.update_traces(texttemplate="%{text:,}", textposition="outside", cliponaxis=False)
        fig.update_xaxes(range=[0, d["n"].max() * 1.15])
        chart(fig, height=340, legend=False)

    st.subheader("Chênh lệch giữa các nhóm")
    c1, c2 = st.columns(2)
    for col, dim, title in [(c1, "race", "Chủng tộc / dân tộc"), (c2, "income_band", "Thu nhập (PIR)")]:
        d = olap.aggregate([dim], ["CVD prevalence (%)", "People (n)"], flt, min_n=100)
        d = d[d[dim] != "Unknown"]
        fig = px.bar(d, x=dim, y="CVD prevalence (%)", color_discrete_sequence=[SERIES[0]],
                     labels={dim: title}, hover_data={"People (n)": ":,"})
        col.markdown(f"**CVD theo {title}**")
        with col:
            chart(fig, height=320, legend=False)
