"""Trang 5 - Kho dữ liệu: sơ đồ sao, nhật ký ETL, từ điển dữ liệu, kiểm tra chất lượng."""
import streamlit as st

from src import config, olap

STAR_DOT = """
digraph G {
  rankdir=LR; nodesep=0.25; ranksep=2.2; node [shape=box, fontname="Helvetica", fontsize=11, style="rounded,filled"];
  edge [color="#8a8a85"];
  F1 [label="fact_health_exam\\n(exam_id, 14 measures, 5 flags)", fillcolor="#cfe2fa", color="#2a78d6", penwidth=2];
  F2 [label="fact_nutrition\\n(exam_id, 14 measures, 2 flags)", fillcolor="#cfe2fa", color="#2a78d6", penwidth=2];
  node [fillcolor="#f1f1ee", color="#8a8a85", penwidth=1];
  D1 [label="dim_cycle\\nperiod_group > cycle"]; D2 [label="dim_sex"];
  D3 [label="dim_race\\nrace_group > race"]; D4 [label="dim_education\\nlevel > education"];
  D5 [label="dim_income"]; D6 [label="dim_age_group\\nlife_stage > age_group"];
  D7 [label="dim_bmi_category\\nweight_status > bmi"]; D8 [label="dim_bp_category\\nbp_group > bp"];
  D9 [label="dim_chol_category"]; D10 [label="dim_cvd_profile\\n(junk dim) cvd_group > profile"];
  {rank=same; F2; F1}
  F1 -> {D1 D2 D3 D4 D5 D6 D7 D8 D9 D10};
  F2 -> {D1 D6 D7 D8 D10};
  F2 -> F1 [style=dashed, label="exam_id"];
}
"""

DICTIONARY = [
    ("has_cvd", "Cờ 0/1", "1 nếu tự khai báo ≥1 trong: suy tim, bệnh mạch vành, đau thắt ngực, nhồi máu cơ tim, đột quỵ (NHANES MCQ160B-F)"),
    ("is_hypertensive", "Cờ 0/1", "SBP ≥ 130 hoặc DBP ≥ 80 mmHg (trung bình các lần đo hợp lệ), theo ACC/AHA 2017"),
    ("is_obese", "Cờ 0/1", "BMI ≥ 30"),
    ("is_high_chol", "Cờ 0/1", "Cholesterol toàn phần ≥ 240 mg/dL"),
    ("is_low_hdl", "Cờ 0/1", "HDL < 40 (nam) hoặc < 50 (nữ) mg/dL"),
    ("sbp / dbp", "mmHg", "Trung bình các lần đo 2-4 (BPXSY2-4, BPXDI2-4), nếu chỉ có lần 1 thì dùng lần 1, theo quy ước CDC; nguồn CSV dùng giá trị có sẵn"),
    ("mec_weight", "trọng số", "WTMEC2YR - chỉ có ở nguồn XPT; hiện chưa dùng để gia quyền"),
    ("crp_mgl", "mg/L", "C-reactive protein - chỉ có ở nguồn CSV"),
    ("high_sodium", "Cờ 0/1", "Natri ≥ 2.300 mg/ngày (hồi tưởng 24h)"),
]


def render() -> None:
    st.header("Kho dữ liệu & ETL")
    tab_schema, tab_etl, tab_dq, tab_dict = st.tabs(["Sơ đồ sao", "Nhật ký ETL", "Chất lượng dữ liệu", "Từ điển dữ liệu"])

    with tab_schema:
        st.graphviz_chart(STAR_DOT, width="stretch")
        st.markdown(
            "**Mô hình Constellation (fact constellation):** hai bảng fact chia sẻ các dimension đã đồng nhất (conformed). "
            "`dim_cvd_profile` là *junk dimension* gom 5 cờ bệnh. Mỗi dimension có phân cấp cho drill-down/roll-up. "
            "Bản ghi thiếu thuộc tính được trỏ về thành viên `Unknown` (key = 0) nên không mất dòng khi JOIN.")
        counts = olap.sql("""SELECT 'fact_health_exam' AS tbl, count(*) AS n_rows FROM fact_health_exam
            UNION ALL SELECT 'fact_nutrition', count(*) FROM fact_nutrition
            UNION ALL SELECT 'dim_cycle', count(*) FROM dim_cycle UNION ALL SELECT 'dim_age_group', count(*) FROM dim_age_group
            UNION ALL SELECT 'dim_cvd_profile', count(*) FROM dim_cvd_profile""")
        st.dataframe(counts, hide_index=True, width="content")
        with st.expander("DDL (schema.sql)"):
            st.code((config.SQL_DIR / "schema.sql").read_text(encoding="utf-8"), language="sql")

    with tab_etl:
        st.markdown("**Quy trình:** Extract (6 bảng × 4 chu kỳ XPT + 1 CSV) → Transform (lọc người ≥ 20 tuổi, trung bình huyết áp, "
                    "mã hoá Yes/No, loại outlier, phân lớp thành key dimension, tích hợp 2 nguồn) → Load (MySQL 8.0, full refresh).")
        log = olap.sql("SELECT step, detail, rows_in, rows_out, rows_dropped, logged_at FROM etl_log")
        st.dataframe(log, hide_index=True, width="stretch")

    with tab_dq:
        dq = olap.sql("""
            SELECT c.cycle_label AS cycle, count(*) AS n,
                   round(100.0 * count(sbp) / count(*), 1) AS "SBP có (%)",
                   round(100.0 * count(bmi) / count(*), 1) AS "BMI có (%)",
                   round(100.0 * count(total_chol) / count(*), 1) AS "TC có (%)",
                   round(100.0 * count(hdl_chol) / count(*), 1) AS "HDL có (%)",
                   round(100.0 * count(has_cvd) / count(*), 1) AS "Nhãn CVD có (%)"
            FROM fact_health_exam f JOIN dim_cycle c USING (cycle_key) GROUP BY c.cycle_label, c.cycle_key ORDER BY c.cycle_key""")
        st.markdown("**Độ đầy đủ dữ liệu theo chu kỳ** (tỷ lệ bản ghi có giá trị):")
        st.dataframe(dq, hide_index=True, width="stretch")
        st.caption("HDL không có ở nguồn CSV; huyết áp/cholesterol thiếu do không phải ai cũng được đo trong phiên khám.")

    with tab_dict:
        st.dataframe([dict(zip(["Trường", "Đơn vị/kiểu", "Định nghĩa"], r)) for r in DICTIONARY], hide_index=True, width="stretch")
