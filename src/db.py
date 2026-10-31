"""Kết nối MySQL (SQLAlchemy + PyMySQL).

* read_engine(): dùng cho OLAP/dashboard/DSS - phiên READ ONLY, bật ANSI_QUOTES
  (để "alias có dấu cách" hoạt động như SQL chuẩn).
* admin_engine(): dùng cho ETL - có quyền ghi, tự tạo database nếu chưa có.
"""
from functools import lru_cache

import pandas as pd
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL, Engine

from src import config

ANSI = "SET SESSION sql_mode = CONCAT(@@sql_mode, ',ANSI_QUOTES')"


def _url(database: str | None) -> URL:
    m = config.MYSQL
    return URL.create("mysql+pymysql", username=m["user"], password=m["password"] or None,
                      host=m["host"], port=m["port"], database=database, query={"charset": "utf8mb4"})


def ensure_database() -> None:
    """Tạo database nếu chưa có (cần quyền CREATE)."""
    eng = create_engine(_url(None))
    with eng.begin() as con:
        con.execute(text(f"CREATE DATABASE IF NOT EXISTS `{config.MYSQL['database']}` "
                         "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"))
    eng.dispose()


def admin_engine() -> Engine:
    return create_engine(_url(config.MYSQL["database"]), connect_args={"init_command": ANSI})


@lru_cache(maxsize=1)
def read_engine() -> Engine:
    eng = create_engine(_url(config.MYSQL["database"]), pool_pre_ping=True, pool_recycle=1800)

    @event.listens_for(eng, "connect")
    def _session_setup(dbapi_con, _):  # mỗi kết nối: ANSI_QUOTES + chỉ đọc
        cur = dbapi_con.cursor()
        cur.execute(ANSI)
        cur.execute("SET SESSION TRANSACTION READ ONLY")
        cur.close()

    return eng


def warehouse_ready() -> bool:
    """True nếu database có sẵn và đã nạp bảng fact."""
    try:
        with read_engine().connect() as con:
            return con.execute(text("SELECT count(*) FROM fact_health_exam")).scalar() > 0
    except Exception:
        return False


def query_df(sql: str, params: list | None = None) -> pd.DataFrame:
    """Chạy SELECT, trả DataFrame. Placeholder `?` được đổi thành `%s` của PyMySQL.
    Kết quả DECIMAL (từ AVG/SUM của MySQL) được chuyển sang float/int."""
    args = tuple(p.item() if hasattr(p, "item") else p for p in params) if params else None
    # PyMySQL nội suy bằng `%` (kể cả khi không có tham số): escape '%' có sẵn trong SQL
    # (vd. alias "CVD (%)") trước khi đổi placeholder `?` -> `%s`
    sql = sql.replace("%", "%%").replace("?", "%s")
    with read_engine().connect() as con:
        res = con.exec_driver_sql(sql, args) if args else con.exec_driver_sql(sql)
        df = pd.DataFrame(res.fetchall(), columns=list(res.keys()))
    for c in df.columns:
        if df[c].dtype == object and df[c].notna().any() and type(df[c].dropna().iloc[0]).__name__ == "Decimal":
            df[c] = pd.to_numeric(df[c])
    return df
