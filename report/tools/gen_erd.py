"""Sinh hình ERD (TikZ) của star schema từ danh sách bảng/cột.
Chạy:  python report/tools/gen_erd.py   -> report/figures/erd_health.tex, erd_nutrition.tex
Thông tin cột lấy theo src/sql/schema.sql (rút gọn nhóm measure để vừa trang).
"""
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "figures"

COLORS = {"cycle": "green", "sex": "blue", "race": "blue", "edu": "blue", "inc": "blue", "age": "violet",
          "bmi": "orange", "bp": "red", "chol": "orange", "cvd": "magenta", "fact": "cyan"}


def esc(s: str) -> str:
    return s.replace("_", r"\_")


def rows(items):
    """items: (khóa, tên, kiểu). khóa in {'PK','FK','PK,FK',''}"""
    body = r"\\".join(f"{k}&{esc(n)}&{t}" for k, n, t in items)
    return r"\begin{tabular}{@{}l@{\ }l@{\ \ }l@{}}" + body + r"\end{tabular}"


DIMS = {
    "cycle": ("dim\\_cycle", [("PK", "cycle_key", "int"), ("", "cycle_label", "varchar"), ("", "start_year", "int"),
                              ("", "end_year", "int"), ("", "period_group", "varchar"), ("", "source_system", "varchar")]),
    "sex": ("dim\\_sex", [("PK", "sex_key", "int"), ("", "sex", "varchar")]),
    "race": ("dim\\_race", [("PK", "race_key", "int"), ("", "race", "varchar"), ("", "race_group", "varchar")]),
    "edu": ("dim\\_education", [("PK", "education_key", "int"), ("", "education", "varchar"),
                                ("", "education_level", "varchar")]),
    "inc": ("dim\\_income", [("PK", "income_key", "int"), ("", "income_band", "varchar"), ("", "sort_order", "int")]),
    "age": ("dim\\_age\\_group", [("PK", "age_group_key", "int"), ("", "age_group", "varchar"),
                                  ("", "life_stage", "varchar"), ("", "min_age", "int"), ("", "max_age", "int")]),
    "bmi": ("dim\\_bmi\\_category", [("PK", "bmi_category_key", "int"), ("", "bmi_category", "varchar"),
                                     ("", "weight_status", "varchar"), ("", "sort_order", "int")]),
    "bp": ("dim\\_bp\\_category", [("PK", "bp_category_key", "int"), ("", "bp_category", "varchar"),
                                   ("", "bp_group", "varchar"), ("", "sort_order", "int")]),
    "chol": ("dim\\_chol\\_category", [("PK", "chol_category_key", "int"), ("", "chol_category", "varchar"),
                                       ("", "sort_order", "int")]),
    "cvd": ("dim\\_cvd\\_profile", [("PK", "cvd_profile_key", "int"), ("", "chf", "varchar"), ("", "chd", "varchar"),
                                    ("", "angina", "varchar"), ("", "heart_attack", "varchar"),
                                    ("", "stroke", "varchar"), ("", "n_conditions", "int"),
                                    ("", "profile_label", "varchar"), ("", "cvd_group", "varchar")]),
}

HEALTH_ROWS = [("PK", "exam_id", "bigint"), ("FK", "cycle_key", "int"), ("FK", "sex_key", "int"),
               ("FK", "race_key", "int"), ("FK", "education_key", "int"), ("FK", "income_key", "int"),
               ("FK", "age_group_key", "int"), ("FK", "bmi_category_key", "int"), ("FK", "bp_category_key", "int"),
               ("FK", "chol_category_key", "int"), ("FK", "cvd_profile_key", "int"),
               ("", "age_years, sbp, dbp, pulse", "double"), ("", "bmi, waist_cm, weight_kg, height_cm", "double"),
               ("", "total_chol, hdl_chol, non_hdl_chol", "double"), ("", "crp_mgl, income_ratio, mec_weight", "double"),
               ("", "has_cvd, is_hypertensive, is_obese", "tinyint"), ("", "is_high_chol, is_low_hdl", "tinyint")]

NUT_ROWS = [("PK,FK", "exam_id", "bigint"), ("FK", "cycle_key", "int"), ("FK", "age_group_key", "int"),
            ("FK", "bmi_category_key", "int"), ("FK", "bp_category_key", "int"), ("FK", "cvd_profile_key", "int"),
            ("", "protein_g, carbohydrate_g, sugar_g, fiber_g", "double"),
            ("", "saturated_fat_g, monounsat_fat_g, polyunsat_fat_g", "double"),
            ("", "dietary_chol_mg, sodium_mg, potassium_mg", "double"),
            ("", "calcium_mg, magnesium_mg, vitamin_d_mcg", "double"), ("", "na_k_ratio", "double"),
            ("", "high_sodium, low_fiber", "tinyint")]

PREAMBLE = r"""\providecommand{\erdsize}{\scriptsize}
\tikzset{
  erd/.style={rectangle split, rectangle split parts=2, align=left, inner sep=3pt, font=\erdsize, line width=0.6pt},
  rel/.style={black!65, line width=0.7pt, {Bar[width=4pt]}-{Rays[n=3,length=5pt]}},
}
"""


def card(name, pos, color, title, items):
    return (rf"\node[erd, draw={color}!65!black, rectangle split part fill={{{color}!38,{color}!7}}] ({name}) at ({pos}) "
            rf"{{\textbf{{{title}}}\nodepart{{two}}{rows(items)}}};")


def health() -> str:
    lines = [PREAMBLE, r"\begin{tikzpicture}[x=1cm,y=1cm]"]
    top = ["cycle", "age", "bmi", "bp", "cvd"]
    bottom = ["sex", "race", "edu", "inc", "chol"]
    xs = [-10.4, -5.2, 0, 5.2, 10.4]
    for k, x in zip(top, xs):
        lines.append(card(k, f"{x},4.9", COLORS[k], *DIMS[k]))
    for k, x in zip(bottom, xs):
        lines.append(card(k, f"{x},-4.9", COLORS[k], *DIMS[k]))
    lines.append(card("fact", "0,0", COLORS["fact"], "fact\\_health\\_exam", HEALTH_ROWS).replace("rectangle split part fill", "line width=1.2pt, rectangle split part fill"))
    for i, k in enumerate(top):
        lines.append(rf"\draw[rel] ({k}.south) -- ($(fact.north west)!{0.1 + 0.2 * i}!(fact.north east)$);")
    for i, k in enumerate(bottom):
        lines.append(rf"\draw[rel] ({k}.north) -- ($(fact.south west)!{0.1 + 0.2 * i}!(fact.south east)$);")
    lines.append(r"\end{tikzpicture}")
    return "\n".join(lines)


def nutrition() -> str:
    lines = [PREAMBLE, r"\begin{tikzpicture}[x=1cm,y=1cm]"]
    top = ["cycle", "age", "bmi", "bp", "cvd"]
    xs = [-10.4, -5.2, 0, 5.2, 10.4]
    for k, x in zip(top, xs):
        lines.append(card(k, f"{x},4.2", COLORS[k], *DIMS[k]))
    lines.append(card("fact", "0,0.2", COLORS["fact"], "fact\\_nutrition", NUT_ROWS).replace("rectangle split part fill", "line width=1.2pt, rectangle split part fill"))
    lines.append(card("fh", "0,-4.6", "gray", "fact\\_health\\_exam (xem Hình~\\ref{fig:erd_health})",
                      [("PK", "exam_id", "bigint"), ("", "... (36 cột)", "")]))
    for i, k in enumerate(top):
        lines.append(rf"\draw[rel] ({k}.south) -- ($(fact.north west)!{0.1 + 0.2 * i}!(fact.north east)$);")
    lines.append(r"\draw[rel] (fh.north) -- (fact.south);")
    lines.append(r"\node[font=\erdsize\itshape, right=2pt] at ($(fact.south)!0.5!(fh.north)$) {exam\_id (FK)};")
    lines.append(r"\end{tikzpicture}")
    return "\n".join(lines)


NUT_ROWS_SHORT = [("PK,FK", "exam_id", "bigint"), ("FK", "cycle_key", "int"), ("FK", "age_group_key", "int"),
                  ("FK", "bmi_category_key", "int"), ("FK", "bp_category_key", "int"), ("FK", "cvd_profile_key", "int"),
                  ("", "protein, carbohydrate, sugar, fiber (g)", "double"),
                  ("", "saturated/mono/polyunsat fat (g)", "double"),
                  ("", "dietary_chol, sodium, potassium (mg)", "double"),
                  ("", "calcium, magnesium (mg), vitamin_d (mcg)", "double"),
                  ("", "na_k_ratio", "double"), ("", "high_sodium, low_fiber", "tinyint")]


def combined() -> str:
    """Một hình ERD cho cả 2 fact: 5 dimension dùng chung ở hàng trên, 5 dimension riêng của fact_health_exam ở hàng dưới."""
    lines = [PREAMBLE, r"\begin{tikzpicture}[x=1cm,y=1cm]"]
    top = ["cycle", "age", "bmi", "bp", "cvd"]
    bottom = ["sex", "race", "edu", "inc", "chol"]
    for k, x in zip(top, [-10.6, -5.3, 0, 5.3, 10.6]):
        lines.append(card(k, f"{x},5.6", COLORS[k], *DIMS[k]))
    for k, x in zip(bottom, [-12.2, -8.1, -4.0, 0.1, 4.2]):
        lines.append(card(k, f"{x},-5.0", COLORS[k], *DIMS[k]))
    lines.append(card("fact", "-4.2,-0.1", COLORS["fact"], "fact\\_health\\_exam", HEALTH_ROWS)
                 .replace("rectangle split part fill", "line width=1.2pt, rectangle split part fill"))
    lines.append(card("fn", "7.0,0.4", COLORS["fact"], "fact\\_nutrition", NUT_ROWS_SHORT)
                 .replace("rectangle split part fill", "line width=1.2pt, rectangle split part fill"))
    for i, k in enumerate(top):
        lines.append(rf"\draw[rel] ({k}.south) -- ($(fact.north west)!{0.1 + 0.2 * i}!(fact.north east)$);")
    for i, k in enumerate(top):
        lines.append(rf"\draw[rel] ({k}.south) -- ($(fn.north west)!{0.1 + 0.2 * i}!(fn.north east)$);")
    for i, k in enumerate(bottom):
        lines.append(rf"\draw[rel] ({k}.north) -- ($(fact.south west)!{0.1 + 0.2 * i}!(fact.south east)$);")
    lines.append(r"\draw[rel, dashed] (fn.west) -- node[above, font=\erdsize\itshape]{exam\_id (FK)} (fact.east);")
    lines.append(r"\end{tikzpicture}")
    return "\n".join(lines)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    (OUT / "erd_health.tex").write_text(health(), encoding="utf-8")
    (OUT / "erd_nutrition.tex").write_text(nutrition(), encoding="utf-8")
    (OUT / "erd.tex").write_text(combined(), encoding="utf-8")
    print("ok")
