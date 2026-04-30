import re
import pandas as pd
from pathlib import Path

path = Path("results/rwc.txt")
text = path.read_text()

rows = []

pattern = re.compile(
    r"^([A-Z0-9_]+)\s+"
    r"(-?\d+(?:\.\d+)?)\s+"
    r"(-?\d+(?:\.\d+)?)\s+"
    r"(-?\d+(?:\.\d+)?)\s+"
    r"(-?\d+(?:\.\d+)?)$",
    re.MULTILINE,
)

for match in pattern.finditer(text):
    product, d2, d3, d4, total = match.groups()

    rows.append({
        "product": product,
        "D+2": float(d2),
        "D+3": float(d3),
        "D+4": float(d4),
        "TOTAL": float(total),
    })

pnl = pd.DataFrame(rows)
pnl = pnl.sort_values("TOTAL", ascending=False)

pnl["positive_days"] = (
    (pnl["D+2"] > 0).astype(int)
    + (pnl["D+3"] > 0).astype(int)
    + (pnl["D+4"] > 0).astype(int)
)

pnl["worst_day"] = pnl[["D+2", "D+3", "D+4"]].min(axis=1)
pnl["best_day"] = pnl[["D+2", "D+3", "D+4"]].max(axis=1)
pnl["avg_day"] = pnl[["D+2", "D+3", "D+4"]].mean(axis=1)
pnl["total"] = pnl[["D+2", "D+3", "D+4"]].sum(axis=1)

pnl["worst_to_avg"] = pnl["worst_day"] / pnl["avg_day"].abs()
filtered = pnl[
    (pnl["positive_days"] >= 2)
    & (pnl["total"] > 0)
    & (pnl["worst_day"] > -0.5 * pnl["avg_day"].abs())
]
positive_all_days = pnl[
    (pnl["D+2"] > 0)
    & (pnl["D+3"] > 0)
    & (pnl["D+4"] > 0)
].sort_values("TOTAL", ascending=False)



# print(positive_all_days.to_csv(index=False, sep="\t"))
filtered.to_clipboard(index=False, sep="\t")
print("Copied to clipboard")