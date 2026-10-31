"""Trang 4 - Hệ hỗ trợ quyết định (DSS)."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import olap
from src.app.common import SERIES, STATUS_ICON, chart, kpi_row
from src.dss import engine, risk_model


@st.cache_resource(show_spinner="Đang nạp mô hình...")
def _bundle():
    return risk_model.load_bundle()


def _effect_sizes_ui(prefix: str) -> engine.EffectSizes:
    with st.expander("Giả định về hiệu quả can thiệp (RR từ y văn - có thể chỉnh)"):
        a, b, c, d = st.columns(4)
        fx = engine.EffectSizes(
            rr_per_10mmhg_sbp=a.number_input("RR / giảm 10 mmHg SBP", 0.5, 1.0, 0.80, 0.01,
                                             help="Ettehad et al., Lancet 2016", key=f"{prefix}_rr1"),
            rr_per_39mgdl_tc=b.number_input("RR / giảm 39 mg/dL cholesterol", 0.5, 1.0, 0.78, 0.01,
                                            help="CTT Collaboration, Lancet 2010 (giả định giảm TC ~ giảm LDL)", key=f"{prefix}_rr2"),
            rr_per_1bmi=c.number_input("RR / giảm 1 đơn vị BMI", 0.80, 1.0, 0.953, 0.001,
                                       help="Giả định minh hoạ, cùng bậc với các phân tích gộp (vd. ERFC, Lancet 2011); cần đối chiếu số gốc", key=f"{prefix}_rr3"),
            realization=d.slider("Tỷ lệ hiệu quả đạt được", 0.1, 1.0, 0.6, 0.05,
                                 help="Hiệu quả ngoài đời thực thấp hơn thử nghiệm (tuân thủ, duy trì)", key=f"{prefix}_real"))
    return fx


def _intervention_ui(prefix: str) -> tuple[float, float, float]:
    a, b, c = st.columns(3)
    sbp = a.slider("Giảm huyết áp tâm thu (mmHg)", 0, 30, 10, key=f"{prefix}_sbp")
    tc = b.slider("Giảm cholesterol toàn phần (mg/dL)", 0, 80, 30, key=f"{prefix}_tc")
    bmi = c.slider("Giảm BMI (đơn vị)", 0.0, 6.0, 1.5, 0.5, key=f"{prefix}_bmi")
    return float(sbp), float(tc), float(bmi)


def render() -> None:
    st.header("Hệ hỗ trợ quyết định (DSS)")
    st.caption("Kết hợp dữ liệu từ kho (nguy cơ nền, quy mô nhóm) với mô hình can thiệp để trả lời: "
               "*ai có nguy cơ cao?*, *can thiệp thì được gì?*, *nên dồn ngân sách vào đâu?*, *nhóm nào đang xấu đi?*")
    bundle = _bundle()
    t1, t2, t3, t4, t5 = st.tabs(["1. Nguy cơ cá nhân", "2. What-if", "3. Phân bổ ngân sách", "4. Cảnh báo xu hướng", "Mô hình"])

    # ------------------------------------------------------------ cá nhân
    with t1:
        c = st.columns(4)
        age = c[0].number_input("Tuổi", 20, 90, 58)
        male = c[1].radio("Giới", ["Nam", "Nữ"], horizontal=True) == "Nam"
        sbp = c[2].number_input("Huyết áp tâm thu", 80, 230, 142)
        dbp = c[3].number_input("Huyết áp tâm trương", 40, 140, 88)
        c = st.columns(3)
        bmi = c[0].number_input("BMI", 15.0, 60.0, 29.5, 0.1)
        tc = c[1].number_input("Cholesterol toàn phần (mg/dL)", 100, 400, 225)
        hdl = c[2].number_input("HDL (mg/dL)", 15, 120, 42)
        r = engine.assess_individual(age, male, sbp, dbp, bmi, tc, hdl, bundle)

        kpi_row([
            ("Xác suất mắc CVD (mô hình)", f"{r['probability'] * 100:.1f}%", "Xác suất đã/đang mắc ≥1 bệnh tim mạch, không phải nguy cơ 10 năm"),
            ("Mức nguy cơ", r["band"], "Low <5%, Moderate 5-12%, High 12-25%, Very high ≥25%"),
            (f"Nhóm cùng tuổi/giới (n={r['peer_n']:,})", f"{r['peer_rate'] * 100:.1f}%", "Tỷ lệ hiện mắc thực tế trong kho dữ liệu, ±5 tuổi cùng giới"),
            ("Nếu đạt mục tiêu điều trị", f"{r['p_if_targets_met'] * 100:.1f}%",
             "HA<120, cholesterol<200, BMI<25 - áp dụng RR từ y văn lên xác suất nền"),
        ])
        left, right = st.columns([1, 1])
        with left:
            st.subheader("Khuyến nghị")
            for level, text in r["advice"]:
                st.markdown(f"{STATUS_ICON[level]} {text}")
        with right:
            st.subheader("Đóng góp vào nguy cơ")
            ct = pd.DataFrame({"Yếu tố": list(r["contributions"]), "logit": list(r["contributions"].values())})
            ct["Hướng"] = ct["logit"].map(lambda v: "Tăng nguy cơ" if v > 0 else "Giảm nguy cơ")
            fig = px.bar(ct, x="logit", y="Yếu tố", color="Hướng", orientation="h",
                         color_discrete_map={"Tăng nguy cơ": SERIES[1], "Giảm nguy cơ": SERIES[0]},
                         labels={"logit": "Đóng góp vào log-odds so với trung bình dân số"})
            chart(fig, height=300)
        st.caption("Huyết áp có đóng góp ≈0 trong mô hình dữ liệu vì người bệnh đã dùng thuốc hạ áp (nhiễu điều trị). "
                   "Vì vậy khuyến nghị huyết áp/cholesterol dựa trên luật hướng dẫn lâm sàng, không dựa trên hệ số mô hình.")

    # ------------------------------------------------------------- what-if
    with t2:
        st.markdown("**Nếu một nhóm dân số đạt mức cải thiện X thì số ca CVD giảm bao nhiêu?** "
                    "(mức giảm bị chặn ở ngưỡng mục tiêu: HA 120, cholesterol 199, BMI 24.9).")
        fx = _effect_sizes_ui("wi")
        sbp_d, tc_d, bmi_d = _intervention_ui("wi")
        f1, f2, f3 = st.columns(3)
        flt = {}
        for col, dim, lab in [(f1, "age_group", "Nhóm tuổi"), (f2, "bp_group", "Nhóm huyết áp"), (f3, "weight_status", "Cân nặng")]:
            vals = col.multiselect(lab, [v for v in olap.distinct_values(dim) if v != "Unknown"], key=f"wi_f_{dim}")
            if vals:
                flt[dim] = vals
        res = engine.simulate_intervention(sbp_d, tc_d, bmi_d, flt, fx, bundle)
        if res["n"] == 0:
            st.warning("Không có dữ liệu cho nhóm đã chọn.")
        else:
            kpi_row([
                ("Quy mô mẫu nhóm", f"{res['n']:,}", None),
                ("Nguy cơ sau can thiệp", f"{res['after_risk'] * 100:.1f}%", f"Hiện tại {res['baseline_risk'] * 100:.1f}%"),
                ("Giảm tương đối", f"{res['rel_reduction'] * 100:.1f}%", None),
                ("Ca tránh được / 1.000 người", f"{res['cases_avoided_per_1000']:.1f}", None),
                ("Tỷ lệ người được hưởng lợi", f"{res['share_affected'] * 100:.0f}%", "Người còn trên ngưỡng mục tiêu"),
            ])
            by = res["by_age"].melt("age_group", var_name="Kịch bản", value_name="Nguy cơ")
            by["Kịch bản"] = by["Kịch bản"].map({"before": "Hiện tại", "after": "Sau can thiệp"})
            by["Nguy cơ"] *= 100
            fig = px.bar(by, x="age_group", y="Nguy cơ", color="Kịch bản", barmode="group",
                         color_discrete_map={"Hiện tại": SERIES[0], "Sau can thiệp": SERIES[2]},
                         labels={"age_group": "Nhóm tuổi", "Nguy cơ": "Xác suất CVD trung bình (%)"})
            chart(fig)

    # ------------------------------------------------------------ ngân sách
    with t3:
        st.markdown("**Với ngân sách hữu hạn, nên ưu tiên can thiệp nhóm nào để tránh được nhiều ca CVD nhất?** "
                    "Hệ thống xếp hạng các phân khúc theo *ca tránh được trên mỗi đồng chi phí* và lấp đầy ngân sách theo thứ tự đó.")
        fx = _effect_sizes_ui("al")
        c = st.columns(3)
        pop = c[0].number_input("Dân số mục tiêu (người)", 1_000, 50_000_000, 100_000, 10_000)
        cost = c[1].number_input("Chi phí can thiệp / người (USD)", 10, 5_000, 300, 10)
        budget = c[2].number_input("Ngân sách (USD)", 10_000, 500_000_000, 2_000_000, 100_000)
        seg_by = st.multiselect("Phân khúc theo", list(engine.SEGMENT_DIMS), default=["Age group", "Blood pressure group"])
        sbp_d, tc_d, bmi_d = _intervention_ui("al")
        if not seg_by:
            st.info("Chọn ít nhất một tiêu chí phân khúc.")
        else:
            out = engine.allocate_budget(budget, cost, pop, seg_by, sbp_d, tc_d, bmi_d, fx, bundle)
            seg = out["segments"]
            gain = out["optimized_avoided"] - out["uniform_avoided"]
            kpi_row([
                ("Ca CVD tránh được (ưu tiên)", f"{out['optimized_avoided']:,.0f}", None),
                ("Nếu chia đều ngân sách", f"{out['uniform_avoided']:,.0f}", f"Độ phủ đều {out['uniform_coverage'] * 100:.1f}%"),
                ("Chênh lệch nhờ DSS", f"{gain:+,.0f} ca", None),
                ("Số người được phủ", f"{out['people_covered']:,.0f}", f"Chi {out['budget_used']:,.0f} USD"),
            ])
            show = seg[seg["coverage"] > 0]
            fig = px.bar(show.sort_values("cases_avoided"), x="cases_avoided", y="segment", orientation="h",
                         color_discrete_sequence=[SERIES[0]], text="cases_avoided",
                         labels={"cases_avoided": "Ca tránh được", "segment": ""})
            fig.update_traces(texttemplate="%{text:.0f}", textposition="outside", cliponaxis=False)
            chart(fig, height=max(260, 34 * len(show) + 80), legend=False)
            tbl = seg[["segment", "size", "baseline_risk", "arr", "efficiency", "coverage", "spend", "cases_avoided"]].copy()
            tbl.columns = ["Phân khúc", "Quy mô ước tính", "Nguy cơ nền", "Giảm nguy cơ tuyệt đối/người",
                           "Ca tránh được / 1.000 USD", "Độ phủ", "Chi tiêu (USD)", "Ca tránh được"]
            st.dataframe(tbl, width="stretch", hide_index=True, column_config={
                "Nguy cơ nền": st.column_config.NumberColumn(format="percent"),
                "Giảm nguy cơ tuyệt đối/người": st.column_config.NumberColumn(format="percent"),
                "Độ phủ": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
                "Quy mô ước tính": st.column_config.NumberColumn(format="%d"),
                "Chi tiêu (USD)": st.column_config.NumberColumn(format="%d"),
                "Ca tránh được": st.column_config.NumberColumn(format="%.0f"),
                "Ca tránh được / 1.000 USD": st.column_config.NumberColumn(format="%.2f"),
            })
            st.caption("Giả định: chi phí tính cho mọi người trong nhóm được phủ (chưa sàng lọc trước); các nhóm có < 30 người trong mẫu bị loại.")

    # ------------------------------------------------------------ cảnh báo
    with t4:
        c = st.columns(4)
        dim_names = {"race_group": "Nhóm chủng tộc", "age_group": "Nhóm tuổi", "sex": "Giới tính",
                     "income_band": "Thu nhập", "weight_status": "Cân nặng", "education_level": "Mức học vấn"}
        dim = c[0].selectbox("Nhóm theo", list(dim_names), format_func=dim_names.get)
        ind = c[1].selectbox("Chỉ số", list(engine.INDICATORS))
        cycles = [v for v in olap.distinct_values("cycle_label") if v in ("2011-2012", "2013-2014", "2015-2016", "2017-2018")]
        base = c[2].selectbox("Chu kỳ gốc", cycles, index=0)
        late = c[3].selectbox("Chu kỳ mới", cycles, index=len(cycles) - 1)
        if base == late:
            st.info("Chọn hai chu kỳ khác nhau.")
        else:
            al = engine.trend_alerts(dim, ind, base, late)
            if al.empty:
                st.info("Không đủ cỡ mẫu.")
            else:
                n_up = int((al.alert == "Rising").sum())
                st.markdown(f"**{n_up} nhóm** tăng có ý nghĩa thống kê (|z| ≥ 1.96) cho chỉ số *{ind}*.")
                fig = go.Figure(go.Bar(
                    x=al["change_pp"], y=al[dim].astype(str), orientation="h",
                    marker_color=[SERIES[1] if a == "Rising" else SERIES[2] if a == "Falling" else "#9a9a95" for a in al["alert"]],
                    customdata=al[["rate_base", "rate_latest", "z", "alert"]],
                    hovertemplate="%{y}<br>%{customdata[0]:.1f}% → %{customdata[1]:.1f}%<br>z=%{customdata[2]:.2f} (%{customdata[3]})<extra></extra>"))
                fig.update_layout(xaxis_title="Thay đổi (điểm phần trăm)", yaxis=dict(autorange="reversed"))
                chart(fig, height=max(260, 40 * len(al) + 80), legend=False)
                shown = al.rename(columns={dim: dim_names[dim], "n_base": f"n ({base})", "rate_base": f"Tỷ lệ % ({base})",
                                           "n_latest": f"n ({late})", "rate_latest": f"Tỷ lệ % ({late})",
                                           "change_pp": "Thay đổi (điểm %)", "z": "z", "alert": "Cảnh báo"})
                st.dataframe(shown.round(2), width="stretch", hide_index=True)
                st.caption("Cam = tăng, xanh = giảm, xám = ổn định. Kiểm định z hai tỷ lệ độc lập, chưa hiệu chỉnh thiết kế mẫu phức hợp "
                           "của NHANES nên khoảng tin cậy thực tế rộng hơn.")

    # ------------------------------------------------------------- mô hình
    with t5:
        m = bundle["metrics"]
        kpi_row([("Mẫu huấn luyện/kiểm tra", f"{m['n_train']:,} / {m['n_test']:,}", None),
                 ("AUC (logistic)", f"{m['auc_logit']:.3f}", "Trên tập kiểm tra 25%"),
                 ("AUC (gradient boosting)", f"{m['auc_gbm']:.3f}", "Chỉ để đối chiếu"),
                 ("Brier (mô hình / nền)", f"{m['brier_logit']:.4f} / {m['brier_baseline']:.4f}", "Thấp hơn là tốt hơn")])
        cal = m["calibration"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 0.5], y=[0, 0.5], mode="lines", name="Hiệu chuẩn hoàn hảo",
                                 line=dict(color="#9a9a95", dash="dash", width=1.5)))
        fig.add_trace(go.Scatter(x=cal["mean_pred"], y=cal["frac_pos"], mode="lines+markers", name="Mô hình",
                                 line=dict(color=SERIES[0], width=2), marker=dict(size=8)))
        fig.update_layout(xaxis_title="Xác suất dự báo", yaxis_title="Tỷ lệ mắc thực tế")
        chart(fig, height=320)
        st.markdown(
            f"- **Đặc trưng được dùng:** {', '.join(risk_model.FEATURE_LABELS[f] for f in bundle['features'])}.\n"
            f"- **Vì sao loại cholesterol toàn phần và huyết áp tâm trương?** Khi thêm vào (AUC {m['auc_full7']:.3f}), "
            f"hệ số cholesterol là {m['coef_full7']['total_chol']:+.2f} (âm - ngược y học) do người bệnh đang dùng statin/thuốc hạ áp; "
            "bảng dữ liệu hiện có không có thông tin thuốc để hiệu chỉnh nên giữ mô hình đơn giản, đúng dấu.\n"
            "- **Biến mục tiêu** là bệnh tim mạch *tự khai báo đã từng mắc* (cắt ngang) nên đây là mô hình *tỷ lệ hiện mắc*, không phải dự báo biến cố tương lai.")
