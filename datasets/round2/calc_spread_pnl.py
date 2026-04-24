from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class SimulationResult:
    buys: int
    sells: int
    buy_qty: int
    sell_qty: int
    cash: float
    inventory: int
    final_mark_price: float

    @property
    def mtm_pnl(self) -> float:
        return self.cash + self.inventory * self.final_mark_price


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay round-2 ASH_COATED_OSMIUM books and buy the best ask "
            "when spread equals one value, then sell the best bid when spread equals another."
        )
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directory containing prices_round_2_day_*.csv files.",
    )
    parser.add_argument(
        "--product",
        default="ASH_COATED_OSMIUM",
        help="Product symbol to simulate.",
    )
    parser.add_argument(
        "--days",
        type=int,
        nargs="*",
        default=None,
        help="Optional subset of round-2 days to load, for example: --days -1 0",
    )
    parser.add_argument(
        "--buy-spread",
        type=float,
        default=5,
        help="Buy best ask whenever ask_price_1 - bid_price_1 equals this spread.",
    )
    parser.add_argument(
        "--sell-spread",
        type=float,
        default=7,
        help="Sell best bid whenever ask_price_1 - bid_price_1 equals this spread.",
    )
    parser.add_argument(
        "--fixed-qty",
        type=int,
        default=None,
        help="Use a fixed order size instead of the displayed level-1 volume.",
    )
    parser.add_argument(
        "--allow-short",
        action="store_true",
        help="Allow sells even when inventory is zero.",
    )
    parser.add_argument(
        "--mark-price",
        choices=("mid", "bid", "ask"),
        default="mid",
        help="Price used to mark any remaining inventory at the end.",
    )
    return parser.parse_args()


def load_prices(data_dir: Path, product: str, selected_days: list[int] | None) -> pd.DataFrame:
    price_paths = sorted(data_dir.glob("prices_round_2_day_*.csv"))
    if not price_paths:
        raise FileNotFoundError(f"No price files found in {data_dir}")

    frames: list[pd.DataFrame] = []
    for path in price_paths:
        df = pd.read_csv(path, sep=";")
        df = df[df["product"] == product].copy()
        if df.empty:
            continue
        if selected_days is not None:
            df = df[df["day"].isin(selected_days)].copy()
        if df.empty:
            continue
        df = df[df["bid_price_1"].notna() & df["ask_price_1"].notna()].copy()
        df["source_file"] = path.name
        frames.append(df)

    if not frames:
        raise ValueError(f"No rows found for product {product!r}")

    combined = pd.concat(frames, ignore_index=True)
    combined["ask_volume_1"] = combined["ask_volume_1"].fillna(0)
    combined["bid_volume_1"] = combined["bid_volume_1"].fillna(0)
    combined["spread"] = combined["ask_price_1"] - combined["bid_price_1"]
    combined["mid_price"] = (combined["ask_price_1"] + combined["bid_price_1"]) / 2
    return combined.sort_values(["day", "timestamp"]).reset_index(drop=True)


def choose_trade_qty(row: pd.Series, side: str, fixed_qty: int | None) -> int:
    if fixed_qty is not None:
        return max(fixed_qty, 0)
    volume_col = "ask_volume_1" if side == "buy" else "bid_volume_1"
    return max(int(row[volume_col]), 0)


def simulate(
    df: pd.DataFrame,
    buy_spread: float,
    sell_spread: float,
    fixed_qty: int | None,
    allow_short: bool,
    mark_price: str,
) -> SimulationResult:
    cash = 0.0
    inventory = 0
    buys = sells = buy_qty = sell_qty = 0

    for _, row in df.iterrows():
        if row["spread"] == buy_spread:
            qty = choose_trade_qty(row, side="buy", fixed_qty=fixed_qty)
            if qty > 0:
                buys += 1
                buy_qty += qty
                inventory += qty
                cash -= qty * float(row["ask_price_1"])

        if row["spread"] == sell_spread:
            requested_qty = choose_trade_qty(row, side="sell", fixed_qty=fixed_qty)
            qty = requested_qty if allow_short else min(requested_qty, inventory)
            if qty > 0:
                sells += 1
                sell_qty += qty
                inventory -= qty
                cash += qty * float(row["bid_price_1"])

    final_row = df.iloc[-1]
    if mark_price == "mid":
        final_mark_price = float(final_row["mid_price"])
    elif mark_price == "bid":
        final_mark_price = float(final_row["bid_price_1"])
    else:
        final_mark_price = float(final_row["ask_price_1"])

    return SimulationResult(
        buys=buys,
        sells=sells,
        buy_qty=buy_qty,
        sell_qty=sell_qty,
        cash=cash,
        inventory=inventory,
        final_mark_price=final_mark_price,
    )


def main() -> None:
    args = parse_args()
    df = load_prices(args.data_dir, args.product, args.days)
    result = simulate(
        df=df,
        buy_spread=args.buy_spread,
        sell_spread=args.sell_spread,
        fixed_qty=args.fixed_qty,
        allow_short=args.allow_short,
        mark_price=args.mark_price,
    )

    print(f"product: {args.product}")
    print(f"days loaded: {sorted(df['day'].unique().tolist())}")
    print(f"rows replayed: {len(df)}")
    print(f"buy spread: {args.buy_spread}")
    print(f"sell spread: {args.sell_spread}")
    print(
        "sizing: "
        + (f"fixed {args.fixed_qty}" if args.fixed_qty is not None else "level-1 displayed volume")
    )
    print(f"allow short: {args.allow_short}")
    print(f"buy fills: {result.buys} events / {result.buy_qty} units")
    print(f"sell fills: {result.sells} events / {result.sell_qty} units")
    print(f"ending inventory: {result.inventory}")
    print(f"cash: {result.cash:.2f}")
    print(f"final {args.mark_price} mark: {result.final_mark_price:.2f}")
    print(f"mark-to-market pnl: {result.mtm_pnl:.2f}")


if __name__ == "__main__":
    main()
