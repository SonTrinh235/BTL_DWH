# Kho dữ liệu & Hệ hỗ trợ quyết định cho phân tích bệnh tim mạch (NHANES)

Bài tập lớn CO4031 – HK261. Hệ thống gồm: ETL → Data Warehouse (MySQL 8.0, mô hình constellation) → OLAP → Dashboard (Streamlit) → DSS.

## Bài toán nghiệp vụ
Cơ quan y tế công cộng có ngân sách sàng lọc/can thiệp hữu hạn và cần trả lời:
1. Tỷ lệ bệnh tim mạch (CVD), tăng huyết áp, béo phì… phân bố thế nào theo tuổi, giới, chủng tộc, thu nhập, theo thời gian?
2. Nhóm nào có nguy cơ cao nhất, và yếu tố nào làm khác biệt trong cùng nhóm tuổi?
3. Nếu giảm huyết áp/cholesterol/BMI cho một nhóm thì tránh được bao nhiêu ca? Nên dồn ngân sách vào nhóm nào?
4. Nhóm nào đang xấu đi có ý nghĩa thống kê (cảnh báo sớm)?

## Dữ liệu (đã kiểm tra – dùng được, không cần dữ liệu mới)
| Nguồn | Nội dung | Quy mô | Dùng cho |
|---|---|---|---|
| `data/raw/nhanes/*.XPT` (từ `DoAnCN/data/nhanes_raw`) | NHANES 2011-2018: DEMO, BMX, BPX, HDL, TCHOL, MCQ × 4 chu kỳ | 39.156 người → 21.572 người lớn được khám | `fact_health_exam` |
| `data/raw/nhanes_cvd_2017_23/Nhanes_cvd_raw.csv` (từ `DoAnCN/data2`) | Dinh dưỡng 24h, CRP, vòng eo, huyết áp, nhãn CVD | 27.493 → 17.040 người lớn | `fact_health_exam` + `fact_nutrition` |

Không dùng: `cardio_train.csv`, `framingham.csv`, `heart_disease_uci.csv`, `nhanes_cardio.csv` (bản tổng hợp đã xử lý sẵn, trùng nguồn thô), `main_dataset/` (chỉ 1 chu kỳ, 6 file rất rộng – gợi ý mở rộng: bảng thuốc để hiệu chỉnh nhiễu điều trị), `data2/NHANES Dataset/*` (< 8.100 dòng, thiếu nhãn bệnh).

Kho cuối: **38.612 bản ghi khám** (6 chu kỳ), **12.505 bản ghi dinh dưỡng**.

## Chạy hệ thống
Yêu cầu: Python 3.12, MySQL Server 8.0 đang chạy (MySQL Workbench chỉ là công cụ xem dữ liệu).
Sao chép `.env.example` thành `.env` và điền `MYSQL_PASSWORD`; database `cvd_dw` được tạo tự động.
```bash
pip install -r requirements.txt
python -m src.etl.run_etl        # Extract-Transform-Load  -> database MySQL `cvd_dw`
python -m src.dss.risk_model     # huấn luyện mô hình nguy cơ -> warehouse/risk_model.joblib
-     # dashboard + OLAP + DSS
python -m pytest tests -q        # kiểm thử ETL/OLAP/DSS (cần đã chạy ETL)
```

## Cấu trúc
```
data/raw/            dữ liệu nguồn
src/config.py        đường dẫn, khoảng giá trị hợp lệ
src/etl/             extract.py · dimensions.py · transform.py · run_etl.py (load)
src/sql/             schema.sql (DDL), materialize.sql (bảng phẳng olap_exam), truy_van_olap.sql (22 truy vấn OLAP mẫu, mở bằng MySQL Workbench)
src/db.py            kết nối MySQL (SQLAlchemy + PyMySQL), phiên chỉ đọc cho dashboard
src/olap.py          slice/dice, pivot, rollup/cube, drill-down (whitelist chống SQL injection)
src/dss/             risk_model.py (ML) · engine.py (đánh giá cá nhân, what-if, phân bổ ngân sách, cảnh báo xu hướng)
src/app/             Streamlit: 5 trang
tests/               kiểm thử toàn tuyến
report/              báo cáo LaTeX (main.tex) và PDF (BaoCao_CO4031.pdf)
```

## Thiết kế kho dữ liệu
* **Grain** `fact_health_exam`: 1 người ≥ 20 tuổi được khám trong 1 chu kỳ. `fact_nutrition`: 1 người có dữ liệu ăn uống 24h.
* **Dimension** (conformed): cycle, sex, race, education, income, age_group, bmi_category, bp_category, chol_category, cvd_profile (junk dim).
  Mỗi dimension có phân cấp (vd. life_stage → age_group; bp_group → bp_category) phục vụ drill-down.
* **Bus matrix**

| Dimension | fact_health_exam | fact_nutrition |
|---|:-:|:-:|
| cycle | ✓ | ✓ |
| age_group | ✓ | ✓ |
| bmi_category | ✓ | ✓ |
| bp_category | ✓ | ✓ |
| cvd_profile | ✓ | ✓ |
| sex, race, education, income, chol_category | ✓ | – |

* **ETL** xử lý: lọc người lớn; trung bình huyết áp các lần đo 2-4 theo quy ước CDC, bỏ lần đo đầu (loại DBP = 0); mã Yes/No → 0/1/NULL (7, 9 → NULL); loại outlier ngoài khoảng sinh lý (ghi `etl_log`); suy ra chu kỳ của nguồn CSV từ SEQN; phân lớp ACC/AHA 2017 (huyết áp), WHO (BMI), ATP III (cholesterol); thành viên `Unknown` (key 0) cho mọi dimension.

## DSS
1. **Nguy cơ cá nhân** – logistic regression (AUC ≈ 0.79 trên tập kiểm tra) + khuyến nghị theo luật ACC/AHA, ATP III.
2. **What-if** – áp RR từ y văn (huyết áp: Ettehad 2016; cholesterol: CTT 2010; BMI: giả định minh hoạ; tất cả chỉnh được trên giao diện) lên nguy cơ nền từng người trong DW.
3. **Phân bổ ngân sách** – xếp hạng phân khúc theo ca-tránh-được/chi phí, lấp đầy ngân sách (knapsack phân số); so sánh với chia đều (mặc định 2 triệu USD cho 100.000 người, hiệu quả thực tế 60%: 348 ca vs 87 ca).
4. **Cảnh báo xu hướng** – kiểm định z hai tỷ lệ giữa hai chu kỳ cho từng nhóm.
