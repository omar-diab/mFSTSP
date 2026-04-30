import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

THEIR_FILE = BASE_DIR / "performance_summary_archive.csv"
OUR_FILE = BASE_DIR / "performance_summary.csv"

OUTPUT_DIR = BASE_DIR / "frontend_data"
OUTPUT_DIR.mkdir(exist_ok=True)

OUTPUT_JSON = OUTPUT_DIR / "comparison_8_10_25.json"
OUTPUT_CSV = OUTPUT_DIR / "comparison_8_10_25.csv"

CUSTOMERS_TO_USE = [8, 10, 25]

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

KEY_COLS = [
    "problemName",
    "numCustomers",
    "vehicleFileID",
    "problemType",
    "numUAVs",
    "numTrucks",
    "requireTruckAtDepot",
    "requireDriver",
    "Etype",
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
            df[col] = pd.to_numeric(
                df[col].astype(str).str.strip(),
                errors="coerce"
            )

    return df


def check_required(name, df, required_cols):
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        print(f"\n{name} columns:")
        for col in df.columns:
            print(f"- {col}")
        raise KeyError(f"{name} is missing columns: {missing}")


def main():
    their = pd.read_csv(THEIR_FILE)
    ours = pd.read_csv(OUR_FILE, header=None, names=OUR_COLUMNS)

    their = clean_columns(their)
    ours = clean_columns(ours)

    their = normalize_bool_columns(their)
    ours = normalize_bool_columns(ours)

    their = normalize_numeric_columns(their)
    ours = normalize_numeric_columns(ours)

    check_required("THEIR archive file", their, KEY_COLS + METRICS)
    check_required("OUR performance file", ours, KEY_COLS + METRICS)

    # Keep only 8, 10, 25 customers
    their = their[their["numCustomers"].isin(CUSTOMERS_TO_USE)].copy()
    ours = ours[ours["numCustomers"].isin(CUSTOMERS_TO_USE)].copy()

    # Heuristic only
    their = their[their["problemType"] == 2].copy()
    ours = ours[ours["problemType"] == 2].copy()

    # Keep only comparable columns
    their_small = their[KEY_COLS + METRICS].copy()
    ours_small = ours[KEY_COLS + METRICS].copy()

    # Remove duplicates
    their_small = their_small.drop_duplicates(subset=KEY_COLS)
    ours_small = ours_small.drop_duplicates(subset=KEY_COLS)

    comparison = pd.merge(
        ours_small,
        their_small,
        on=KEY_COLS,
        suffixes=("_our", "_their"),
        how="inner"
    )

    # If strict config matching gives 0 rows, fallback to problemName + numCustomers
    if len(comparison) == 0:
        print("⚠️ Strict matching returned 0 rows.")
        print("Trying fallback match by problemName + numCustomers only...")

        fallback_keys = ["problemName", "numCustomers"]

        their_small = their[fallback_keys + METRICS].copy()
        ours_small = ours[fallback_keys + METRICS].copy()

        their_small = their_small.drop_duplicates(subset=fallback_keys)
        ours_small = ours_small.drop_duplicates(subset=fallback_keys)

        comparison = pd.merge(
            ours_small,
            their_small,
            on=fallback_keys,
            suffixes=("_our", "_their"),
            how="inner"
        )

    # Winner logic: lower is better for these metrics
    for metric in METRICS:
        our_col = f"{metric}_our"
        their_col = f"{metric}_their"
        winner_col = f"{metric}_winner"

        comparison[winner_col] = comparison.apply(
            lambda row:
                "our" if row[our_col] < row[their_col]
                else "their" if row[their_col] < row[our_col]
                else "tie",
            axis=1
        )

    comparison = comparison.sort_values(["numCustomers", "problemName"])

    comparison.to_csv(OUTPUT_CSV, index=False)
    comparison.to_json(OUTPUT_JSON, orient="records", indent=2)

    print("\n✅ Done")
    print(f"Rows created: {len(comparison)}")
    print(f"CSV saved to: {OUTPUT_CSV}")
    print(f"JSON saved to: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()