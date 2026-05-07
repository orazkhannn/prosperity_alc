from pathlib import Path
import pandas as pd


GRID_DIR = Path("results/grid_rwa")

SUMMARY_PATH = GRID_DIR / "rwa_grid_summary.csv"
BY_PRODUCT_PATH = GRID_DIR / "rwa_grid_by_product.csv"

OUT_DIR = GRID_DIR / "analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def add_metrics(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["TRAIN_TOTAL"] = df["D+2"] + df["D+3"]
    df["VALIDATION"] = df["D+4"]

    df["positive_days"] = (
        (df["D+2"] > 0).astype(int)
        + (df["D+3"] > 0).astype(int)
        + (df["D+4"] > 0).astype(int)
    )

    df["worst_day"] = df[["D+2", "D+3", "D+4"]].min(axis=1)
    df["best_day"] = df[["D+2", "D+3", "D+4"]].max(axis=1)
    df["avg_day"] = df[["D+2", "D+3", "D+4"]].mean(axis=1)

    # Penalizes high total PnL with one very bad day
    df["stability_score"] = df["TOTAL"] + 0.5 * df["worst_day"]

    # Validation ratio:
    # > 0 means validation agrees with train direction.
    # Near 1 means D+4 is roughly half of D+2+D+3, which is reasonable.
    df["validation_ratio"] = df["VALIDATION"] / df["TRAIN_TOTAL"].replace(0, pd.NA)

    return df


def analyze_global_params(by_product: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        by_product
        .groupby(["base_size", "improvement"], as_index=False)
        .agg(
            D2=("D+2", "sum"),
            D3=("D+3", "sum"),
            D4=("D+4", "sum"),
            TOTAL=("TOTAL", "sum"),
            TRAIN_TOTAL=("TRAIN_TOTAL", "sum"),
            VALIDATION=("VALIDATION", "sum"),
            avg_product_total=("TOTAL", "mean"),
            median_product_total=("TOTAL", "median"),
            min_product_total=("TOTAL", "min"),
            positive_product_count=("TOTAL", lambda x: (x > 0).sum()),
            product_count=("product", "count"),
            avg_positive_days=("positive_days", "mean"),
            worst_product_day=("worst_day", "min"),
        )
    )

    grouped["positive_product_fraction"] = (
        grouped["positive_product_count"] / grouped["product_count"]
    )

    grouped["validation_ratio"] = (
        grouped["VALIDATION"] / grouped["TRAIN_TOTAL"].replace(0, pd.NA)
    )

    grouped["global_stability_score"] = (
        grouped["TOTAL"]
        + 0.50 * grouped["D2"].clip(upper=0)
        + 0.50 * grouped["D3"].clip(upper=0)
        + 0.75 * grouped["D4"].clip(upper=0)
        + 0.25 * grouped["worst_product_day"].clip(upper=0)
    )

    return grouped.sort_values("global_stability_score", ascending=False)


def select_best_per_product_by_train(by_product: pd.DataFrame) -> pd.DataFrame:
    """
    Choose params using only D+2 + D+3.
    D+4 is left as validation.
    """
    selected = (
        by_product
        .sort_values(["product", "TRAIN_TOTAL"], ascending=[True, False])
        .groupby("product", as_index=False)
        .head(1)
        .sort_values("TRAIN_TOTAL", ascending=False)
    )

    selected["selection_rule"] = "best_train_D2_D3"

    return selected


def select_best_per_product_stable(by_product: pd.DataFrame) -> pd.DataFrame:
    """
    Alternative selection: use a stability-aware score.
    This still uses all days, so do not treat it as clean validation.
    Useful as a sanity-check table.
    """
    selected = (
        by_product
        .sort_values(["product", "stability_score"], ascending=[True, False])
        .groupby("product", as_index=False)
        .head(1)
        .sort_values("stability_score", ascending=False)
    )

    selected["selection_rule"] = "best_stability_all_days"

    return selected


def classify_selected(selected: pd.DataFrame) -> pd.DataFrame:
    selected = selected.copy()

    def label(row):
        if row["D+2"] > 0 and row["D+3"] > 0 and row["D+4"] > 0:
            return "strong_keep"

        if row["TRAIN_TOTAL"] > 0 and row["VALIDATION"] > 0 and row["positive_days"] >= 2:
            return "keep"

        if row["TRAIN_TOTAL"] > 0 and row["VALIDATION"] > -0.25 * row["TRAIN_TOTAL"]:
            return "borderline_keep"

        if row["TRAIN_TOTAL"] > 0 and row["VALIDATION"] <= -0.25 * row["TRAIN_TOTAL"]:
            return "train_good_validation_bad"

        return "reject"

    selected["decision"] = selected.apply(label, axis=1)

    return selected


def print_section(title: str):
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def main():
    if not SUMMARY_PATH.exists():
        raise FileNotFoundError(f"Missing file: {SUMMARY_PATH}")

    if not BY_PRODUCT_PATH.exists():
        raise FileNotFoundError(f"Missing file: {BY_PRODUCT_PATH}")

    summary = pd.read_csv(SUMMARY_PATH, sep=";")
    by_product = pd.read_csv(BY_PRODUCT_PATH, sep=";")

    # Remove accidental TOTAL rows if parser captured any
    by_product = by_product[by_product["product"] != "TOTAL"].copy()

    by_product = add_metrics(by_product)

    # ------------------------------------------------------------------
    # 1. Global parameter analysis
    # ------------------------------------------------------------------

    global_params = analyze_global_params(by_product)

    global_params.to_csv(
        OUT_DIR / "global_param_analysis.csv",
        index=False,
        sep=";",
    )

    print_section("BEST GLOBAL PARAMS BY STABILITY SCORE")
    print(
        global_params[
            [
                "base_size",
                "improvement",
                "D2",
                "D3",
                "D4",
                "TOTAL",
                "TRAIN_TOTAL",
                "VALIDATION",
                "validation_ratio",
                "positive_product_fraction",
                "global_stability_score",
            ]
        ]
        .head(20)
        .to_csv(index=False, sep="\t")
    )

    print_section("BEST GLOBAL PARAMS BY TOTAL PNL")
    print(
        global_params
        .sort_values("TOTAL", ascending=False)[
            [
                "base_size",
                "improvement",
                "D2",
                "D3",
                "D4",
                "TOTAL",
                "TRAIN_TOTAL",
                "VALIDATION",
                "validation_ratio",
                "positive_product_fraction",
            ]
        ]
        .head(20)
        .to_csv(index=False, sep="\t")
    )

    print_section("BEST GLOBAL PARAMS BY TRAIN TOTAL; VALIDATE ON D+4")
    print(
        global_params
        .sort_values("TRAIN_TOTAL", ascending=False)[
            [
                "base_size",
                "improvement",
                "D2",
                "D3",
                "D4",
                "TRAIN_TOTAL",
                "VALIDATION",
                "TOTAL",
                "validation_ratio",
                "positive_product_fraction",
            ]
        ]
        .head(20)
        .to_csv(index=False, sep="\t")
    )

    # ------------------------------------------------------------------
    # 2. Product-level selection by train only
    # ------------------------------------------------------------------

    best_by_train = select_best_per_product_by_train(by_product)
    best_by_train = classify_selected(best_by_train)

    best_by_train.to_csv(
        OUT_DIR / "best_per_product_by_train.csv",
        index=False,
        sep=";",
    )

    print_section("BEST PARAMS PER PRODUCT USING D+2 + D+3 ONLY")
    print(
        best_by_train[
            [
                "product",
                "base_size",
                "improvement",
                "D+2",
                "D+3",
                "D+4",
                "TRAIN_TOTAL",
                "VALIDATION",
                "TOTAL",
                "positive_days",
                "worst_day",
                "decision",
            ]
        ]
        .sort_values("TRAIN_TOTAL", ascending=False)
        .to_csv(index=False, sep="\t")
    )

    # ------------------------------------------------------------------
    # 3. Product-level selection by stability score
    # ------------------------------------------------------------------

    best_stable = select_best_per_product_stable(by_product)
    best_stable = classify_selected(best_stable)

    best_stable.to_csv(
        OUT_DIR / "best_per_product_by_stability.csv",
        index=False,
        sep=";",
    )

    print_section("BEST PARAMS PER PRODUCT BY STABILITY SCORE")
    print(
        best_stable[
            [
                "product",
                "base_size",
                "improvement",
                "D+2",
                "D+3",
                "D+4",
                "TOTAL",
                "positive_days",
                "worst_day",
                "stability_score",
                "decision",
            ]
        ]
        .sort_values("stability_score", ascending=False)
        .to_csv(index=False, sep="\t")
    )

    # ------------------------------------------------------------------
    # 4. Robust picks from train-selected table
    # ------------------------------------------------------------------

    strong_keep = best_by_train[best_by_train["decision"] == "strong_keep"].copy()
    keep_or_better = best_by_train[
        best_by_train["decision"].isin(["strong_keep", "keep"])
    ].copy()

    usable = best_by_train[
        best_by_train["decision"].isin(["strong_keep", "keep", "borderline_keep"])
    ].copy()

    strong_keep.to_csv(
        OUT_DIR / "strong_keep_products.csv",
        index=False,
        sep=";",
    )

    keep_or_better.to_csv(
        OUT_DIR / "keep_products.csv",
        index=False,
        sep=";",
    )

    usable.to_csv(
        OUT_DIR / "usable_products.csv",
        index=False,
        sep=";",
    )

    print_section("ROBUST PRODUCTS: POSITIVE ALL 3 DAYS")
    print(
        strong_keep[
            [
                "product",
                "base_size",
                "improvement",
                "D+2",
                "D+3",
                "D+4",
                "TOTAL",
                "decision",
            ]
        ]
        .sort_values("TOTAL", ascending=False)
        .to_csv(index=False, sep="\t")
    )

    print_section("USABLE PRODUCTS: TRAIN GOOD, VALIDATION NOT BAD")
    print(
        usable[
            [
                "product",
                "base_size",
                "improvement",
                "D+2",
                "D+3",
                "D+4",
                "TRAIN_TOTAL",
                "VALIDATION",
                "TOTAL",
                "positive_days",
                "worst_day",
                "decision",
            ]
        ]
        .sort_values("TOTAL", ascending=False)
        .to_csv(index=False, sep="\t")
    )

    # ------------------------------------------------------------------
    # 5. Danger table: params picked by train that fail validation
    # ------------------------------------------------------------------

    validation_bad = best_by_train[
        best_by_train["decision"] == "train_good_validation_bad"
    ].copy()

    validation_bad.to_csv(
        OUT_DIR / "validation_bad_products.csv",
        index=False,
        sep=";",
    )

    print_section("WARNING: TRAIN GOOD BUT VALIDATION BAD")
    print(
        validation_bad[
            [
                "product",
                "base_size",
                "improvement",
                "D+2",
                "D+3",
                "D+4",
                "TRAIN_TOTAL",
                "VALIDATION",
                "TOTAL",
                "decision",
            ]
        ]
        .sort_values("VALIDATION")
        .to_csv(index=False, sep="\t")
    )

    # ------------------------------------------------------------------
    # 6. Combined recommendation summary
    # ------------------------------------------------------------------

    recommended = usable[
        [
            "product",
            "base_size",
            "improvement",
            "D+2",
            "D+3",
            "D+4",
            "TRAIN_TOTAL",
            "VALIDATION",
            "TOTAL",
            "positive_days",
            "worst_day",
            "decision",
        ]
    ].copy()

    recommended = recommended.sort_values(
        ["decision", "TOTAL"],
        ascending=[True, False],
    )

    recommended.to_csv(
        OUT_DIR / "recommended_product_params.csv",
        index=False,
        sep=";",
    )

    print_section("OUTPUT FILES WRITTEN")
    for path in sorted(OUT_DIR.glob("*.csv")):
        print(path)


if __name__ == "__main__":
    main()