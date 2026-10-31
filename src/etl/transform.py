"""TRANSFORM: làm sạch, tích hợp 2 nguồn, tính measure/cờ và sinh khóa dimension."""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src import config
from src.etl import dimensions as D


@dataclass
class TransformResult:
    dims: dict[str, pd.DataFrame]
    fact_health_exam: pd.DataFrame
    fact_nutrition: pd.DataFrame
    log: list[tuple] = field(default_factory=list)  # (step, detail, rows_in, rows_out)


def _log(res_log, step, detail, rows_in, rows_out):
    res_log.append((step, detail, int(rows_in), int(rows_out)))


def _yes_no(s: pd.Series) -> pd.Series:
    """Mã NHANES: 1=Yes, 2=No, 7/9/NaN -> thiếu."""
    return s.map({1: 1.0, 2: 0.0})


def _clip_invalid(df: pd.DataFrame, log: list) -> pd.DataFrame:
    """Giá trị ngoài khoảng hợp lệ -> NULL (ghi log số giá trị bị loại theo nguồn)."""
    for col, (lo, hi) in config.VALID_RANGES.items():
        bad = df[col].notna() & ~df[col].between(lo, hi)
        for src in df.loc[bad, "source_system"].unique():
            n = int((bad & (df["source_system"] == src)).sum())
            _log(log, "clean_outlier", f"{src}.{col} ngoài [{lo},{hi}] -> NULL", n, 0)
        df.loc[bad, col] = np.nan
    return df


# --------------------------------------------------------------- SOURCE A
def _transform_xpt(raw: dict[str, pd.DataFrame], log: list) -> pd.DataFrame:
    demo = raw["DEMO"][["SEQN", "cycle_code", "RIAGENDR", "RIDAGEYR", "RIDRETH1",
                        "DMDEDUC2", "INDFMPIR", "WTMEC2YR"]].copy()
    n0 = len(demo)
    demo = demo[demo["RIDAGEYR"] >= config.ADULT_MIN_AGE]
    _log(log, "filter", "XPT: chỉ giữ người >= 20 tuổi (có bộ câu hỏi bệnh tim mạch)", n0, len(demo))

    bpx = raw["BPX"]
    sy = bpx[[f"BPXSY{i}" for i in range(1, 5)]].where(lambda x: x > 0)
    di = bpx[[f"BPXDI{i}" for i in range(1, 5)]].where(lambda x: x > 0)  # DBP=0 là mã lỗi đo

    def cdc_mean(r: pd.DataFrame) -> pd.Series:
        """Quy ước CDC: trung bình các lần đo 2-4; nếu chỉ có lần 1 thì dùng lần 1 (lần đầu thường cao hơn)."""
        later = r.iloc[:, 1:].mean(axis=1)
        return later.fillna(r.iloc[:, 0])

    bp = pd.DataFrame({"SEQN": bpx["SEQN"], "sbp": cdc_mean(sy), "dbp": cdc_mean(di),
                       "pulse": bpx["BPXPLS"]})
    bmx = raw["BMX"][["SEQN", "BMXBMI", "BMXWAIST", "BMXWT", "BMXHT"]].rename(
        columns={"BMXBMI": "bmi", "BMXWAIST": "waist_cm", "BMXWT": "weight_kg", "BMXHT": "height_cm"})
    hdl = raw["HDL"][["SEQN", "LBDHDD"]].rename(columns={"LBDHDD": "hdl_chol"})
    tch = raw["TCHOL"][["SEQN", "LBXTC"]].rename(columns={"LBXTC": "total_chol"})
    mcq = raw["MCQ"][["SEQN", "MCQ160B", "MCQ160C", "MCQ160D", "MCQ160E", "MCQ160F"]].copy()
    for src, dst in zip(["MCQ160B", "MCQ160C", "MCQ160D", "MCQ160E", "MCQ160F"], D.CVD_FLAGS):
        mcq[dst] = _yes_no(mcq[src])
    mcq = mcq.drop(columns=["MCQ160B", "MCQ160C", "MCQ160D", "MCQ160E", "MCQ160F"])

    df = demo
    n_demo = len(df)
    for part in (bp, bmx, hdl, tch, mcq):
        df = df.merge(part.drop_duplicates("SEQN"), on="SEQN", how="left")
    # chỉ giữ người thực sự được khám (có dữ liệu huyết áp hoặc nhân trắc)
    examined = df[["sbp", "bmi"]].notna().any(axis=1)
    _log(log, "filter", "XPT: bỏ người không được khám MEC (thiếu cả BP và BMI)", n_demo, int(examined.sum()))
    df = df[examined].copy()

    df = df.rename(columns={"RIAGENDR": "sex_code", "RIDAGEYR": "age_years", "RIDRETH1": "race_code",
                            "DMDEDUC2": "edu_code", "INDFMPIR": "income_ratio", "WTMEC2YR": "mec_weight"})
    df["crp_mgl"] = np.nan
    cycle_key = {c: i for i, c in enumerate(config.NHANES_CYCLES, start=1)}
    df["cycle_key"] = df["cycle_code"].map(cycle_key)
    df["sex_key"] = df["sex_code"].map({1: 1, 2: 2}).fillna(0).astype(int)
    df["race_key"] = df["race_code"].where(df["race_code"].isin([1, 2, 3, 4, 5]), 0).astype(int)
    df["education_key"] = df["edu_code"].where(df["edu_code"].isin([1, 2, 3, 4, 5]), 0).astype(int)
    df["source_system"] = "NHANES_XPT"
    return df.drop(columns=["cycle_code", "sex_code", "race_code", "edu_code"])


# --------------------------------------------------------------- SOURCE B
NUTRIENT_MAP = {
    "Protein": "protein_g", "Carbohydrates": "carbohydrate_g", "Sugars": "sugar_g",
    "Fiber": "fiber_g", "Saturated_Fat": "saturated_fat_g", "Monounsaturated_Fat": "monounsat_fat_g",
    "Polyunsaturated_Fat": "polyunsat_fat_g", "Cholesterol": "dietary_chol_mg",
    "Sodium": "sodium_mg", "Potassium": "potassium_mg", "Calcium": "calcium_mg",
    "Magnesium": "magnesium_mg", "Vitamin_D": "vitamin_d_mcg",
}


def _transform_csv(raw: pd.DataFrame, log: list) -> pd.DataFrame:
    n0 = len(raw)
    df = raw.rename(columns={
        "SEQN": "SEQN", "Age": "age_years", "BMI": "bmi", "Waist_circ": "waist_cm",
        "Systolic_BP": "sbp", "Diastolic_BP": "dbp", "Total_Colesterol": "total_chol",
        "C_Reactive": "crp_mgl", "Congestive": "chf", "Coronary": "chd", "Angina": "angina",
        "Heart_attack": "heart_attack", "Stroke": "stroke", **NUTRIENT_MAP}).copy()
    adult = df["age_years"] >= config.ADULT_MIN_AGE
    has_outcome = df[D.CVD_FLAGS].notna().any(axis=1)
    _log(log, "filter", "CSV: chỉ giữ người >= 20 tuổi và có ít nhất 1 câu trả lời về bệnh tim mạch",
         n0, int((adult & has_outcome).sum()))
    df = df[adult & has_outcome].copy()
    for c in D.CVD_FLAGS:
        df[c] = _yes_no(df[c])
    df["cycle_key"] = np.where(df["SEQN"] <= config.CVD_PREPANDEMIC_MAX_SEQN, 5, 6)
    df["sex_key"] = 0
    df["race_key"] = 0
    df["education_key"] = 0
    df["income_ratio"] = np.nan
    df["mec_weight"] = np.nan
    df["pulse"] = np.nan
    df["weight_kg"] = np.nan
    df["height_cm"] = np.nan
    df["hdl_chol"] = np.nan
    df["source_system"] = "NHANES_CVD_CSV"
    return df


# ------------------------------------------------------------ DERIVATIONS
def _derive_and_key(df: pd.DataFrame, log: list) -> pd.DataFrame:
    """Làm sạch outlier, tính measure/cờ và sinh khóa dimension dùng chung."""
    df = _clip_invalid(df, log)

    df["non_hdl_chol"] = df["total_chol"] - df["hdl_chol"]
    df["age_group_key"] = D.age_group_key(df["age_years"])
    df["bmi_category_key"] = D.bmi_category_key(df["bmi"])
    df["bp_category_key"] = D.bp_category_key(df["sbp"], df["dbp"])
    df["chol_category_key"] = D.chol_category_key(df["total_chol"])
    df["income_key"] = D.income_key(df["income_ratio"])
    df["cvd_profile_key"] = D.cvd_profile_key(df[D.CVD_FLAGS])

    f = df[D.CVD_FLAGS]
    has_cvd = pd.Series(np.nan, index=df.index)
    has_cvd[(f == 1).any(axis=1)] = 1
    has_cvd[(f == 0).all(axis=1)] = 0
    df["has_cvd"] = has_cvd
    bp_known = df["bp_category_key"] > 0
    df["is_hypertensive"] = np.where(bp_known, df["bp_category_key"].isin([3, 4]).astype(float), np.nan)
    df["is_obese"] = np.where(df["bmi"].notna(), (df["bmi"] >= 30).astype(float), np.nan)
    df["is_high_chol"] = np.where(df["total_chol"].notna(), (df["total_chol"] >= 240).astype(float), np.nan)
    low_cut = np.where(df["sex_key"] == 2, 50, 40)
    df["is_low_hdl"] = np.where(df["hdl_chol"].notna(), (df["hdl_chol"] < low_cut).astype(float), np.nan)
    return df


FACT_HEALTH_COLS = [
    "exam_id", "cycle_key", "sex_key", "race_key", "education_key", "income_key", "age_group_key",
    "bmi_category_key", "bp_category_key", "chol_category_key", "cvd_profile_key",
    "age_years", "sbp", "dbp", "pulse", "bmi", "waist_cm", "weight_kg", "height_cm", "total_chol",
    "hdl_chol", "non_hdl_chol", "crp_mgl", "income_ratio", "mec_weight",
    "has_cvd", "is_hypertensive", "is_obese", "is_high_chol", "is_low_hdl",
]
FLAG_COLS = ["has_cvd", "is_hypertensive", "is_obese", "is_high_chol", "is_low_hdl"]


def _build_fact_nutrition(csv_df: pd.DataFrame, log: list) -> pd.DataFrame:
    n0 = len(csv_df)
    df = csv_df[csv_df["protein_g"].notna() & csv_df["sodium_mg"].notna()].copy()
    _log(log, "filter", "Nutrition: giữ người có dữ liệu dinh dưỡng 24h (Protein & Sodium)", n0, len(df))
    # giá trị âm / cực đoan -> NULL
    for c in NUTRIENT_MAP.values():
        df.loc[df[c] < 0, c] = np.nan
    for c in ("sodium_mg", "potassium_mg"):  # 0 mg/ngày là không khả thi -> thiếu dữ liệu
        df.loc[df[c] <= 0, c] = np.nan
    df["na_k_ratio"] = df["sodium_mg"] / df["potassium_mg"].replace(0, np.nan)
    df["high_sodium"] = np.where(df["sodium_mg"].notna(), (df["sodium_mg"] >= 2300).astype(float), np.nan)
    df["low_fiber"] = np.where(df["fiber_g"].notna(), (df["fiber_g"] < 25).astype(float), np.nan)
    df["exam_id"] = df["SEQN"]
    cols = ["exam_id", "cycle_key", "age_group_key", "bmi_category_key", "bp_category_key",
            "cvd_profile_key", *NUTRIENT_MAP.values(), "na_k_ratio", "high_sodium", "low_fiber"]
    return df[cols].reset_index(drop=True)


def transform(raw_xpt: dict[str, pd.DataFrame], raw_csv: pd.DataFrame) -> TransformResult:
    log: list = []
    a = _transform_xpt(raw_xpt, log)
    b = _transform_csv(raw_csv, log)

    common = ["SEQN", "cycle_key", "sex_key", "race_key", "education_key", "income_ratio", "mec_weight",
              "age_years", "sbp", "dbp", "pulse", "bmi", "waist_cm", "weight_kg", "height_cm",
              "total_chol", "hdl_chol", "crp_mgl", "source_system", *D.CVD_FLAGS]
    nut_cols = [c for c in NUTRIENT_MAP.values()]
    all_df = pd.concat([a[common], b[common + nut_cols]], ignore_index=True)
    n_before = len(all_df)
    all_df = all_df.drop_duplicates("SEQN")
    _log(log, "dedupe", "Loại SEQN trùng giữa 2 nguồn", n_before, len(all_df))
    all_df = _derive_and_key(all_df, log)
    all_df["exam_id"] = all_df["SEQN"]

    fact = all_df[FACT_HEALTH_COLS].copy()
    for c in FLAG_COLS:
        fact[c] = fact[c].astype("Int8")
    nutrition = _build_fact_nutrition(all_df[all_df["source_system"] == "NHANES_CVD_CSV"], log)
    for c in ["high_sodium", "low_fiber"]:
        nutrition[c] = nutrition[c].astype("Int8")

    dims = {
        "dim_cycle": D.build_dim_cycle(), "dim_sex": D.build_dim_sex(), "dim_race": D.build_dim_race(),
        "dim_education": D.build_dim_education(), "dim_income": D.build_dim_income(),
        "dim_age_group": D.build_dim_age_group(), "dim_bmi_category": D.build_dim_bmi_category(),
        "dim_bp_category": D.build_dim_bp_category(), "dim_chol_category": D.build_dim_chol_category(),
        "dim_cvd_profile": D.build_dim_cvd_profile(),
    }
    return TransformResult(dims=dims, fact_health_exam=fact, fact_nutrition=nutrition, log=log)
