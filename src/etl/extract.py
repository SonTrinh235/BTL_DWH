"""EXTRACT: đọc dữ liệu thô từ 2 nguồn (NHANES .XPT và Nhanes_cvd_raw.csv)."""
import pandas as pd

from src import config


def extract_nhanes_xpt() -> dict[str, pd.DataFrame]:
    """Đọc 6 bảng x 4 chu kỳ; gộp theo bảng, thêm cột cycle_code."""
    out = {}
    for table in config.NHANES_TABLES:
        frames = []
        for code in config.NHANES_CYCLES:
            path = config.NHANES_DIR / f"{table}_{code}.XPT"
            df = pd.read_sas(path, format="xport", encoding="utf-8")
            df["SEQN"] = df["SEQN"].astype("int64")
            df["cycle_code"] = code
            frames.append(df)
        out[table] = pd.concat(frames, ignore_index=True)
    return out


def extract_nhanes_cvd_csv() -> pd.DataFrame:
    """Đọc file nguồn thứ 2 (dinh dưỡng + bệnh tim mạch, 2017-2023)."""
    return pd.read_csv(config.NHANES_CVD_CSV)
