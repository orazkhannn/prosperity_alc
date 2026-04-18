import pandas as pd


DATA_PATH = "datasets/round1/prices_round_1_day_0.csv"
OUTPUT_PATH = "datasets/round1/orderbook_hidden_pattern_events.csv"
MIN_EVENT_COUNT = 50


def summarize_product(df: pd.DataFrame, product: str) -> pd.DataFrame:
    sub = df[df["product"] == product].copy().reset_index(drop=True)

    sub["next_bid"] = sub["bid_price_1"].shift(-1)
    sub["next_ask"] = sub["ask_price_1"].shift(-1)

    clean = sub[
        sub[["bid_price_1", "ask_price_1", "next_bid", "next_ask"]].notna().all(axis=1)
    ].copy()
    clean["next_mid"] = (clean["next_bid"] + clean["next_ask"]) / 2
    clean["dmid"] = clean["next_mid"] - clean["mid_price"]
    clean["bid_gap12"] = clean["bid_price_1"] - clean["bid_price_2"]
    clean["ask_gap12"] = clean["ask_price_2"] - clean["ask_price_1"]
    clean["gap_tilt"] = clean["ask_gap12"] - clean["bid_gap12"]

    same_v1 = (
        clean["bid_volume_1"].notna()
        & clean["ask_volume_1"].notna()
        & (clean["bid_volume_1"] == clean["ask_volume_1"])
    )
    same_v2 = (
        clean["bid_volume_2"].notna()
        & clean["ask_volume_2"].notna()
        & (clean["bid_volume_2"] == clean["ask_volume_2"])
    )

    print(f"\n=== {product} ===")
    print(f"rows: {len(sub)}")
    print(f"level-1 mirrored volume share: {same_v1.mean():.3f}")
    print(f"level-2 mirrored volume share: {same_v2.mean():.3f}")

    tilt_summary = (
        clean.dropna(subset=["bid_gap12", "ask_gap12"])
        .groupby("gap_tilt")["dmid"]
        .agg(["count", "mean", "std"])
        .sort_index()
    )

    print("\ngap_tilt -> next clean mid move")
    for tilt, row in tilt_summary.iterrows():
        if row["count"] < MIN_EVENT_COUNT:
            continue
        print(
            f"  {tilt:+.0f}: count={int(row['count'])}, "
            f"mean_next_mid_change={row['mean']:+.3f}, "
            f"std_next_mid_change={row['std']:+.3f}"
        )

    event_rows = clean.dropna(subset=["bid_gap12", "ask_gap12"]).copy()
    significant_tilts = tilt_summary[tilt_summary["count"] >= MIN_EVENT_COUNT].index.tolist()

    if not significant_tilts:
        return pd.DataFrame(
            columns=[
                "product",
                "day",
                "timestamp",
                "gap_tilt",
                "next_timestamp_mid_change",
                "mean_next_mid_change",
                "std_next_mid_change",
            ]
        )

    matching_events = event_rows[event_rows["gap_tilt"].isin(significant_tilts)].copy()
    mean_by_tilt = tilt_summary["mean"].to_dict()
    std_by_tilt = tilt_summary["std"].to_dict()
    matching_events["product"] = product
    matching_events["next_timestamp_mid_change"] = matching_events["dmid"]
    matching_events["mean_next_mid_change"] = matching_events["gap_tilt"].map(mean_by_tilt)
    matching_events["std_next_mid_change"] = matching_events["gap_tilt"].map(std_by_tilt)

    return matching_events[
        [
            "product",
            "day",
            "timestamp",
            "gap_tilt",
            "next_timestamp_mid_change",
            "mean_next_mid_change",
            "std_next_mid_change",
        ]
    ].sort_values(["gap_tilt", "timestamp"])


def main() -> None:
    df = pd.read_csv(DATA_PATH, sep=";")
    event_frames = []
    for product in df["product"].unique():
        event_frames.append(summarize_product(df, product))

    all_events = pd.concat(event_frames, ignore_index=True)
    all_events.to_csv(OUTPUT_PATH, index=False)
    print(f"\nsaved event timestamps to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
