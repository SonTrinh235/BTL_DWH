"""Định nghĩa các dimension (bảng chiều) và hàm phân lớp giá trị -> khóa."""
import itertools

import pandas as pd

from src import config

UNKNOWN = "Unknown"


# --------------------------------------------------------------- dim_cycle
def build_dim_cycle() -> pd.DataFrame:
    rows = []
    for i, (_, (label, y0, y1)) in enumerate(config.NHANES_CYCLES.items(), start=1):
        rows.append((i, label, y0, y1, "2011-2018 (XPT)", "NHANES_XPT"))
    n = len(rows)
    rows.append((n + 1, "2017-Mar 2020", 2017, 2020, "2017-2023 (CSV)", "NHANES_CVD_CSV"))
    rows.append((n + 2, "2021-2023", 2021, 2023, "2017-2023 (CSV)", "NHANES_CVD_CSV"))
    return pd.DataFrame(rows, columns=["cycle_key", "cycle_label", "start_year", "end_year",
                                       "period_group", "source_system"])


# ----------------------------------------------------------------- dim_sex
def build_dim_sex() -> pd.DataFrame:
    return pd.DataFrame({"sex_key": [0, 1, 2], "sex": [UNKNOWN, "Male", "Female"]})


# ---------------------------------------------------------------- dim_race
RACE_ROWS = [
    (0, UNKNOWN, UNKNOWN),
    (1, "Mexican American", "Hispanic"),
    (2, "Other Hispanic", "Hispanic"),
    (3, "Non-Hispanic White", "Non-Hispanic"),
    (4, "Non-Hispanic Black", "Non-Hispanic"),
    (5, "Other / Multi-racial", "Non-Hispanic"),
]


def build_dim_race() -> pd.DataFrame:
    return pd.DataFrame(RACE_ROWS, columns=["race_key", "race", "race_group"])


# ----------------------------------------------------------- dim_education
EDU_ROWS = [
    (0, UNKNOWN, UNKNOWN),
    (1, "Less than 9th grade", "Low"),
    (2, "9-11th grade", "Low"),
    (3, "High school / GED", "Medium"),
    (4, "Some college / AA", "Medium"),
    (5, "College graduate or above", "High"),
]


def build_dim_education() -> pd.DataFrame:
    return pd.DataFrame(EDU_ROWS, columns=["education_key", "education", "education_level"])


# -------------------------------------------------------------- dim_income
INCOME_ROWS = [
    (0, UNKNOWN, 9),
    (1, "Below poverty (PIR<1)", 1),
    (2, "Low (PIR 1-1.99)", 2),
    (3, "Middle (PIR 2-3.99)", 3),
    (4, "High (PIR>=4)", 4),
]


def build_dim_income() -> pd.DataFrame:
    return pd.DataFrame(INCOME_ROWS, columns=["income_key", "income_band", "sort_order"])


def income_key(pir: pd.Series) -> pd.Series:
    k = pd.Series(0, index=pir.index)
    k[pir < 1] = 1
    k[(pir >= 1) & (pir < 2)] = 2
    k[(pir >= 2) & (pir < 4)] = 3
    k[pir >= 4] = 4
    return k.astype(int)


# ----------------------------------------------------------- dim_age_group
AGE_BINS = [(20, 29), (30, 39), (40, 49), (50, 59), (60, 69), (70, 79), (80, 120)]


def build_dim_age_group() -> pd.DataFrame:
    rows = [(0, UNKNOWN, UNKNOWN, None, None)]
    for i, (lo, hi) in enumerate(AGE_BINS, start=1):
        label = f"{lo}-{hi}" if hi < 100 else f"{lo}+"
        stage = "Young adult" if lo < 40 else ("Middle-aged" if lo < 60 else "Older adult")
        rows.append((i, label, stage, lo, min(hi, 100)))
    return pd.DataFrame(rows, columns=["age_group_key", "age_group", "life_stage", "min_age", "max_age"])


def age_group_key(age: pd.Series) -> pd.Series:
    k = pd.Series(0, index=age.index)
    for i, (lo, hi) in enumerate(AGE_BINS, start=1):
        k[(age >= lo) & (age < hi + 1)] = i
    return k.astype(int)


# ------------------------------------------------------- dim_bmi_category
BMI_ROWS = [
    (0, UNKNOWN, UNKNOWN, 9),
    (1, "Underweight (<18.5)", "Underweight", 1),
    (2, "Normal (18.5-24.9)", "Healthy", 2),
    (3, "Overweight (25-29.9)", "Excess weight", 3),
    (4, "Obese I (30-34.9)", "Excess weight", 4),
    (5, "Obese II (35-39.9)", "Excess weight", 5),
    (6, "Obese III (>=40)", "Excess weight", 6),
]


def build_dim_bmi_category() -> pd.DataFrame:
    return pd.DataFrame(BMI_ROWS, columns=["bmi_category_key", "bmi_category", "weight_status", "sort_order"])


def bmi_category_key(bmi: pd.Series) -> pd.Series:
    k = pd.Series(0, index=bmi.index)
    k[bmi < 18.5] = 1
    k[(bmi >= 18.5) & (bmi < 25)] = 2
    k[(bmi >= 25) & (bmi < 30)] = 3
    k[(bmi >= 30) & (bmi < 35)] = 4
    k[(bmi >= 35) & (bmi < 40)] = 5
    k[bmi >= 40] = 6
    return k.astype(int)


# -------------------------------------------------------- dim_bp_category
BP_ROWS = [
    (0, UNKNOWN, UNKNOWN, 9),
    (1, "Normal (<120/<80)", "Normotensive", 1),
    (2, "Elevated (120-129/<80)", "Normotensive", 2),
    (3, "Hypertension Stage 1 (130-139/80-89)", "Hypertensive", 3),
    (4, "Hypertension Stage 2 (>=140/>=90)", "Hypertensive", 4),
]


def build_dim_bp_category() -> pd.DataFrame:
    return pd.DataFrame(BP_ROWS, columns=["bp_category_key", "bp_category", "bp_group", "sort_order"])


def bp_category_key(sbp: pd.Series, dbp: pd.Series) -> pd.Series:
    """Phân loại theo ACC/AHA 2017; lấy mức cao nhất của SBP/DBP."""
    k = pd.Series(0, index=sbp.index)
    ok = sbp.notna() & dbp.notna()
    k[ok & (sbp < 120) & (dbp < 80)] = 1
    k[ok & (sbp >= 120) & (sbp < 130) & (dbp < 80)] = 2
    k[ok & ((sbp >= 130) | (dbp >= 80))] = 3
    k[ok & ((sbp >= 140) | (dbp >= 90))] = 4
    return k.astype(int)


# ------------------------------------------------------ dim_chol_category
CHOL_ROWS = [
    (0, UNKNOWN, 9),
    (1, "Desirable (<200)", 1),
    (2, "Borderline high (200-239)", 2),
    (3, "High (>=240)", 3),
]


def build_dim_chol_category() -> pd.DataFrame:
    return pd.DataFrame(CHOL_ROWS, columns=["chol_category_key", "chol_category", "sort_order"])


def chol_category_key(tc: pd.Series) -> pd.Series:
    k = pd.Series(0, index=tc.index)
    k[tc < 200] = 1
    k[(tc >= 200) & (tc < 240)] = 2
    k[tc >= 240] = 3
    return k.astype(int)


# ------------------------------------------------------- dim_cvd_profile
CVD_FLAGS = ["chf", "chd", "angina", "heart_attack", "stroke"]
CVD_LABELS = {"chf": "Heart failure", "chd": "Coronary disease", "angina": "Angina",
              "heart_attack": "Heart attack", "stroke": "Stroke"}


def _profile_index(flags) -> int:
    """Khóa = 1 + số nhị phân 5 bit (bit i = cờ i); 0 = Unknown."""
    return 1 + sum(int(f) << i for i, f in enumerate(flags))


def build_dim_cvd_profile() -> pd.DataFrame:
    rows = [(0, UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN, None, UNKNOWN, UNKNOWN)]
    for combo in itertools.product([0, 1], repeat=len(CVD_FLAGS)):
        names = [CVD_LABELS[n] for n, f in zip(CVD_FLAGS, combo) if f]
        n = sum(combo)
        label = " + ".join(names) if names else "No CVD"
        group = "No CVD" if n == 0 else ("Single condition" if n == 1 else "Multiple conditions")
        rows.append((_profile_index(combo), *["Yes" if f else "No" for f in combo], n, label, group))
    return (pd.DataFrame(rows, columns=["cvd_profile_key", *CVD_FLAGS, "n_conditions",
                                        "profile_label", "cvd_group"])
            .sort_values("cvd_profile_key").reset_index(drop=True))


def cvd_profile_key(flags: pd.DataFrame) -> pd.Series:
    """flags: 5 cột 0/1/NaN theo thứ tự CVD_FLAGS. Có cờ nào =1 -> xác định;
    tất cả =0 -> 'No CVD'; còn lại (thiếu mà không có cờ =1) -> Unknown."""
    f = flags[CVD_FLAGS]
    any_yes = (f == 1).any(axis=1)
    all_no = (f == 0).all(axis=1)
    bits = sum((f[c].fillna(0).astype(int) * (2 ** i)) for i, c in enumerate(CVD_FLAGS))
    key = pd.Series(0, index=f.index)
    known = any_yes | all_no
    key[known] = 1 + bits[known]
    return key.astype(int)
