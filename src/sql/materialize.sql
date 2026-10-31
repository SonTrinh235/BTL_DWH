-- Bảng phẳng cho OLAP: join sẵn star schema một lần lúc ETL (MySQL không có materialized view).
-- Tầng OLAP/dashboard truy vấn bảng này nên mỗi truy vấn chỉ quét 1 bảng thay vì join 10 bảng.
CREATE TABLE olap_exam AS SELECT * FROM v_exam;

ALTER TABLE olap_exam ADD PRIMARY KEY (exam_id);

CREATE INDEX ix_olap_cycle ON olap_exam(cycle_label);
CREATE INDEX ix_olap_age   ON olap_exam(age_group_key);
