"""Chạy toàn bộ pipeline ETL:  python -m src.etl.run_etl"""
import re
import time

import pandas as pd
from sqlalchemy import text

from src import config, db
from src.etl.extract import extract_nhanes_cvd_csv, extract_nhanes_xpt
from src.etl.transform import transform

DIM_ORDER = ["dim_cycle", "dim_sex", "dim_race", "dim_education", "dim_income", "dim_age_group",
             "dim_bmi_category", "dim_bp_category", "dim_chol_category", "dim_cvd_profile"]
FACTS = ["fact_health_exam", "fact_nutrition"]
VIEWS = ["v_exam", "v_nutrition"]
ALL_TABLES = ["olap_exam", "etl_log", *FACTS[::-1], *DIM_ORDER[::-1]]


def _statements(script: str) -> list[str]:
    """Tách file .sql thành từng câu lệnh (bỏ comment `-- ...`)."""
    script = re.sub(r"--[^\n]*", "", script)
    return [s.strip() for s in script.split(";") if s.strip()]


def _bulk_insert(con, table: str, df: pd.DataFrame, chunk: int = 5000) -> None:
    df = df.astype(object).where(df.notna(), None)  # NaN/NA -> NULL
    df.to_sql(table, con, if_exists="append", index=False, method="multi", chunksize=chunk)


def load(res) -> None:
    """LOAD: tạo lại schema rồi nạp dimension -> fact -> log (full refresh, idempotent)."""
    db.ensure_database()
    eng = db.admin_engine()
    with eng.begin() as con:
        con.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for v in VIEWS:
            con.execute(text(f"DROP VIEW IF EXISTS {v}"))
        for t in ALL_TABLES:
            con.execute(text(f"DROP TABLE IF EXISTS {t}"))
        con.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        for stmt in _statements((config.SQL_DIR / "schema.sql").read_text(encoding="utf-8")):
            con.execute(text(stmt))
        for name in DIM_ORDER:
            _bulk_insert(con, name, res.dims[name])
        _bulk_insert(con, "fact_health_exam", res.fact_health_exam)
        _bulk_insert(con, "fact_nutrition", res.fact_nutrition)
        for step, detail, rin, rout in res.log:
            dropped = rin if step == "clean_outlier" else max(rin - rout, 0)
            con.execute(text("INSERT INTO etl_log (step, detail, rows_in, rows_out, rows_dropped) "
                             "VALUES (:s, :d, :i, :o, :x)"),
                        {"s": step, "d": detail, "i": rin, "o": rout, "x": dropped})
        for stmt in _statements((config.SQL_DIR / "materialize.sql").read_text(encoding="utf-8")):
            con.execute(text(stmt))  # bảng phẳng olap_exam cho tầng OLAP
        for t in [*DIM_ORDER, *FACTS, "olap_exam"]:  # cập nhật thống kê index cho optimizer
            con.execute(text(f"ANALYZE TABLE {t}")).fetchall()
    eng.dispose()


def main() -> None:
    t0 = time.time()
    print("[1/3] Extract ...")
    xpt = extract_nhanes_xpt()
    csv = extract_nhanes_cvd_csv()
    print(f"      XPT: { {k: len(v) for k, v in xpt.items()} } | CSV: {len(csv)} dòng")
    print("[2/3] Transform ...")
    res = transform(xpt, csv)
    print(f"[3/3] Load vào MySQL ({config.MYSQL['host']}:{config.MYSQL['port']}/{config.MYSQL['database']}) ...")
    load(res)
    db.read_engine.cache_clear()
    for t in FACTS:
        n = db.query_df(f"SELECT count(*) AS n FROM {t}").iloc[0, 0]
        print(f"      {t}: {n:,} dòng")
    print(f"Xong trong {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
