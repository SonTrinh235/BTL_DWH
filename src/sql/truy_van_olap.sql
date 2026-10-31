-- =====================================================================
-- CÁC TRUY VẤN OLAP / PHÂN TÍCH TRÊN KHO DỮ LIỆU  cvd_dw  (MySQL 8.0)
-- Mở file này trong MySQL Workbench, chọn connection cvd_dw_local và chạy từng câu
-- (bôi đen một câu rồi nhấn Ctrl+Enter).
--
-- Bảng dùng trong file:
--   fact_health_exam, fact_nutrition      : 2 bảng fact (star schema)
--   dim_*                                 : 10 bảng dimension
--   olap_exam                             : bảng phẳng (đã join sẵn fact + dimension) - truy vấn nhanh
--   v_nutrition                           : view phẳng của fact_nutrition
--   etl_log                               : nhật ký ETL
-- Tỷ lệ hiện mắc = AVG(cờ 0/1) * 100 (cờ NULL tự bị bỏ qua).
-- Mọi tên cột kết quả đặt dạng snake_case để chạy được trên mọi sql_mode.
-- =====================================================================
USE cvd_dw;

-- ---------------------------------------------------------------------
-- A. TỔNG QUAN (KPI)
-- ---------------------------------------------------------------------

-- A1. Năm KPI của trang Tổng quan
SELECT COUNT(*)                          AS so_nguoi,
       ROUND(AVG(has_cvd) * 100, 2)      AS cvd_pct,
       ROUND(AVG(is_hypertensive) * 100, 2) AS tang_huyet_ap_pct,
       ROUND(AVG(is_obese) * 100, 2)     AS beo_phi_pct,
       ROUND(AVG(sbp), 1)                AS sbp_trung_binh
FROM olap_exam;

-- A2. Xu hướng theo chu kỳ khảo sát (chiều thời gian)
SELECT cycle_label,
       COUNT(*)                              AS so_nguoi,
       ROUND(AVG(has_cvd) * 100, 2)          AS cvd_pct,
       ROUND(AVG(is_hypertensive) * 100, 2)  AS tang_huyet_ap_pct,
       ROUND(AVG(is_obese) * 100, 2)         AS beo_phi_pct
FROM olap_exam
GROUP BY cycle_label, cycle_key
ORDER BY cycle_key;

-- ---------------------------------------------------------------------
-- B. TRUY VẤN TRÊN STAR SCHEMA (join fact với dimension)
-- ---------------------------------------------------------------------

-- B1. Tỷ lệ CVD theo chu kỳ x nhóm tuổi - join đúng mô hình sao
SELECT c.cycle_label, a.age_group,
       COUNT(*)                         AS so_nguoi,
       ROUND(AVG(f.has_cvd) * 100, 2)   AS cvd_pct
FROM fact_health_exam f
JOIN dim_cycle     c USING (cycle_key)
JOIN dim_age_group a USING (age_group_key)
GROUP BY c.cycle_label, c.cycle_key, a.age_group, a.age_group_key
ORDER BY c.cycle_key, a.age_group_key;

-- B2. Số người theo từng tổ hợp bệnh tim mạch (junk dimension), phổ biến nhất trước
SELECT v.profile_label, v.n_conditions, COUNT(*) AS so_nguoi
FROM fact_health_exam f
JOIN dim_cvd_profile v USING (cvd_profile_key)
WHERE v.cvd_group <> 'No CVD' AND v.cvd_group <> 'Unknown'
GROUP BY v.profile_label, v.n_conditions
ORDER BY so_nguoi DESC
LIMIT 10;

-- ---------------------------------------------------------------------
-- C. SLICE & DICE
-- ---------------------------------------------------------------------

-- C1. Slice: chỉ giữ giới tính = nữ, xem theo nhóm tuổi
SELECT age_group, COUNT(*) AS so_nguoi, ROUND(AVG(has_cvd) * 100, 2) AS cvd_pct
FROM olap_exam
WHERE sex = 'Female'
GROUP BY age_group, age_group_key
ORDER BY age_group_key;

-- C2. Dice: nhiều điều kiện trên nhiều chiều (>= 60 tuổi, thừa cân/béo phì, tăng huyết áp, nguồn XPT)
SELECT sex, COUNT(*) AS so_nguoi, ROUND(AVG(has_cvd) * 100, 2) AS cvd_pct
FROM olap_exam
WHERE life_stage = 'Older adult'
  AND weight_status = 'Excess weight'
  AND bp_group = 'Hypertensive'
  AND source_system = 'NHANES_XPT'
  AND sex IN ('Male', 'Female')
GROUP BY sex;

-- ---------------------------------------------------------------------
-- D. ROLL-UP / DRILL-DOWN / CUBE / PIVOT
-- ---------------------------------------------------------------------

-- D1. Roll-up: giai đoạn đời -> nhóm tuổi, có dòng tổng phụ và tổng chung (NULL = "All")
SELECT life_stage, age_group, COUNT(*) AS so_nguoi,
       ROUND(AVG(has_cvd) * 100, 2) AS cvd_pct
FROM olap_exam
GROUP BY life_stage, age_group WITH ROLLUP;

-- D2. Drill-down, bước 1: mức thô (giai đoạn đời)
SELECT life_stage, COUNT(*) AS so_nguoi, ROUND(AVG(has_cvd) * 100, 2) AS cvd_pct
FROM olap_exam
GROUP BY life_stage
ORDER BY MIN(age_group_key);

-- D3. Drill-down, bước 2: khoan vào "Older adult" xuống nhóm tuổi 10 năm
SELECT age_group, COUNT(*) AS so_nguoi, ROUND(AVG(has_cvd) * 100, 2) AS cvd_pct
FROM olap_exam
WHERE life_stage = 'Older adult'
GROUP BY age_group, age_group_key
ORDER BY age_group_key;

-- D4. Cube giới x giai đoạn đời: MySQL không có CUBE nên UNION ALL các tập con (2^2 = 4)
SELECT sex, life_stage, COUNT(*) AS so_nguoi, ROUND(AVG(has_cvd) * 100, 2) AS cvd_pct
  FROM olap_exam WHERE sex IN ('Male', 'Female') GROUP BY sex, life_stage
UNION ALL
SELECT sex, NULL, COUNT(*), ROUND(AVG(has_cvd) * 100, 2)
  FROM olap_exam WHERE sex IN ('Male', 'Female') GROUP BY sex
UNION ALL
SELECT NULL, life_stage, COUNT(*), ROUND(AVG(has_cvd) * 100, 2)
  FROM olap_exam WHERE sex IN ('Male', 'Female') GROUP BY life_stage
UNION ALL
SELECT NULL, NULL, COUNT(*), ROUND(AVG(has_cvd) * 100, 2)
  FROM olap_exam WHERE sex IN ('Male', 'Female');

-- D5. Pivot: hàng = nhóm tuổi, cột = giới (xoay bằng CASE / AVG có điều kiện)
SELECT age_group,
       ROUND(AVG(CASE WHEN sex = 'Male'   THEN has_cvd END) * 100, 2) AS nam_cvd_pct,
       ROUND(AVG(CASE WHEN sex = 'Female' THEN has_cvd END) * 100, 2) AS nu_cvd_pct
FROM olap_exam
WHERE sex IN ('Male', 'Female')
GROUP BY age_group, age_group_key
ORDER BY age_group_key;

-- D6. Bản đồ nhiệt nhóm tuổi x phân loại BMI, ẩn ô dưới 30 người
SELECT age_group, bmi_category, COUNT(*) AS so_nguoi,
       ROUND(AVG(has_cvd) * 100, 2) AS cvd_pct
FROM olap_exam
WHERE source_system = 'NHANES_XPT'
GROUP BY age_group, age_group_key, bmi_category, bmi_category_key
HAVING COUNT(*) >= 30
ORDER BY age_group_key, bmi_category_key;

-- ---------------------------------------------------------------------
-- E. PHÂN TÍCH NGUYÊN NHÂN (ROOT-CAUSE)
-- ---------------------------------------------------------------------

-- E1. Trong cùng nhóm tuổi, tình trạng cân nặng ảnh hưởng thế nào?
SELECT age_group, weight_status, COUNT(*) AS so_nguoi,
       ROUND(AVG(has_cvd) * 100, 2) AS cvd_pct
FROM olap_exam
WHERE source_system = 'NHANES_XPT' AND weight_status <> 'Unknown'
GROUP BY age_group, age_group_key, weight_status
HAVING COUNT(*) >= 40
ORDER BY age_group_key, weight_status;

-- E2. Window function: xếp hạng nhóm tuổi x huyết áp theo tỷ lệ CVD trong từng giai đoạn đời
WITH seg AS (
  SELECT life_stage, age_group, bp_category,
         COUNT(*) AS so_nguoi, AVG(has_cvd) * 100 AS cvd_pct
  FROM olap_exam
  WHERE source_system = 'NHANES_XPT' AND bp_group <> 'Unknown'
  GROUP BY life_stage, age_group, bp_category
  HAVING COUNT(*) >= 40
)
SELECT life_stage, age_group, bp_category, so_nguoi, ROUND(cvd_pct, 2) AS cvd_pct,
       RANK() OVER (PARTITION BY life_stage ORDER BY cvd_pct DESC) AS hang_trong_giai_doan
FROM seg
ORDER BY life_stage, hang_trong_giai_doan;

-- E3. Chênh lệch theo thu nhập (chưa hiệu chỉnh tuổi)
SELECT income_band, COUNT(*) AS so_nguoi, ROUND(AVG(has_cvd) * 100, 2) AS cvd_pct
FROM olap_exam
WHERE source_system = 'NHANES_XPT' AND income_band <> 'Unknown'
GROUP BY income_band, income_key
ORDER BY income_key;

-- E4. Khẩu phần ăn theo nhóm huyết áp (bảng fact_nutrition)
SELECT bp_group,
       COUNT(*)                          AS so_nguoi,
       ROUND(AVG(sodium_mg))             AS natri_mg_tb,
       ROUND(AVG(potassium_mg))          AS kali_mg_tb,
       ROUND(AVG(na_k_ratio), 2)         AS ty_le_na_k,
       ROUND(AVG(high_sodium) * 100, 1)  AS an_man_pct,
       ROUND(AVG(low_fiber) * 100, 1)    AS it_xo_pct
FROM v_nutrition
WHERE bp_group <> 'Unknown'
GROUP BY bp_group;

-- ---------------------------------------------------------------------
-- F. HỖ TRỢ DSS
-- ---------------------------------------------------------------------

-- F1. Quy mô và tỷ lệ CVD thực tế của từng phân khúc (nhóm tuổi x huyết áp) - đầu vào của bài toán
--     phân bổ ngân sách; DSS dùng thêm nguy cơ nền từ mô hình để tính "giảm nguy cơ tuyệt đối".
SELECT age_group, bp_group,
       COUNT(*)                                          AS mau,
       ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2)  AS ti_trong_pct,
       ROUND(AVG(has_cvd) * 100, 2)                      AS cvd_pct
FROM olap_exam
WHERE source_system = 'NHANES_XPT' AND sex IN ('Male', 'Female')
GROUP BY age_group, age_group_key, bp_group
ORDER BY cvd_pct DESC;

-- F2. Cảnh báo xu hướng: tăng huyết áp theo nhóm chủng tộc, 2011-2012 so với 2017-2018,
--     kiểm định z hai tỷ lệ tính ngay trong SQL (|z| >= 1.96 => thay đổi có ý nghĩa thống kê)
WITH t AS (
  SELECT race_group,
         SUM(cycle_label = '2011-2012')                                   AS n1,
         AVG(CASE WHEN cycle_label = '2011-2012' THEN is_hypertensive END) AS p1,
         SUM(cycle_label = '2017-2018')                                   AS n2,
         AVG(CASE WHEN cycle_label = '2017-2018' THEN is_hypertensive END) AS p2,
         AVG(is_hypertensive)                                             AS p_all
  FROM olap_exam
  WHERE cycle_label IN ('2011-2012', '2017-2018')
    AND is_hypertensive IS NOT NULL AND race_group <> 'Unknown'
  GROUP BY race_group
)
SELECT race_group, n1, ROUND(p1 * 100, 2) AS truoc_pct, n2, ROUND(p2 * 100, 2) AS sau_pct,
       ROUND((p2 - p1) * 100, 2) AS thay_doi_diem_pct,
       ROUND((p2 - p1) / SQRT(p_all * (1 - p_all) * (1 / n1 + 1 / n2)), 2) AS z,
       CASE WHEN (p2 - p1) / SQRT(p_all * (1 - p_all) * (1 / n1 + 1 / n2)) >= 1.96  THEN 'Rising'
            WHEN (p2 - p1) / SQRT(p_all * (1 - p_all) * (1 / n1 + 1 / n2)) <= -1.96 THEN 'Falling'
            ELSE 'Stable' END AS canh_bao
FROM t;

-- ---------------------------------------------------------------------
-- G. KIỂM TRA CHẤT LƯỢNG VÀ TOÀN VẸN DỮ LIỆU
-- ---------------------------------------------------------------------

-- G1. Độ đầy đủ dữ liệu theo chu kỳ (% bản ghi có giá trị)
SELECT c.cycle_label, COUNT(*) AS so_nguoi,
       ROUND(100 * COUNT(f.sbp)        / COUNT(*), 1) AS sbp_pct,
       ROUND(100 * COUNT(f.bmi)        / COUNT(*), 1) AS bmi_pct,
       ROUND(100 * COUNT(f.total_chol) / COUNT(*), 1) AS cholesterol_pct,
       ROUND(100 * COUNT(f.hdl_chol)   / COUNT(*), 1) AS hdl_pct,
       ROUND(100 * COUNT(f.has_cvd)    / COUNT(*), 1) AS nhan_cvd_pct
FROM fact_health_exam f
JOIN dim_cycle c USING (cycle_key)
GROUP BY c.cycle_label, c.cycle_key
ORDER BY c.cycle_key;

-- G2. Kiểm tra toàn vẹn tham chiếu: số khóa ngoại "orphan" (trỏ tới bản ghi không tồn tại) phải bằng 0
SELECT 'cycle' AS dimension, COUNT(*) AS mo_coi
  FROM fact_health_exam f LEFT JOIN dim_cycle d USING (cycle_key) WHERE d.cycle_key IS NULL
UNION ALL
SELECT 'age_group', COUNT(*)
  FROM fact_health_exam f LEFT JOIN dim_age_group d USING (age_group_key) WHERE d.age_group_key IS NULL
UNION ALL
SELECT 'cvd_profile', COUNT(*)
  FROM fact_health_exam f LEFT JOIN dim_cvd_profile d USING (cvd_profile_key) WHERE d.cvd_profile_key IS NULL
UNION ALL
SELECT 'nutrition_exam', COUNT(*)
  FROM fact_nutrition n LEFT JOIN fact_health_exam f USING (exam_id) WHERE f.exam_id IS NULL;

-- G3. Nhật ký ETL: mỗi bước lọc/loại bỏ bao nhiêu dòng
SELECT step, detail, rows_in, rows_out, rows_dropped FROM etl_log ORDER BY log_id;

-- G4. Số dòng từng bảng
SELECT 'fact_health_exam' AS bang, COUNT(*) AS so_dong FROM fact_health_exam
UNION ALL SELECT 'fact_nutrition', COUNT(*) FROM fact_nutrition
UNION ALL SELECT 'olap_exam', COUNT(*) FROM olap_exam
UNION ALL SELECT 'dim_cvd_profile', COUNT(*) FROM dim_cvd_profile;
