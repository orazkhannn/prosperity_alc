import re
import pandas as pd
from pathlib import Path

path = Path("results/rw_a1_terminal.txt")
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

pnl_by_product = pd.DataFrame(rows)

pnl_by_product = pnl_by_product.sort_values("TOTAL", ascending=False)

pnl_by_product.to_csv("results/rw_a1_pnl_by_product.csv", index=False, sep=";")