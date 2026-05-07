import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

THEIR_FILE = BASE_DIR / "performance_summary_archive.csv"
OUR_FILE = BASE_DIR / "performance_summary.csv"

OUTPUT_DIR = BASE_DIR / "frontend_data"
OUTPUT_DIR.mkdir(exist_ok=True)

OUTPUT_JSON = OUTPUT_DIR / "comparison_all_100.json"
OUTPUT_CSV = OUTPUT_DIR / "comparison_all_100.csv"
OUTPUT_SUMMARY_CSV = OUTPUT_DIR / "comparison_all_100_summary.csv"

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


def clean_columns(df):
    df.columns = df.columns.astype(str).str.strip()
    return df


def normalize_bool_columns(df):
    for col in ["requireTruckAtDepot", "requireDriver", "isOptimal"]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .str.lower()
                .replace({
                    "true": 1,
                    "false": 0,
                    "1": 1,
                    "0": 0,
                })
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def normalize_numeric_columns(df):
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
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.strip(), errors="coerce")

    return df


def keep_best_per_problem(df):
    """
    Keep one row per actual problem:
    problemName + numCustomers.

    If the same problem appears many times, keep the best OFV.
    This is what we need for frontend comparison of all 100 problems.
    """
    keys = ["problemName", "numCustomers"]

    df = df.copy()
    df = df.sort_values(keys + ["ofv"], ascending=True)
    df = df.drop_duplicates(subset=keys, keep="first")

    return df


def add_difference_columns(comparison):
    lower_is_better = ["totalTime", "ofv", "waitingTruck", "waitingUAV"]

    for metric in METRICS:
        our_col = f"{metric}_our"
        their_col = f"{metric}_their"

        comparison[f"{metric}_diff_our_minus_their"] = (
            comparison[our_col] - comparison[their_col]
        )

        comparison[f"{metric}_diff_their_minus_our"] = (
            comparison[their_col] - comparison[our_col]
        )

        if metric in lower_is_better:
            comparison[f"{metric}_our_improvement_percent"] = comparison.apply(
                lambda row:
                    ((row[their_col] - row[our_col]) / row[their_col] * 100)
                    if pd.notna(row[their_col]) and row[their_col] != 0
                    else None,
                axis=1
            )

    return comparison


def add_winner_columns(comparison):
    lower_is_better = [
        "totalTime",
        "ofv",
        "waitingTruck",
        "waitingUAV",
        "numTruckCust",
    ]

    higher_is_better = ["numUAVcust"]

    for metric in METRICS:
        our_col = f"{metric}_our"
        their_col = f"{metric}_their"
        winner_col = f"{metric}_winner"

        def decide(row):
            our_value = row[our_col]
            their_value = row[their_col]

            if pd.isna(our_value) or pd.isna(their_value):
                return "missing"

            if metric in lower_is_better:
                if our_value < their_value:
                    return "our"
                if their_value < our_value:
                    return "their"
                return "tie"

            if metric in higher_is_better:
                if our_value > their_value:
                    return "our"
                if their_value > our_value:
                    return "their"
                return "tie"

            return "tie"

        comparison[winner_col] = comparison.apply(decide, axis=1)

    return comparison


def build_summary(comparison):
    rows = []

    for customer_count, group in comparison.groupby("numCustomers"):
        row = {
            "numCustomers": int(customer_count),
            "matchedProblems": len(group),
        }

        for metric in METRICS:
            our_col = f"{metric}_our"
            their_col = f"{metric}_their"
            winner_col = f"{metric}_winner"

            row[f"avg_{metric}_our"] = group[our_col].mean()
            row[f"avg_{metric}_their"] = group[their_col].mean()

            row[f"{metric}_our_wins"] = int((group[winner_col] == "our").sum())
            row[f"{metric}_their_wins"] = int((group[winner_col] == "their").sum())
            row[f"{metric}_ties"] = int((group[winner_col] == "tie").sum())

            improvement_col = f"{metric}_our_improvement_percent"
            if improvement_col in group.columns:
                row[f"avg_{metric}_our_improvement_percent"] = group[improvement_col].mean()

        rows.append(row)

    return pd.DataFrame(rows).sort_values("numCustomers")


def main():
    if not THEIR_FILE.exists():
        raise FileNotFoundError(f"Missing file: {THEIR_FILE}")

    if not OUR_FILE.exists():
        raise FileNotFoundError(f"Missing file: {OUR_FILE}")

    their = pd.read_csv(THEIR_FILE)
    ours = pd.read_csv(OUR_FILE, header=None, names=OUR_COLUMNS)

    their = clean_columns(their)
    ours = clean_columns(ours)

    their = normalize_bool_columns(their)
    ours = normalize_bool_columns(ours)

    their = normalize_numeric_columns(their)
    ours = normalize_numeric_columns(ours)

    # Keep heuristic rows only
    their = their[their["problemType"] == 2].copy()
    ours = ours[ours["problemType"] == 2].copy()

    # Keep only the 5 customer groups
    their = their[their["numCustomers"].isin(CUSTOMERS_TO_USE)].copy()
    ours = ours[ours["numCustomers"].isin(CUSTOMERS_TO_USE)].copy()

    print("\nLoaded rows before keeping best per problem:")
    print(f"Their rows: {len(their)}")
    print(f"Our rows: {len(ours)}")

    print("\nTheir rows by customer count:")
    print(their["numCustomers"].value_counts().sort_index())

    print("\nOur rows by customer count:")
    print(ours["numCustomers"].value_counts().sort_index())

    # Keep only one best row for each actual problem
    their_best = keep_best_per_problem(their)
    ours_best = keep_best_per_problem(ours)

    print("\nRows after keeping best per problem:")
    print(f"Their best rows: {len(their_best)}")
    print(f"Our best rows: {len(ours_best)}")

    print("\nTheir best rows by customer count:")
    print(their_best["numCustomers"].value_counts().sort_index())

    print("\nOur best rows by customer count:")
    print(ours_best["numCustomers"].value_counts().sort_index())

    # Compare by actual problem only
    keys = ["problemName", "numCustomers"]

    their_small = their_best[keys + METRICS].copy()
    ours_small = ours_best[keys + METRICS].copy()

    comparison = pd.merge(
        ours_small,
        their_small,
        on=keys,
        suffixes=("_our", "_their"),
        how="inner"
    )

    if len(comparison) == 0:
        print("\nNo matches found.")
        print("Check problemName values in both files.")
        return

    comparison["matchType"] = "problemName_numCustomers"

    comparison = add_difference_columns(comparison)
    comparison = add_winner_columns(comparison)

    comparison = comparison.sort_values(["numCustomers", "problemName"])

    summary = build_summary(comparison)

    comparison.to_csv(OUTPUT_CSV, index=False)
    comparison.to_json(OUTPUT_JSON, orient="records", indent=2)
    summary.to_csv(OUTPUT_SUMMARY_CSV, index=False)

    print("\nDone")
    print(f"Rows created: {len(comparison)}")

    print("\nMatched rows by customer count:")
    print(comparison["numCustomers"].value_counts().sort_index())

    print(f"\nCSV saved to: {OUTPUT_CSV}")
    print(f"JSON saved to: {OUTPUT_JSON}")
    print(f"Summary saved to: {OUTPUT_SUMMARY_CSV}")


if __name__ == "__main__":
    main()