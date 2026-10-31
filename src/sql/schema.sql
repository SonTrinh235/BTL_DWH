-- =====================================================================
-- Data Warehouse: Phân tích nguy cơ bệnh tim mạch (CVD) - NHANES
-- Mô hình: Constellation (2 bảng fact dùng chung các dimension - conformed)
-- DBMS: MySQL 8.0 (InnoDB). Mỗi câu lệnh kết thúc bằng ';' ở cuối dòng.
-- =====================================================================

-- ---------------------------- DIMENSIONS ------------------------------
CREATE TABLE dim_cycle (
    cycle_key      INT PRIMARY KEY,
    cycle_label    VARCHAR(30) NOT NULL,      -- 2011-2012, ...
    start_year     INT,
    end_year       INT,
    period_group   VARCHAR(30),               -- cấp cao hơn: giai đoạn khảo sát
    source_system  VARCHAR(30)                -- NHANES_XPT | NHANES_CVD_CSV
);

CREATE TABLE dim_sex (
    sex_key  INT PRIMARY KEY,
    sex      VARCHAR(10) NOT NULL
);

CREATE TABLE dim_race (
    race_key    INT PRIMARY KEY,
    race        VARCHAR(40) NOT NULL,         -- 5 nhóm của NHANES (RIDRETH1)
    race_group  VARCHAR(20) NOT NULL          -- Hispanic | Non-Hispanic | Unknown
);

CREATE TABLE dim_education (
    education_key    INT PRIMARY KEY,
    education        VARCHAR(40) NOT NULL,
    education_level  VARCHAR(20) NOT NULL     -- Low | Medium | High | Unknown
);

CREATE TABLE dim_income (
    income_key   INT PRIMARY KEY,
    income_band  VARCHAR(30) NOT NULL,        -- theo Poverty Income Ratio (PIR)
    sort_order   INT
);

CREATE TABLE dim_age_group (
    age_group_key  INT PRIMARY KEY,
    age_group      VARCHAR(10) NOT NULL,      -- 20-29, 30-39, ...
    life_stage     VARCHAR(20) NOT NULL,      -- Young adult | Middle-aged | Older adult
    min_age        INT,
    max_age        INT
);

CREATE TABLE dim_bmi_category (
    bmi_category_key  INT PRIMARY KEY,
    bmi_category      VARCHAR(30) NOT NULL,   -- Underweight ... Obese III
    weight_status     VARCHAR(20) NOT NULL,   -- Healthy | Excess weight | Underweight | Unknown
    sort_order        INT
);

CREATE TABLE dim_bp_category (
    bp_category_key  INT PRIMARY KEY,
    bp_category      VARCHAR(50) NOT NULL,    -- ACC/AHA 2017
    bp_group         VARCHAR(20) NOT NULL,    -- Normotensive | Hypertensive | Unknown
    sort_order       INT
);

CREATE TABLE dim_chol_category (
    chol_category_key  INT PRIMARY KEY,
    chol_category      VARCHAR(30) NOT NULL,  -- Desirable / Borderline / High
    sort_order         INT
);

-- Junk dimension: tổ hợp 5 cờ bệnh tim mạch tự khai báo
CREATE TABLE dim_cvd_profile (
    cvd_profile_key  INT PRIMARY KEY,
    chf              VARCHAR(10),             -- suy tim
    chd              VARCHAR(10),             -- bệnh mạch vành
    angina           VARCHAR(10),             -- đau thắt ngực
    heart_attack     VARCHAR(10),             -- nhồi máu cơ tim
    stroke           VARCHAR(10),             -- đột quỵ
    n_conditions     INT,
    profile_label    VARCHAR(120),
    cvd_group        VARCHAR(30)              -- No CVD | Single condition | Multiple conditions | Unknown
);

-- ------------------------------- FACTS --------------------------------
-- Grain: 1 người trưởng thành (>=20 tuổi) được khám trong 1 chu kỳ khảo sát
CREATE TABLE fact_health_exam (
    exam_id            BIGINT PRIMARY KEY,   -- = SEQN (degenerate dimension)
    cycle_key          INT NOT NULL,
    sex_key            INT NOT NULL,
    race_key           INT NOT NULL,
    education_key      INT NOT NULL,
    income_key         INT NOT NULL,
    age_group_key      INT NOT NULL,
    bmi_category_key   INT NOT NULL,
    bp_category_key    INT NOT NULL,
    chol_category_key  INT NOT NULL,
    cvd_profile_key    INT NOT NULL,
    -- measures
    age_years          DOUBLE,
    sbp                DOUBLE,   -- huyết áp tâm thu trung bình (mmHg)
    dbp                DOUBLE,   -- huyết áp tâm trương trung bình (mmHg)
    pulse              DOUBLE,
    bmi                DOUBLE,
    waist_cm           DOUBLE,
    weight_kg          DOUBLE,
    height_cm          DOUBLE,
    total_chol         DOUBLE,   -- mg/dL
    hdl_chol           DOUBLE,   -- mg/dL
    non_hdl_chol       DOUBLE,
    crp_mgl            DOUBLE,   -- C-reactive protein (chỉ nguồn CSV)
    income_ratio       DOUBLE,   -- PIR 0-5
    mec_weight         DOUBLE,   -- trọng số khảo sát (chỉ nguồn XPT)
    -- cờ 0/1 để tính tỷ lệ (AVG của cờ = prevalence)
    has_cvd            TINYINT,
    is_hypertensive    TINYINT,
    is_obese           TINYINT,
    is_high_chol       TINYINT,
    is_low_hdl         TINYINT,
    CONSTRAINT fk_fhe_cycle FOREIGN KEY (cycle_key)         REFERENCES dim_cycle(cycle_key),
    CONSTRAINT fk_fhe_sex   FOREIGN KEY (sex_key)           REFERENCES dim_sex(sex_key),
    CONSTRAINT fk_fhe_race  FOREIGN KEY (race_key)          REFERENCES dim_race(race_key),
    CONSTRAINT fk_fhe_edu   FOREIGN KEY (education_key)     REFERENCES dim_education(education_key),
    CONSTRAINT fk_fhe_inc   FOREIGN KEY (income_key)        REFERENCES dim_income(income_key),
    CONSTRAINT fk_fhe_age   FOREIGN KEY (age_group_key)     REFERENCES dim_age_group(age_group_key),
    CONSTRAINT fk_fhe_bmi   FOREIGN KEY (bmi_category_key)  REFERENCES dim_bmi_category(bmi_category_key),
    CONSTRAINT fk_fhe_bp    FOREIGN KEY (bp_category_key)   REFERENCES dim_bp_category(bp_category_key),
    CONSTRAINT fk_fhe_chol  FOREIGN KEY (chol_category_key) REFERENCES dim_chol_category(chol_category_key),
    CONSTRAINT fk_fhe_cvd   FOREIGN KEY (cvd_profile_key)   REFERENCES dim_cvd_profile(cvd_profile_key)
);

-- Grain: 1 người có dữ liệu dinh dưỡng 24h (nguồn Nhanes_cvd_raw.csv)
CREATE TABLE fact_nutrition (
    exam_id            BIGINT PRIMARY KEY,
    cycle_key          INT NOT NULL,
    age_group_key      INT NOT NULL,
    bmi_category_key   INT NOT NULL,
    bp_category_key    INT NOT NULL,
    cvd_profile_key    INT NOT NULL,
    protein_g          DOUBLE,
    carbohydrate_g     DOUBLE,
    sugar_g            DOUBLE,
    fiber_g            DOUBLE,
    saturated_fat_g    DOUBLE,
    monounsat_fat_g    DOUBLE,
    polyunsat_fat_g    DOUBLE,
    dietary_chol_mg    DOUBLE,
    sodium_mg          DOUBLE,
    potassium_mg       DOUBLE,
    calcium_mg         DOUBLE,
    magnesium_mg       DOUBLE,
    vitamin_d_mcg      DOUBLE,
    na_k_ratio         DOUBLE,   -- Sodium / Potassium (mg/mg)
    high_sodium        TINYINT,  -- >= 2300 mg/ngày (khuyến nghị tối đa)
    low_fiber          TINYINT,  -- < 25 g/ngày
    CONSTRAINT fk_nut_exam  FOREIGN KEY (exam_id)          REFERENCES fact_health_exam(exam_id),
    CONSTRAINT fk_nut_cycle FOREIGN KEY (cycle_key)        REFERENCES dim_cycle(cycle_key),
    CONSTRAINT fk_nut_age   FOREIGN KEY (age_group_key)    REFERENCES dim_age_group(age_group_key),
    CONSTRAINT fk_nut_bmi   FOREIGN KEY (bmi_category_key) REFERENCES dim_bmi_category(bmi_category_key),
    CONSTRAINT fk_nut_bp    FOREIGN KEY (bp_category_key)  REFERENCES dim_bp_category(bp_category_key),
    CONSTRAINT fk_nut_cvd   FOREIGN KEY (cvd_profile_key)  REFERENCES dim_cvd_profile(cvd_profile_key)
);

-- --------------------------- ETL AUDIT LOG ----------------------------
CREATE TABLE etl_log (
    log_id       INT AUTO_INCREMENT PRIMARY KEY,
    step         VARCHAR(30),
    detail       VARCHAR(255),
    rows_in      BIGINT,
    rows_out     BIGINT,
    rows_dropped BIGINT,
    logged_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------ INDEXES -------------------------------
CREATE INDEX ix_fhe_cycle ON fact_health_exam(cycle_key);
CREATE INDEX ix_fhe_age   ON fact_health_exam(age_group_key);
CREATE INDEX ix_fhe_cvd   ON fact_health_exam(cvd_profile_key);

-- ------------------------- VIEW PHẲNG CHO OLAP -------------------------
-- Lưu ý: truy vấn qua view 10 bảng này chậm (~6s, chủ yếu do MySQL lập kế hoạch join).
-- Tầng OLAP dùng bảng phẳng olap_exam được lưu sẵn (materialize) từ view này (xem materialize.sql).
CREATE VIEW v_exam AS
SELECT f.*, c.cycle_label, c.period_group, c.source_system,
       s.sex, r.race, r.race_group, e.education, e.education_level, i.income_band,
       a.age_group, a.life_stage, b.bmi_category, b.weight_status,
       p.bp_category, p.bp_group, h.chol_category,
       v.profile_label, v.cvd_group, v.n_conditions
FROM fact_health_exam f
JOIN dim_cycle c USING (cycle_key)
JOIN dim_sex s USING (sex_key)
JOIN dim_race r USING (race_key)
JOIN dim_education e USING (education_key)
JOIN dim_income i USING (income_key)
JOIN dim_age_group a USING (age_group_key)
JOIN dim_bmi_category b USING (bmi_category_key)
JOIN dim_bp_category p USING (bp_category_key)
JOIN dim_chol_category h USING (chol_category_key)
JOIN dim_cvd_profile v USING (cvd_profile_key);

CREATE VIEW v_nutrition AS
SELECT n.*, c.cycle_label, c.period_group, a.age_group, a.life_stage,
       b.bmi_category, b.weight_status, p.bp_category, p.bp_group,
       v.cvd_group, v.profile_label
FROM fact_nutrition n
JOIN dim_cycle c USING (cycle_key)
JOIN dim_age_group a USING (age_group_key)
JOIN dim_bmi_category b USING (bmi_category_key)
JOIN dim_bp_category p USING (bp_category_key)
JOIN dim_cvd_profile v USING (cvd_profile_key);
