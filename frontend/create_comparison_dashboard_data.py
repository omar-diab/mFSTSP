import pandas as pd
from pathlib import Path

# =============================================================================
# Paths
# =============================================================================

FRONTEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = FRONTEND_DIR.parent

THEIR_FILE = PROJECT_DIR / "performance_summary_archive.csv"
OUR_FILE = PROJECT_DIR / "performance_summary.csv"

OUTPUT_DIR = FRONTEND_DIR / "frontend_data"
OUTPUT_DIR.mkdir(exist_ok=True)

OUTPUT_COMPARISON_CSV = OUTPUT_DIR / "comparison_all_100_full_dashboard.csv"
OUTPUT_COMPARISON_JSON = OUTPUT_DIR / "comparison_all_100_full_dashboard.json"
OUTPUT_SUMMARY_CSV = OUTPUT_DIR / "comparison_all_100_full_dashboard_summary.csv"
OUTPUT_SCORECARD_CSV = OUTPUT_DIR / "comparison_all_100_metric_scorecard.csv"

CUSTOMERS_TO_USE = [8, 10, 25, 50, 100]

OUR_COLUMNS = [
    "problemName",
    "vehicleFileID",
    "cutoffTime",
    "problemType",
    "problemTypeString",
    "numUAVs",
    "numTrucks",
    "requireTruckAtDepot",
    "requireDriver",
    "Etype",
    "ITER",
    "runString",
    "numCustomers",
    "timestamp",
    "ofv",
    "bestBound",
    "totalTime",
    "isOptimal",
    "numUAVcust",
    "numTruckCust",
    "waitingTruck",
    "waitingUAV",
]

METRICS = [
    "totalTime",
    "ofv",
    "waitingTruck",
    "waitingUAV",
    "numUAVcust",
    "numTruckCust",
]

LOWER_IS_BETTER = {
    "totalTime",
    "ofv",
    "waitingTruck",
    "waitingUAV",
    "numTruckCust",
}

HIGHER_IS_BETTER = {"numUAVcust"}

FULL_COLUMNS = [
    "problemName",
    "vehicleFileID",
    "cutoffTime",
    "problemType",
    "problemTypeString",
    "numUAVs",
    "numTrucks",
    "requireTruckAtDepot",
    "requireDriver",
    "Etype",
    "ITER",
    "runString",
    "numCustomers",
    "timestamp",
    "ofv",
    "bestBound",
    "totalTime",
    "isOptimal",
    "numUAVcust",
    "numTruckCust",
    "waitingTruck",
    "waitingUAV",
]


# =============================================================================
# Data cleaning
# =============================================================================

def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip()
    return df


def normalize_bool_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["requireTruckAtDepot", "requireDriver", "isOptimal"]:
        if col in df.columns:
            normalized = (
                df[col]
                .astype(str)
                .str.strip()
                .str.lower()
                .replace({
                    "true": "1",
                    "false": "0",
                    "1.0": "1",
                    "0.0": "0",
                    "1": "1",
                    "0": "0",
                    "nan": "",
                    "none": "",
                })
            )
            df[col] = pd.to_numeric(normalized, errors="coerce")
    return df


def normalize_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    numeric_cols = [
        "numCustomers",
        "vehicleFileID",
        "cutoffTime",
        "problemType",
        "numUAVs",
        "numTrucks",
        "requireTruckAtDepot",
        "requireDriver",
        "Etype",
        "ITER",
        "totalTime",
        "ofv",
        "bestBound",
        "waitingTruck",
        "waitingUAV",
        "numUAVcust",
        "numTruckCust",
        "isOptimal",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.strip(), errors="coerce")
    return df


def load_our_rows() -> pd.DataFrame:
    if not OUR_FILE.exists():
        raise FileNotFoundError(f"Missing file: {OUR_FILE}")
    return pd.read_csv(OUR_FILE, header=None, names=OUR_COLUMNS)


def load_their_rows() -> pd.DataFrame:
    if not THEIR_FILE.exists():
        raise FileNotFoundError(f"Missing file: {THEIR_FILE}")
    return pd.read_csv(THEIR_FILE)


def filter_supported_heuristic_rows(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "problemType" not in df.columns:
        raise ValueError("Missing problemType column.")
    if "numCustomers" not in df.columns:
        raise ValueError("Missing numCustomers column.")
    return df[
        (df["problemType"] == 2)
        & (df["numCustomers"].isin(CUSTOMERS_TO_USE))
    ].copy()


def keep_best_per_problem(df: pd.DataFrame) -> pd.DataFrame:
    """
    One row per actual problem instance:
      problemName + numCustomers

    If the same problem was run multiple times, keep the smallest OFV.
    """
    required = ["problemName", "numCustomers", "ofv"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df.copy()
    df = df.sort_values(
        ["problemName", "numCustomers", "ofv"],
        ascending=[True, True, True],
        na_position="last",
    )
    return df.drop_duplicates(subset=["problemName", "numCustomers"], keep="first")


def available_full_columns(df: pd.DataFrame) -> list[str]:
    return [col for col in FULL_COLUMNS if col in df.columns]


# =============================================================================
# Comparison logic
# =============================================================================

def add_difference_columns(comparison: pd.DataFrame) -> pd.DataFrame:
    comparison = comparison.copy()

    for metric in METRICS:
        our_col = f"{metric}_our"
        their_col = f"{metric}_their"

        if our_col not in comparison.columns or their_col not in comparison.columns:
            continue

        comparison[f"{metric}_diff_our_minus_their"] = comparison[our_col] - comparison[their_col]
        comparison[f"{metric}_diff_their_minus_our"] = comparison[their_col] - comparison[our_col]

        if metric in LOWER_IS_BETTER:
            comparison[f"{metric}_our_improvement_percent"] = comparison.apply(
                lambda row:
                    ((row[their_col] - row[our_col]) / row[their_col] * 100)
                    if pd.notna(row[their_col]) and row[their_col] != 0
                    else None,
                axis=1,
            )
        elif metric in HIGHER_IS_BETTER:
            comparison[f"{metric}_our_advantage_percent"] = comparison.apply(
                lambda row:
                    ((row[our_col] - row[their_col]) / abs(row[their_col]) * 100)
                    if pd.notna(row[their_col]) and row[their_col] != 0
                    else None,
                axis=1,
            )

    return comparison


def add_winner_columns(comparison: pd.DataFrame) -> pd.DataFrame:
    comparison = comparison.copy()

    for metric in METRICS:
        our_col = f"{metric}_our"
        their_col = f"{metric}_their"
        winner_col = f"{metric}_winner"

        if our_col not in comparison.columns or their_col not in comparison.columns:
            comparison[winner_col] = "missing"
            continue

        def decide(row):
            our = row[our_col]
            their = row[their_col]

            if pd.isna(our) or pd.isna(their):
                return "missing"

            if metric in LOWER_IS_BETTER:
                if our < their:
                    return "our"
                if their < our:
                    return "their"
                return "tie"

            if metric in HIGHER_IS_BETTER:
                if our > their:
                    return "our"
                if their > our:
                    return "their"
                return "tie"

            return "tie"

        comparison[winner_col] = comparison.apply(decide, axis=1)

    winner_cols = [f"{metric}_winner" for metric in METRICS if f"{metric}_winner" in comparison.columns]
    comparison["our_metric_wins"] = comparison[winner_cols].eq("our").sum(axis=1)
    comparison["their_metric_wins"] = comparison[winner_cols].eq("their").sum(axis=1)
    comparison["metric_ties"] = comparison[winner_cols].eq("tie").sum(axis=1)

    return comparison


def build_summary(comparison: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for customer_count, group in comparison.groupby("numCustomers"):
        row = {
            "numCustomers": int(customer_count),
            "matchedProblems": int(len(group)),
        }

        for metric in METRICS:
            our_col = f"{metric}_our"
            their_col = f"{metric}_their"
            winner_col = f"{metric}_winner"

            if our_col in group.columns:
                row[f"avg_{metric}_our"] = group[our_col].mean()
            if their_col in group.columns:
                row[f"avg_{metric}_their"] = group[their_col].mean()

            if winner_col in group.columns:
                row[f"{metric}_our_wins"] = int((group[winner_col] == "our").sum())
                row[f"{metric}_their_wins"] = int((group[winner_col] == "their").sum())
                row[f"{metric}_ties"] = int((group[winner_col] == "tie").sum())

            improvement_col = f"{metric}_our_improvement_percent"
            advantage_col = f"{metric}_our_advantage_percent"

            if improvement_col in group.columns:
                row[f"avg_{metric}_our_improvement_percent"] = group[improvement_col].mean()
            if advantage_col in group.columns:
                row[f"avg_{metric}_our_advantage_percent"] = group[advantage_col].mean()

        rows.append(row)

    return pd.DataFrame(rows).sort_values("numCustomers")


def build_scorecard(comparison: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for metric in METRICS:
        winner_col = f"{metric}_winner"
        our_col = f"{metric}_our"
        their_col = f"{metric}_their"

        if winner_col not in comparison.columns:
            continue

        row = {
            "metric": metric,
            "our_wins": int((comparison[winner_col] == "our").sum()),
            "their_wins": int((comparison[winner_col] == "their").sum()),
            "ties": int((comparison[winner_col] == "tie").sum()),
            "missing": int((comparison[winner_col] == "missing").sum()),
            "avg_our": comparison[our_col].mean() if our_col in comparison.columns else None,
            "avg_their": comparison[their_col].mean() if their_col in comparison.columns else None,
        }

        improvement_col = f"{metric}_our_improvement_percent"
        advantage_col = f"{metric}_our_advantage_percent"

        if improvement_col in comparison.columns:
            row["avg_our_improvement_percent"] = comparison[improvement_col].mean()
        if advantage_col in comparison.columns:
            row["avg_our_advantage_percent"] = comparison[advantage_col].mean()

        rows.append(row)

    return pd.DataFrame(rows)


# =============================================================================
# Main
# =============================================================================

def main():
    ours = load_our_rows()
    theirs = load_their_rows()

    ours = normalize_numeric_columns(normalize_bool_columns(clean_columns(ours)))
    theirs = normalize_numeric_columns(normalize_bool_columns(clean_columns(theirs)))

    ours = filter_supported_heuristic_rows(ours)
    theirs = filter_supported_heuristic_rows(theirs)

    print("\nLoaded heuristic rows:")
    print(f"Our rows: {len(ours)}")
    print(f"Their rows: {len(theirs)}")

    ours_best = keep_best_per_problem(ours)
    theirs_best = keep_best_per_problem(theirs)

    print("\nRows after keeping best OFV per problem:")
    print(f"Our best rows: {len(ours_best)}")
    print(f"Their best rows: {len(theirs_best)}")

    keys = ["problemName", "numCustomers"]
    ours_cols = list(dict.fromkeys(keys + available_full_columns(ours_best)))
    theirs_cols = list(dict.fromkeys(keys + available_full_columns(theirs_best)))

    comparison = pd.merge(
        ours_best[ours_cols],
        theirs_best[theirs_cols],
        on=keys,
        suffixes=("_our", "_their"),
        how="inner",
    )

    if comparison.empty:
        raise ValueError("No matched problems found between our results and their archived results.")

    comparison = add_difference_columns(comparison)
    comparison = add_winner_columns(comparison)
    comparison = comparison.sort_values(["numCustomers", "problemName"]).reset_index(drop=True)

    summary = build_summary(comparison)
    scorecard = build_scorecard(comparison)

    comparison.to_csv(OUTPUT_COMPARISON_CSV, index=False)
    comparison.to_json(OUTPUT_COMPARISON_JSON, orient="records", indent=2)
    summary.to_csv(OUTPUT_SUMMARY_CSV, index=False)
    scorecard.to_csv(OUTPUT_SCORECARD_CSV, index=False)

    print("\nDone.")
    print(f"Comparison CSV: {OUTPUT_COMPARISON_CSV}")
    print(f"Comparison JSON: {OUTPUT_COMPARISON_JSON}")
    print(f"Summary CSV: {OUTPUT_SUMMARY_CSV}")
    print(f"Scorecard CSV: {OUTPUT_SCORECARD_CSV}")


if __name__ == "__main__":
    main()
