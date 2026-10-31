# Dữ liệu mẫu

Dữ liệu nguồn của đề tài (NHANES - National Health and Nutrition Examination Survey, CDC/NCHS, Hoa Kỳ; https://www.cdc.gov/nchs/nhanes/).
Chạy `python -m src.etl.run_etl` để nạp các file này vào MySQL (xem README.md ở thư mục gốc).

| Đường dẫn | Nội dung |
|---|---|
| `raw/nhanes/*.XPT` (tải từ `https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/<năm>/DataFiles/<TÊN>_<hậu tố>.XPT`) | 24 file SAS transport: 6 thành phần (DEMO, BMX, BPX, HDL, TCHOL, MCQ) x 4 chu kỳ. Hậu tố G = 2011-2012, H = 2013-2014, I = 2015-2016, J = 2017-2018 |
| `raw/nhanes_cvd_2017_23/Nhanes_cvd_raw.csv` (bản tổng hợp từ dữ liệu NHANES của CDC, tải từ mirror Kaggle - **điền URL**) | 27.493 dòng x 47 cột: khẩu phần ăn 24 giờ, CRP, vòng eo, huyết áp, cholesterol, nhãn 5 bệnh tim mạch (2017-2023) |

Dung lượng khoảng 63 MB. Các file này là dữ liệu công khai, không chứa thông tin định danh cá nhân.
