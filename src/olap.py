"""Tầng OLAP trên MySQL: slice, dice, drill-down/roll-up, cube, pivot.

Mọi tên cột/measure được kiểm tra qua whitelist trước khi ghép vào SQL
(giá trị lọc luôn đi qua tham số `?`) nên không có nguy cơ SQL injection.
"""
import itertools

import pandas as pd

from src import db

# --- Dimension attribute (cột trong view olap_exam) -> cột khóa dùng để sắp xếp
DIMENSIONS = {
    "cycle_label": "cycle_key", "period_group": "cycle_key", "source_system": "cycle_key",
    "sex": "sex_key", "race": "race_key", "race_group": "race_key",
    "education": "education_key", "education_level": "education_key", "income_band": "income_key",
    "age_group": "age_group_key", "life_stage": "age_group_key",
    "bmi_category": "bmi_category_key", "weight_status": "bmi_category_key",
    "bp_category": "bp_category_key", "bp_group": "bp_category_key",
    "chol_category": "chol_category_key",
    "cvd_group": "n_conditions", "profile_label": "n_conditions",
}

# --- Phân cấp (hierarchy) phục vụ drill-down / roll-up: từ thô -> chi tiết
HIERARCHIES = {
    "Time": ["period_group", "cycle_label"],
    "Age": ["life_stage", "age_group"],
    "Race / Ethnicity": ["race_group", "race"],
    "Education": ["education_level", "education"],
    "Weight status": ["weight_status", "bmi_category"],
    "Blood pressure": ["bp_group", "bp_category"],
    "CVD": ["cvd_group", "profile_label"],
}

# --- Measure: tên -> (biểu thức SQL, định dạng)
MEASURES = {
    "People (n)": ("count(*)", "{:,.0f}"),
    "CVD prevalence (%)": ("round(avg(has_cvd) * 100, 2)", "{:.1f}"),
    "Hypertension prevalence (%)": ("round(avg(is_hypertensive) * 100, 2)", "{:.1f}"),
    "Obesity prevalence (%)": ("round(avg(is_obese) * 100, 2)", "{:.1f}"),
    "High cholesterol (%)": ("round(avg(is_high_chol) * 100, 2)", "{:.1f}"),
    "Low HDL (%)": ("round(avg(is_low_hdl) * 100, 2)", "{:.1f}"),
    "Avg systolic BP": ("round(avg(sbp), 2)", "{:.1f}"),
    "Avg diastolic BP": ("round(avg(dbp), 2)", "{:.1f}"),
    "Avg BMI": ("round(avg(bmi), 2)", "{:.1f}"),
    "Avg waist (cm)": ("round(avg(waist_cm), 2)", "{:.1f}"),
    "Avg total cholesterol": ("round(avg(total_chol), 2)", "{:.1f}"),
    "Avg HDL": ("round(avg(hdl_chol), 2)", "{:.1f}"),
    "Avg CRP (mg/L)": ("round(avg(crp_mgl), 2)", "{:.2f}"),
    "CVD cases (n)": ("sum(has_cvd)", "{:,.0f}"),
}

FILTERABLE = set(DIMENSIONS)


def sql(query: str, params: list | None = None) -> pd.DataFrame:
    """Chạy SQL tuỳ ý (phiên MySQL read-only) và trả DataFrame."""
    return db.query_df(query, params)


def distinct_values(dim: str) -> list[str]:
    """Các giá trị của 1 thuộc tính dimension, theo thứ tự tự nhiên (key)."""
    _check_dims([dim])
    df = sql(f"SELECT {dim} AS v, {_sort_expr(dim)} AS k FROM olap_exam GROUP BY {dim} ORDER BY k")
    return df["v"].tolist()


def _sort_expr(dim: str) -> str:
    """Biểu thức sắp xếp theo thứ tự tự nhiên của dimension; thành viên Unknown (key = 0) xếp cuối."""
    key = DIMENSIONS[dim]
    return f"min(CASE WHEN {key} = 0 THEN 999 ELSE {key} END)" if key.endswith("_key") else f"min({key})"


def _check_dims(dims):
    bad = [d for d in dims if d not in DIMENSIONS]
    if bad:
        raise ValueError(f"Dimension không hợp lệ: {bad}")


def _where(filters: dict[str, list] | None) -> tuple[str, list]:
    """Slice (1 giá trị) / Dice (nhiều giá trị) -> mệnh đề WHERE tham số hoá."""
    clauses, params = [], []
    for col, vals in (filters or {}).items():
        if not vals:
            continue
        _check_dims([col])
        vals = list(vals)
        clauses.append(f"{col} IN ({','.join('?' * len(vals))})")
        params += vals
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def aggregate(group_by: list[str], measures: list[str], filters: dict | None = None,
              mode: str = "flat", min_n: int = 0) -> pd.DataFrame:
    """Truy vấn tổng hợp đa chiều.

    mode = 'flat'   : GROUP BY thường
           'rollup' : WITH ROLLUP -> thêm dòng subtotal/grand-total (NULL = 'All')
           'cube'   : mọi tổ hợp subtotal (UNION ALL các tập con)
    min_n: bỏ các nhóm có ít hơn min_n người (tránh tỷ lệ không ổn định).
    """
    _check_dims(group_by)
    unknown = [m for m in measures if m not in MEASURES]
    if unknown:
        raise ValueError(f"Measure không hợp lệ: {unknown}")
    where, params = _where(filters)
    sel_meas = ", ".join(f'{MEASURES[m][0]} AS "{m}"' for m in measures)
    sel_keys = ", ".join(f"{_sort_expr(d)} AS _k{i}" for i, d in enumerate(group_by))
    having = f" HAVING count(*) >= {int(min_n)}" if min_n else ""

    def one_query(grouped: list[str], rollup: bool = False) -> tuple[str, list]:
        """SELECT cho 1 tập cột nhóm; cột không nhóm được thay bằng NULL (= dòng tổng 'All')."""
        dim_cols = ", ".join(d if d in grouped else f"NULL AS {d}" for d in group_by)
        grp = ""
        if grouped:
            grp = " GROUP BY " + ", ".join(grouped) + (" WITH ROLLUP" if rollup else "")
        cols = ", ".join(x for x in [dim_cols, sel_meas, sel_keys] if x)
        return f"SELECT {cols} FROM olap_exam{where}{grp}{having}", list(params)

    if not group_by or mode == "flat":
        q, p = one_query(group_by)
    elif mode == "rollup":
        q, p = one_query(group_by, rollup=True)  # MySQL: GROUP BY a, b WITH ROLLUP
    elif mode == "cube":
        # MySQL không có CUBE -> UNION ALL của mọi tập con các chiều
        parts = [one_query(list(sub)) for r in range(len(group_by), -1, -1)
                 for sub in itertools.combinations(group_by, r)]
        q, p = " UNION ALL ".join(x for x, _ in parts), [v for _, ps in parts for v in ps]
    else:
        raise ValueError(f"mode không hợp lệ: {mode}")
    df = sql(q, p)

    if group_by:
        key_cols = [f"_k{i}" for i in range(len(group_by))]
        if mode != "flat":  # dòng tổng (NULL) xếp sau chi tiết
            df["_tot"] = df[group_by].isna().sum(axis=1)
            df = df.sort_values(["_tot", *key_cols]).drop(columns="_tot")
            df[group_by] = df[group_by].fillna("All")
        else:
            df = df.sort_values(key_cols)
        df = df.drop(columns=key_cols)
    return df.reset_index(drop=True)


def drill(hierarchy: str, level: int, measures: list[str], filters: dict | None = None,
          parent: str | None = None) -> pd.DataFrame:
    """Drill-down: level 0 = cấp thô; level 1 = chi tiết, tuỳ chọn khoá theo giá trị `parent` ở cấp 0."""
    levels = HIERARCHIES[hierarchy]
    f = dict(filters or {})
    if parent is not None and level > 0:
        f[levels[0]] = [parent]
    cols = levels[: level + 1]
    return aggregate(cols, measures, f)


def pivot(group_rows: str, group_cols: str, measure: str, filters: dict | None = None,
          min_n: int = 0) -> pd.DataFrame:
    """Pivot (xoay chiều): hàng x cột -> giá trị measure; giữ thứ tự tự nhiên của dimension."""
    df = aggregate([group_rows, group_cols], [measure], filters, min_n=min_n)
    pv = df.pivot(index=group_rows, columns=group_cols, values=measure)
    pv = pv.reindex(index=[v for v in distinct_values(group_rows) if v in pv.index],
                    columns=[v for v in distinct_values(group_cols) if v in pv.columns])
    return pv


def two_proportion_z(p1: float, n1: int, p2: float, n2: int) -> float:
    """Thống kê z so sánh 2 tỷ lệ (dùng cho cảnh báo xu hướng)."""
    if min(n1, n2) == 0:
        return 0.0
    p = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = (p * (1 - p) * (1 / n1 + 1 / n2)) ** 0.5
    return 0.0 if se == 0 else (p1 - p2) / se
