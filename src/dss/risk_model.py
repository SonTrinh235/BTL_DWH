"""Mô hình dự báo nguy cơ bệnh tim mạch (model-driven DSS) huấn luyện từ kho dữ liệu.

Biến mục tiêu : has_cvd (suy tim / mạch vành / đau thắt ngực / nhồi máu / đột quỵ tự khai báo)
Đặc trưng     : tuổi, giới, SBP, BMI, HDL
                (DBP và cholesterol toàn phần bị LOẠI: trên dữ liệu cắt ngang tự khai báo, hệ số của
                 chúng đổi dấu ngược y học vì người đã bị bệnh thường đang dùng thuốc hạ huyết áp /
                 statin -> giá trị đo thấp hơn. Bộ bảng hiện có không có dữ liệu thuốc để hiệu chỉnh.
                 Tác động can thiệp vì vậy lấy từ hệ số RR trong y văn, xem engine.py)
Mô hình chính : Logistic Regression (diễn giải được, đơn điệu -> phù hợp what-if)
Benchmark     : HistGradientBoosting (chỉ để so sánh AUC)

Chạy huấn luyện:  python -m src.dss.risk_model
"""
import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src import config, olap

FEATURES = ["age_years", "male", "sbp", "bmi", "hdl_chol"]
ALL_FEATURES = ["age_years", "male", "sbp", "dbp", "bmi", "total_chol", "hdl_chol"]  # thí nghiệm lựa chọn đặc trưng
FEATURE_LABELS = {"age_years": "Age", "male": "Male sex", "sbp": "Systolic BP", "dbp": "Diastolic BP",
                  "bmi": "BMI", "total_chol": "Total cholesterol", "hdl_chol": "HDL cholesterol"}


def load_modeling_frame() -> pd.DataFrame:
    """Lấy từ DW các người có đủ nhãn CVD và giới tính (nguồn XPT, chu kỳ 2011-2018)."""
    df = olap.sql("""
        SELECT exam_id, cycle_label, age_years, CAST(sex = 'Male' AS SIGNED) AS male, sex, age_group, race_group,
               life_stage, bp_group, weight_status, income_band, sbp, dbp, bmi, total_chol, hdl_chol,
               has_cvd, mec_weight
        FROM olap_exam
        WHERE source_system = 'NHANES_XPT' AND has_cvd IS NOT NULL AND sex IN ('Male', 'Female')
    """)
    return df


def _make_pipeline(model) -> Pipeline:
    return Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler()), ("clf", model)])


def train(random_state: int = 42) -> dict:
    df = load_modeling_frame()
    X, y = df[FEATURES], df["has_cvd"].astype(int)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, stratify=y, random_state=random_state)

    logit = _make_pipeline(LogisticRegression(max_iter=1000)).fit(Xtr, ytr)
    gbm = _make_pipeline(HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                                        random_state=random_state)).fit(Xtr, ytr)
    p_logit, p_gbm = logit.predict_proba(Xte)[:, 1], gbm.predict_proba(Xte)[:, 1]
    frac_pos, mean_pred = calibration_curve(yte, p_logit, n_bins=8, strategy="quantile")

    metrics = {
        "n_total": int(len(df)), "n_train": int(len(Xtr)), "n_test": int(len(Xte)),
        "prevalence": float(y.mean()),
        "auc_logit": float(roc_auc_score(yte, p_logit)),
        "auc_gbm": float(roc_auc_score(yte, p_gbm)),
        "brier_logit": float(brier_score_loss(yte, p_logit)),
        "brier_baseline": float(brier_score_loss(yte, np.full(len(yte), ytr.mean()))),
        "calibration": {"mean_pred": mean_pred.tolist(), "frac_pos": frac_pos.tolist()},
    }
    coefs = logit.named_steps["clf"].coef_[0]
    metrics["coef_std"] = dict(zip(FEATURES, coefs.tolist()))
    # Thí nghiệm: bộ 7 đặc trưng đầy đủ (để chứng minh vì sao loại DBP/TC)
    full = _make_pipeline(LogisticRegression(max_iter=1000)).fit(df.loc[Xtr.index, ALL_FEATURES], ytr)
    metrics["auc_full7"] = float(roc_auc_score(yte, full.predict_proba(df.loc[Xte.index, ALL_FEATURES])[:, 1]))
    metrics["coef_full7"] = dict(zip(ALL_FEATURES, full.named_steps["clf"].coef_[0].tolist()))
    # Model cuối cùng huấn luyện lại trên toàn bộ dữ liệu
    final = _make_pipeline(LogisticRegression(max_iter=1000)).fit(X, y)
    bundle = {"model": final, "features": FEATURES, "metrics": metrics,
              "feature_means": X.mean().to_dict(), "feature_stds": X.std().to_dict()}
    config.WAREHOUSE_DIR.mkdir(exist_ok=True)  # thư mục không có sẵn khi chạy từ bản nộp sạch
    joblib.dump(bundle, config.MODEL_PATH)
    return bundle


def load_bundle(retrain_if_missing: bool = True) -> dict:
    if not config.MODEL_PATH.exists():
        if not retrain_if_missing:
            raise FileNotFoundError(config.MODEL_PATH)
        return train()
    return joblib.load(config.MODEL_PATH)


def predict(bundle: dict, df: pd.DataFrame) -> np.ndarray:
    return bundle["model"].predict_proba(df[bundle["features"]])[:, 1]


if __name__ == "__main__":
    b = train()
    m = b["metrics"]
    print(f"n={m['n_total']:,} (train {m['n_train']:,} / test {m['n_test']:,}), prevalence={m['prevalence']:.3f}")
    print(f"AUC logistic={m['auc_logit']:.3f} | AUC gradient boosting={m['auc_gbm']:.3f}")
    print(f"AUC 7 đặc trưng (gồm DBP, TC) = {m['auc_full7']:.3f} -> hệ số TC = {m['coef_full7']['total_chol']:+.2f} (ngược y học)")
    print(f"Brier logistic={m['brier_logit']:.4f} vs baseline={m['brier_baseline']:.4f}")
    for k, v in m["coef_std"].items():
        print(f"  {FEATURE_LABELS[k]:<20} coef (chuẩn hoá) = {v:+.3f}")
