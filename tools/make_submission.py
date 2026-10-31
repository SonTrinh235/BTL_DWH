"""Đóng gói bài nộp:  python tools/make_submission.py [--slides duong_dan/slide.pdf]

Tạo dist/NopBai_CO4031.zip gồm: báo cáo PDF, src/, data/, slide PDF (nếu có), cùng README, requirements,
.env.example và tests/ để người chấm chạy lại được. TUYỆT ĐỐI không đưa .env (chứa mật khẩu MySQL),
warehouse/, __pycache__ vào file nộp.
"""
import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "report" / "BaoCao_CO4031.pdf"
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", "warehouse", ".git", "dist"}
EXCLUDE_NAMES = {".env"}


def add_tree(z: zipfile.ZipFile, folder: Path, arc_root: str) -> int:
    n = 0
    for f in sorted(folder.rglob("*")):
        if f.is_dir() or EXCLUDE_DIRS & set(f.relative_to(ROOT).parts) or f.name in EXCLUDE_NAMES:
            continue
        if f.suffix in {".pyc", ".joblib"}:
            continue
        z.write(f, f"{arc_root}/{f.relative_to(folder).as_posix()}")
        n += 1
    return n


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252 không in được tiếng Việt
    ap = argparse.ArgumentParser()
    ap.add_argument("--slides", type=Path, help="file slide thuyết trình (PDF)")
    args = ap.parse_args()

    problems = []
    if not REPORT.exists():
        problems.append(f"thiếu báo cáo: {REPORT}")
    if not args.slides or not args.slides.exists():
        problems.append("chưa có slide PDF (dùng --slides file.pdf); file ZIP vẫn được tạo nhưng CHƯA ĐỦ")

    out = ROOT / "dist" / "NopBai_CO4031.zip"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        if REPORT.exists():
            z.write(REPORT, "BaoCao_CO4031.pdf")
        if args.slides and args.slides.exists():
            z.write(args.slides, "Slide_CO4031.pdf")
        counts = {"src": add_tree(z, ROOT / "src", "src"), "data": add_tree(z, ROOT / "data", "data"),
                  "tests": add_tree(z, ROOT / "tests", "tests")}
        for name in ("README.md", "requirements.txt", ".env.example", ".gitignore"):
            if (ROOT / name).exists():
                z.write(ROOT / name, name)
        names = z.namelist()

    assert not any(n.endswith(".env") for n in names), "ZIP chứa .env!"
    print(f"Đã tạo {out} ({out.stat().st_size / 1e6:.1f} MB), {len(names)} file: {counts}")
    for p in problems:
        print("CẢNH BÁO:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
