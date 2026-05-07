import os
import re
import subprocess
import pandas as pd
from pathlib import Path

RESULTS_DIR = Path("results/grid_rwa")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TRADER = "traders/rw.py"

BASE_SIZES = [1, 2, 3, 4, 5, 6]
IMPROVEMENTS = [1, 2, 3]

product_pattern = re.compile(
    r"^\s*([A-Z0-9_]+)\s+"
    r"(-?\d+(?:\.\d+)?)\s+"
    r"(-?\d+(?:\.\d+)?)\s+"
    r"(-?\d+(?:\.\d+)?)\s+"
    r"(-?\d+(?:\.\d+)?)\s*$",
    re.MULTILINE,
)

summary_pattern = re.compile(
    r"^\s*TOTAL\s+-\s+30000\s+(\d+)\s+(-?\d+(?:\.\d+)?)",
    re.MULTILINE,
)

all_rows = []
summary_rows = []

for base_size in BASE_SIZES:
    for improvement in IMPROVEMENTS:
        print(f"Running BASE_SIZE={base_size}, IMPROVEMENT={improvement}")

        env = os.environ.copy()
        env["BASE_SIZE"] = str(base_size)
        env["IMPROVEMENT"] = str(improvement)

        result = subprocess.run(
            ["make", "round5", f"TRADER={TRADER}"],
            capture_output=True,
            text=True,
            env=env,
        )

        text = result.stdout + "\n" + result.stderr

        out_path = RESULTS_DIR / f"rwa_bs{base_size}_imp{improvement}.txt"
        out_path.write_text(text)

        if result.returncode != 0:
            print(f"WARNING: run failed for BASE_SIZE={base_size}, IMPROVEMENT={improvement}")
            print(text[-2000:])
            continue

        summary_match = summary_pattern.search(text)

        if summary_match:
            own_trades = int(summary_match.group(1))
            total_pnl = float(summary_match.group(2))
        else:
            own_trades = None
            total_pnl = None
            print(f"WARNING: could not parse summary for BASE_SIZE={base_size}, IMPROVEMENT={improvement}")

        summary_rows.append({
            "base_size": base_size,
            "improvement": improvement,
            "own_trades": own_trades,
            "total_pnl": total_pnl,
        })

        matches = list(product_pattern.finditer(text))

        if not matches:
            print(f"WARNING: no product rows parsed for BASE_SIZE={base_size}, IMPROVEMENT={improvement}")
            print("Last 2000 chars of output:")
            print(text[-2000:])

        for match in matches:
            product, d2, d3, d4, total = match.groups()

            # Avoid accidental parsing of non-product rows
            if product in {"SET", "DAY", "PRODUCT"}:
                continue

            all_rows.append({
                "base_size": base_size,
                "improvement": improvement,
                "product": product,
                "D+2": float(d2),
                "D+3": float(d3),
                "D+4": float(d4),
                "TOTAL": float(total),
            })

by_product = pd.DataFrame(all_rows)

if by_product.empty:
    raise RuntimeError(
        "No product rows were parsed. Open one of the saved txt files in results/grid_rwa/ "
        "and check whether the product table format differs from the regex."
    )

by_product["TRAIN_TOTAL"] = by_product["D+2"] + by_product["D+3"]
by_product["VALIDATION"] = by_product["D+4"]

by_product["positive_days"] = (
    (by_product["D+2"] > 0).astype(int)
    + (by_product["D+3"] > 0).astype(int)
    + (by_product["D+4"] > 0).astype(int)
)

by_product["worst_day"] = by_product[["D+2", "D+3", "D+4"]].min(axis=1)

summary = pd.DataFrame(summary_rows)

if not summary.empty:
    summary = summary.sort_values("total_pnl", ascending=False)

by_product.to_csv(
    RESULTS_DIR / "rwa_grid_by_product.csv",
    index=False,
    sep=";",
)

summary.to_csv(
    RESULTS_DIR / "rwa_grid_summary.csv",
    index=False,
    sep=";",
)

print("\n=== GRID SUMMARY ===")
print(summary.to_csv(index=False, sep="\t"))

print("\nSaved:")
print(RESULTS_DIR / "rwa_grid_by_product.csv")
print(RESULTS_DIR / "rwa_grid_summary.csv")