"""Cấu hình đường dẫn và hằng số dùng chung cho toàn bộ hệ thống."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    """Đọc file .env đơn giản (KEY=VALUE); biến môi trường có sẵn được ưu tiên."""
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")

MYSQL = {
    "host": os.environ.get("MYSQL_HOST", "localhost"),
    "port": int(os.environ.get("MYSQL_PORT", "3306")),
    "user": os.environ.get("MYSQL_USER", "root"),
    "password": os.environ.get("MYSQL_PASSWORD", ""),
    "database": os.environ.get("MYSQL_DATABASE", "cvd_dw"),
}

RAW_DIR = ROOT / "data" / "raw"
NHANES_DIR = RAW_DIR / "nhanes"
NHANES_CVD_CSV = RAW_DIR / "nhanes_cvd_2017_23" / "Nhanes_cvd_raw.csv"

WAREHOUSE_DIR = ROOT / "warehouse"  # chỉ chứa model đã huấn luyện; dữ liệu nằm trong MySQL
MODEL_PATH = WAREHOUSE_DIR / "risk_model.joblib"
SQL_DIR = ROOT / "src" / "sql"

# Các chu kỳ NHANES có file raw .XPT: mã hậu tố -> (nhãn, năm bắt đầu, năm kết thúc)
NHANES_CYCLES = {
    "G": ("2011-2012", 2011, 2012),
    "H": ("2013-2014", 2013, 2014),
    "I": ("2015-2016", 2015, 2016),
    "J": ("2017-2018", 2017, 2018),
}
NHANES_TABLES = ["DEMO", "BMX", "BPX", "HDL", "TCHOL", "MCQ"]

# Ngưỡng SEQN của file Nhanes_cvd_raw.csv (nguồn thứ 2)
CVD_PREPANDEMIC_MAX_SEQN = 124822   # 2017 - 03/2020
CVD_POSTPANDEMIC_MIN_SEQN = 130378  # 08/2021 - 08/2023

ADULT_MIN_AGE = 20  # bộ câu hỏi bệnh tim mạch (MCQ160) chỉ hỏi người >= 20 tuổi

# Khoảng giá trị hợp lệ (ngoài khoảng -> NULL và ghi vào etl_log)
VALID_RANGES = {
    "sbp": (60, 260),
    "dbp": (20, 150),
    "pulse": (30, 200),
    "bmi": (10, 80),
    "waist_cm": (40, 200),
    "weight_kg": (20, 300),
    "height_cm": (100, 230),
    "total_chol": (70, 500),
    "hdl_chol": (10, 150),
    "crp_mgl": (0, 300),
}
