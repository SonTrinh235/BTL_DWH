"""Hệ hỗ trợ quyết định (DSS) xây trên kho dữ liệu.

Ba thành phần:
  1. assess_individual   - đánh giá nguy cơ cá nhân + khuyến nghị theo luật (rule-based)
  2. simulate_intervention / allocate_budget - mô phỏng what-if và tối ưu phân bổ ngân sách sàng lọc
  3. trend_alerts        - cảnh báo sớm khi tỷ lệ bệnh/yếu tố nguy cơ của một nhóm tăng có ý nghĩa thống kê

Nguyên tắc mô hình hoá (xem báo cáo, mục Hạn chế):
  * Nguy cơ nền (baseline) của từng người = xác suất từ mô hình logistic huấn luyện trên DW.
  * Hiệu quả can thiệp = nguy cơ tương đối (RR) từ y văn - KHÔNG suy ra từ dữ liệu cắt ngang,
    vì dữ liệu này nhiễu bởi việc người bệnh đang dùng thuốc.
  * Kết quả mang tính hỗ trợ ra quyết định, không thay thế phán đoán lâm sàng.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import olap
from src.dss import risk_model

# ----------------------------------------------------------------------------------------
# Tham số hiệu quả can thiệp (có thể chỉnh trên giao diện)
# ----------------------------------------------------------------------------------------
@dataclass
class EffectSizes:
    rr_per_10mmhg_sbp: float = 0.80     # Ettehad et al., Lancet 2016: giảm 10 mmHg SBP -> RR 0.80 biến cố CVD
    rr_per_39mgdl_tc: float = 0.78      # CTT Collaboration, Lancet 2010: giảm 1 mmol/L (~39 mg/dL) LDL -> RR 0.78
    rr_per_1bmi: float = 0.953          # giả định minh hoạ (~HR 1.27 / 5 đơn vị BMI), cùng bậc với các phân tích gộp như ERFC 2011; cần đối chiếu số gốc
    realization: float = 1.0            # Tỷ lệ hiệu quả đạt được ngoài thực tế (tuân thủ điều trị...)


SBP_FLOOR, BMI_FLOOR, TC_FLOOR = 120.0, 24.9, 199.0  # không giảm quá mức mục tiêu


def risk_ratio(delta_sbp: np.ndarray, delta_tc: np.ndarray, delta_bmi: np.ndarray, fx: EffectSizes) -> np.ndarray:
    """RR gộp (nhân) từ các mức giảm đạt được; giá trị < 1 = giảm nguy cơ. Có tính hệ số thực tế."""
    rr = (fx.rr_per_10mmhg_sbp ** (delta_sbp / 10.0)
          * fx.rr_per_39mgdl_tc ** (delta_tc / 38.7)
          * fx.rr_per_1bmi ** delta_bmi)
    return 1.0 - fx.realization * (1.0 - rr)


def achievable_reduction(values: pd.Series, wanted: float, floor: float) -> np.ndarray:
    """Mức giảm thực tế = min(mức mong muốn, khoảng cách tới ngưỡng mục tiêu); người dưới ngưỡng = 0."""
    v = values.to_numpy(dtype=float)
    return np.where(np.isnan(v), 0.0, np.clip(np.minimum(wanted, v - floor), 0, None))


# ----------------------------------------------------------------------------------------
# 1. Đánh giá cá nhân
# ----------------------------------------------------------------------------------------
def risk_band(p: float) -> str:
    # Ngưỡng tương đối so với tỷ lệ hiện mắc ~11% trong quần thể
    return "Low" if p < 0.05 else "Moderate" if p < 0.12 else "High" if p < 0.25 else "Very high"


def assess_individual(age: float, male: bool, sbp: float, dbp: float, bmi: float,
                      total_chol: float, hdl: float, bundle: dict | None = None) -> dict:
    bundle = bundle or risk_model.load_bundle()
    row = pd.DataFrame([{"age_years": age, "male": int(male), "sbp": sbp, "bmi": bmi, "hdl_chol": hdl,
                         "dbp": dbp, "total_chol": total_chol}])
    p = float(risk_model.predict(bundle, row)[0])

    # So sánh với nhóm cùng độ tuổi & giới (tỷ lệ hiện mắc trong DW)
    peers = olap.sql("""SELECT avg(has_cvd) AS r, count(*) AS n FROM olap_exam
                        WHERE source_system='NHANES_XPT' AND has_cvd IS NOT NULL AND sex = ?
                          AND age_years BETWEEN ? AND ?""",
                     ["Male" if male else "Female", age - 5, age + 5]).iloc[0]

    # Đóng góp từng yếu tố vào logit (so với trung bình quần thể)
    coefs = bundle["model"].named_steps["clf"].coef_[0]
    means, stds = bundle["feature_means"], bundle["feature_stds"]
    contrib = {risk_model.FEATURE_LABELS[f]: float(c * (row[f].iloc[0] - means[f]) / stds[f])
               for f, c in zip(bundle["features"], coefs)}

    # Kịch bản "đạt toàn bộ mục tiêu điều trị"
    fx = EffectSizes()
    d_sbp = float(max(sbp - SBP_FLOOR, 0)) if sbp > 130 else 0.0
    d_tc = float(max(total_chol - TC_FLOOR, 0)) if total_chol >= 200 else 0.0
    d_bmi = float(max(bmi - BMI_FLOOR, 0)) if bmi >= 25 else 0.0
    rr = float(risk_ratio(np.array([d_sbp]), np.array([d_tc]), np.array([d_bmi]), fx)[0])

    return {
        "probability": p, "band": risk_band(p),
        "peer_rate": float(peers["r"]) if peers["n"] else float("nan"), "peer_n": int(peers["n"]),
        "contributions": contrib, "p_if_targets_met": p * rr, "rr_if_targets_met": rr,
        "advice": recommendations(age, male, sbp, dbp, bmi, total_chol, hdl),
    }


def recommendations(age, male, sbp, dbp, bmi, total_chol, hdl) -> list[tuple[str, str]]:
    """Luật khuyến nghị dựa trên hướng dẫn ACC/AHA 2017 (HA) và ATP III (lipid), WHO (BMI).
    Trả về list (mức độ, nội dung): mức độ in {'urgent','action','watch','ok'}."""
    out = []
    if sbp >= 180 or dbp >= 120:
        out.append(("urgent", "Huyết áp ở mức nguy kịch (>=180/120): cần đánh giá y tế ngay."))
    elif sbp >= 140 or dbp >= 90:
        out.append(("action", "Tăng huyết áp độ 2 (>=140/90): nên khám và cân nhắc điều trị thuốc + thay đổi lối sống."))
    elif sbp >= 130 or dbp >= 80:
        out.append(("action", "Tăng huyết áp độ 1 (130-139/80-89): thay đổi lối sống (giảm muối, vận động); theo dõi tại nhà."))
    elif sbp >= 120:
        out.append(("watch", "Huyết áp tăng nhẹ (120-129/<80): giảm muối, duy trì cân nặng, đo lại định kỳ."))
    else:
        out.append(("ok", "Huyết áp bình thường."))

    if total_chol >= 240:
        out.append(("action", "Cholesterol toàn phần cao (>=240 mg/dL): xét nghiệm đủ bộ lipid, tư vấn chế độ ăn / statin."))
    elif total_chol >= 200:
        out.append(("watch", "Cholesterol ở ngưỡng biên (200-239): hạn chế chất béo bão hoà, kiểm tra lại sau 3-6 tháng."))
    else:
        out.append(("ok", "Cholesterol toàn phần trong giới hạn mong muốn."))

    hdl_cut = 40 if male else 50
    if hdl < hdl_cut:
        out.append(("watch", f"HDL thấp (<{hdl_cut} mg/dL): tăng hoạt động thể lực, bỏ thuốc lá, hạn chế đường tinh luyện."))

    if bmi >= 35:
        out.append(("action", "Béo phì độ II-III (BMI>=35): nên có chương trình giảm cân có giám sát."))
    elif bmi >= 30:
        out.append(("action", "Béo phì độ I (BMI 30-34.9): mục tiêu giảm 5-10% cân nặng."))
    elif bmi >= 25:
        out.append(("watch", "Thừa cân (BMI 25-29.9): điều chỉnh khẩu phần và vận động."))
    elif bmi < 18.5:
        out.append(("watch", "Thiếu cân (BMI<18.5): nên được tư vấn dinh dưỡng."))
    else:
        out.append(("ok", "BMI trong khoảng bình thường."))

    if age >= 65:
        out.append(("watch", "Nhóm >=65 tuổi: tuổi là yếu tố nguy cơ mạnh nhất - nên khám tim mạch tổng quát hằng năm."))
    return out


# ----------------------------------------------------------------------------------------
# 2. What-if và phân bổ ngân sách
# ----------------------------------------------------------------------------------------
def _population_frame(filters: dict | None = None, bundle: dict | None = None) -> pd.DataFrame:
    """Quần thể mẫu từ DW (kèm xác suất nền); các giá trị thiếu được điền trung vị trước khi dự báo."""
    bundle = bundle or risk_model.load_bundle()
    df = risk_model.load_modeling_frame()
    for col, vals in (filters or {}).items():
        if vals:
            df = df[df[col].isin(vals)]
    if df.empty:
        return df
    df = df.copy()
    df["p0"] = risk_model.predict(bundle, df)
    return df


def simulate_intervention(wanted_sbp: float, wanted_tc: float, wanted_bmi: float,
                          filters: dict | None = None, fx: EffectSizes | None = None,
                          bundle: dict | None = None) -> dict:
    """What-if: nếu cả nhóm lọc `filters` đạt mức giảm mong muốn (bị chặn ở ngưỡng mục tiêu)
    thì nguy cơ trung bình & số ca CVD kỳ vọng giảm bao nhiêu / 1.000 người."""
    fx = fx or EffectSizes()
    df = _population_frame(filters, bundle)
    if df.empty:
        return {"n": 0}
    d_sbp = achievable_reduction(df["sbp"], wanted_sbp, SBP_FLOOR)
    d_tc = achievable_reduction(df["total_chol"], wanted_tc, TC_FLOOR)
    d_bmi = achievable_reduction(df["bmi"], wanted_bmi, BMI_FLOOR)
    rr = risk_ratio(d_sbp, d_tc, d_bmi, fx)
    p1 = df["p0"].to_numpy() * rr
    base, after = float(df["p0"].mean()), float(p1.mean())
    return {
        "n": int(len(df)), "baseline_risk": base, "after_risk": after,
        "abs_reduction": base - after, "rel_reduction": 1 - after / base if base else 0.0,
        "cases_avoided_per_1000": (base - after) * 1000,
        "share_affected": float(np.mean((d_sbp + d_tc + d_bmi) > 0)),
        "by_age": (pd.DataFrame({"age_group": df["age_group"], "before": df["p0"], "after": p1})
                   .groupby("age_group", sort=True).mean().reset_index()),
    }


SEGMENT_DIMS = {"Age group": "age_group", "Sex": "sex", "Race group": "race_group",
                "Blood pressure group": "bp_group", "Weight status": "weight_status",
                "Income band": "income_band"}


def allocate_budget(budget: float, cost_per_person: float, population: int,
                    segment_by: list[str], wanted_sbp: float, wanted_tc: float, wanted_bmi: float,
                    fx: EffectSizes | None = None, bundle: dict | None = None,
                    min_sample: int = 30) -> dict:
    """Chọn nhóm ưu tiên can thiệp để tối đa hoá số ca CVD tránh được dưới ràng buộc ngân sách.

    Bài toán knapsack liên tục (mỗi nhóm có thể phủ một phần): lợi ích/chi phí của nhóm i là
    ARR_i / cost (giảm nguy cơ tuyệt đối trên mỗi người được can thiệp). Sắp giảm dần rồi lấp đầy
    ngân sách (tham lam - tối ưu cho knapsack phân số). So sánh với phân bổ đều theo quy mô nhóm.
    Chi phí được áp cho mọi người trong nhóm được phủ, kể cả người ít hưởng lợi (vì chưa biết trước).
    """
    fx = fx or EffectSizes()
    df = _population_frame(None, bundle)
    cols = [SEGMENT_DIMS[s] for s in segment_by]
    d_sbp = achievable_reduction(df["sbp"], wanted_sbp, SBP_FLOOR)
    d_tc = achievable_reduction(df["total_chol"], wanted_tc, TC_FLOOR)
    d_bmi = achievable_reduction(df["bmi"], wanted_bmi, BMI_FLOOR)
    df = df.assign(p1=df["p0"] * risk_ratio(d_sbp, d_tc, d_bmi, fx))
    df["arr"] = df["p0"] - df["p1"]

    seg = (df.groupby(cols, observed=True)
             .agg(sample=("p0", "size"), baseline_risk=("p0", "mean"), arr=("arr", "mean"))
             .reset_index())
    seg = seg[seg["sample"] >= min_sample].copy()
    seg["segment"] = seg[cols].astype(str).agg(" | ".join, axis=1)
    seg["size"] = (seg["sample"] / seg["sample"].sum() * population).round().astype(int)
    seg["cases_avoided_if_full"] = seg["size"] * seg["arr"]
    seg["cost_if_full"] = seg["size"] * cost_per_person
    seg["efficiency"] = seg["arr"] / cost_per_person * 1000  # ca tránh được / 1.000 USD
    seg = seg.sort_values("efficiency", ascending=False).reset_index(drop=True)

    # --- Tham lam theo hiệu quả
    remaining, cover = budget, []
    for _, r in seg.iterrows():
        spend = min(r["cost_if_full"], max(remaining, 0.0))
        cover.append(spend / r["cost_if_full"] if r["cost_if_full"] else 0.0)
        remaining -= spend
    seg["coverage"] = cover
    seg["spend"] = seg["coverage"] * seg["cost_if_full"]
    seg["cases_avoided"] = seg["coverage"] * seg["cases_avoided_if_full"]

    # --- Đối chứng: phân bổ đều theo quy mô (mọi nhóm cùng độ phủ)
    uniform_cov = min(1.0, budget / seg["cost_if_full"].sum())
    uniform_avoided = float((uniform_cov * seg["cases_avoided_if_full"]).sum())
    return {
        "segments": seg,
        "optimized_avoided": float(seg["cases_avoided"].sum()),
        "uniform_avoided": uniform_avoided,
        "budget_used": float(seg["spend"].sum()),
        "people_covered": float((seg["coverage"] * seg["size"]).sum()),
        "uniform_coverage": uniform_cov,
        "total_cost_full": float(seg["cost_if_full"].sum()),
    }


# ----------------------------------------------------------------------------------------
# 3. Cảnh báo xu hướng
# ----------------------------------------------------------------------------------------
INDICATORS = {"CVD prevalence": "has_cvd", "Hypertension": "is_hypertensive", "Obesity": "is_obese",
              "High cholesterol": "is_high_chol"}


def trend_alerts(dim: str, indicator: str, base_cycle: str = "2011-2012", latest_cycle: str = "2017-2018",
                 z_crit: float = 1.96, min_n: int = 100) -> pd.DataFrame:
    """So sánh tỷ lệ chỉ báo giữa 2 chu kỳ cho từng nhóm của `dim`, kiểm định z hai tỷ lệ.
    Alert: 'Rising' / 'Falling' nếu |z| >= z_crit, ngược lại 'Stable'."""
    col = INDICATORS[indicator]
    olap._check_dims([dim])
    df = olap.sql(f"""
        SELECT {dim} AS grp, cycle_label, avg({col}) AS rate, count({col}) AS n
        FROM olap_exam WHERE cycle_label IN (?, ?) AND {col} IS NOT NULL
        GROUP BY grp, cycle_label""", [base_cycle, latest_cycle])
    b = df[df.cycle_label == base_cycle].set_index("grp")
    l = df[df.cycle_label == latest_cycle].set_index("grp")
    j = b.join(l, lsuffix="_base", rsuffix="_latest", how="inner")
    j = j[(j.n_base >= min_n) & (j.n_latest >= min_n)]
    j["change_pp"] = (j.rate_latest - j.rate_base) * 100
    j["z"] = [olap.two_proportion_z(r.rate_latest, int(r.n_latest), r.rate_base, int(r.n_base))
              for r in j.itertuples()]
    j["alert"] = np.where(j.z >= z_crit, "Rising", np.where(j.z <= -z_crit, "Falling", "Stable"))
    j["rate_base"] *= 100
    j["rate_latest"] *= 100
    return (j.reset_index().rename(columns={"grp": dim})
             .sort_values("z", ascending=False)[[dim, "n_base", "rate_base", "n_latest", "rate_latest",
                                                  "change_pp", "z", "alert"]]
             .reset_index(drop=True))
