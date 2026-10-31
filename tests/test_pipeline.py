"""Kiểm thử ETL, OLAP và DSS.  Chạy:  python -m pytest tests -q   (cần kho dữ liệu đã build)"""
import numpy as np
import pandas as pd
import pytest

from src import olap
from src.dss import engine
from src.etl import dimensions as D


# ------------------------------------------------------------- dimension logic
def test_bp_category_boundaries():
    sbp = pd.Series([110, 125, 135, 118, 145, 125, np.nan])
    dbp = pd.Series([70, 75, 70, 85, 70, 92, 70])
    assert D.bp_category_key(sbp, dbp).tolist() == [1, 2, 3, 3, 4, 4, 0]


def test_bmi_and_age_keys():
    assert D.bmi_category_key(pd.Series([17, 22, 27, 31, 36, 45, np.nan])).tolist() == [1, 2, 3, 4, 5, 6, 0]
    assert D.age_group_key(pd.Series([20, 29.9, 30, 80, 85])).tolist() == [1, 1, 2, 7, 7]


def test_cvd_profile_key_is_unique_and_handles_unknown():
    dim = D.build_dim_cvd_profile()
    assert dim["cvd_profile_key"].is_unique and len(dim) == 33
    flags = pd.DataFrame({"chf": [0, 1, np.nan, 0], "chd": [0, 0, np.nan, np.nan], "angina": [0, 0, np.nan, 0],
                          "heart_attack": [0, 1, np.nan, 0], "stroke": [0, 0, np.nan, 0]})
    keys = D.cvd_profile_key(flags)
    assert keys[0] == 1 and keys[2] == 0 and keys[3] == 0  # no CVD / all missing / partial missing no yes
    row = dim.set_index("cvd_profile_key").loc[keys[1]]
    assert row["n_conditions"] == 2 and row["cvd_group"] == "Multiple conditions"


# ------------------------------------------------------------------ warehouse
def test_referential_integrity():
    checks = {
        "dim_cycle": "cycle_key", "dim_sex": "sex_key", "dim_race": "race_key", "dim_education": "education_key",
        "dim_income": "income_key", "dim_age_group": "age_group_key", "dim_bmi_category": "bmi_category_key",
        "dim_bp_category": "bp_category_key", "dim_chol_category": "chol_category_key",
        "dim_cvd_profile": "cvd_profile_key"}
    for dim, key in checks.items():
        orphans = olap.sql(f"SELECT count(*) AS n FROM fact_health_exam f LEFT JOIN {dim} d USING ({key}) "
                           f"WHERE d.{key} IS NULL").iloc[0, 0]
        assert orphans == 0, dim


def test_view_does_not_lose_or_duplicate_rows():
    n_fact = olap.sql("SELECT count(*) FROM fact_health_exam").iloc[0, 0]
    n_view = olap.sql("SELECT count(*) FROM v_exam").iloc[0, 0]
    n_flat = olap.sql("SELECT count(*) FROM olap_exam").iloc[0, 0]
    assert n_fact == n_view == n_flat > 30_000


def test_nutrition_is_subset_of_exam():
    assert olap.sql("SELECT count(*) FROM fact_nutrition n LEFT JOIN fact_health_exam f USING (exam_id) "
                    "WHERE f.exam_id IS NULL").iloc[0, 0] == 0


def test_clean_ranges_respected():
    r = olap.sql("SELECT min(sbp) lo, max(sbp) hi, min(bmi) b0, max(bmi) b1 FROM fact_health_exam").iloc[0]
    assert r.lo >= 60 and r.hi <= 260 and r.b0 >= 10 and r.b1 <= 80


# ------------------------------------------------------------------------ OLAP
def test_rollup_totals_match():
    df = olap.aggregate(["life_stage", "age_group"], ["People (n)"], mode="rollup")
    grand = df[(df.life_stage == "All") & (df.age_group == "All")]["People (n)"].iloc[0]
    detail = df[(df.life_stage != "All") & (df.age_group != "All")]["People (n)"].sum()
    assert grand == detail == olap.sql("SELECT count(*) FROM olap_exam").iloc[0, 0]


def test_slice_filters_and_rejects_bad_dimension():
    df = olap.aggregate(["sex"], ["People (n)"], {"sex": ["Male"]})
    assert df["sex"].tolist() == ["Male"]
    with pytest.raises(ValueError):
        olap.aggregate(["sex; DROP TABLE x"], ["People (n)"])


def test_prevalence_increases_with_age():
    df = olap.aggregate(["age_group"], ["CVD prevalence (%)"], {"source_system": ["NHANES_XPT"]})
    vals = df["CVD prevalence (%)"].tolist()
    assert vals == sorted(vals)


def test_drill_down_children_sum_to_parent():
    parent = olap.drill("Age", 0, ["People (n)"]).set_index("life_stage")["People (n)"]
    child = olap.drill("Age", 1, ["People (n)"]).groupby("life_stage")["People (n)"].sum()
    assert parent.sort_index().equals(child.sort_index())


# ------------------------------------------------------------------------- DSS
def test_risk_increases_with_age_and_model_is_better_than_baseline():
    b = engine.risk_model.load_bundle()
    assert b["metrics"]["auc_logit"] > 0.75
    assert b["metrics"]["brier_logit"] < b["metrics"]["brier_baseline"]
    young = engine.assess_individual(30, True, 118, 75, 23, 180, 55, b)["probability"]
    old = engine.assess_individual(75, True, 118, 75, 23, 180, 55, b)["probability"]
    assert old > young


def test_intervention_never_increases_risk_and_is_monotone():
    small = engine.simulate_intervention(5, 10, 0.5)
    big = engine.simulate_intervention(15, 40, 3)
    assert 0 <= small["abs_reduction"] <= big["abs_reduction"]
    assert engine.simulate_intervention(0, 0, 0)["abs_reduction"] == pytest.approx(0, abs=1e-12)


def test_allocation_respects_budget_and_beats_uniform():
    out = engine.allocate_budget(200_000, 300, 100_000, ["Age group", "Blood pressure group"], 10, 30, 1.0)
    assert out["budget_used"] <= 200_000 + 1e-6
    assert (out["segments"]["coverage"].between(0, 1)).all()
    assert out["optimized_avoided"] >= out["uniform_avoided"]


def test_trend_alert_flags_known_increase():
    al = engine.trend_alerts("race_group", "Hypertension")
    assert set(al["alert"]) <= {"Rising", "Falling", "Stable"}
    assert (al["z"].diff().dropna() <= 1e-9).all()  # sắp giảm dần theo z
