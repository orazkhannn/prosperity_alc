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

# Sort products by total PnL
pnl_by_product = pnl_by_product.sort_values("TOTAL", ascending=False)

# Add total row at the bottom
total_row = pd.DataFrame([{
    "product": "TOTAL",
    "D+2": pnl_by_product["D+2"].sum(),
    "D+3": pnl_by_product["D+3"].sum(),
    "D+4": pnl_by_product["D+4"].sum(),
    "TOTAL": pnl_by_product["TOTAL"].sum(),
}])

pnl_by_product_with_total = pd.concat(
    [pnl_by_product, total_row],
    ignore_index=True
)

pnl_by_product_with_total.to_csv(
    "results/rwa.csv",
    index=False,
    sep="\t"
)