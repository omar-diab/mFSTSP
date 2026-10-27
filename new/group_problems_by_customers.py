import pandas as pd
from pathlib import Path

# =========================
# Paths
# =========================
BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "performance_summary_archive.csv"
OUTPUT_DIR = BASE_DIR / "grouped_by_customers"

# create folder if not exists
OUTPUT_DIR.mkdir(exist_ok=True)

# =========================
# Read data
# =========================
df = pd.read_csv(CSV_FILE)

# take only needed columns + remove duplicates
df_clean = df[["problemName", "numCustomers"]].drop_duplicates()

# =========================
# Group by numCustomers
# =========================
groups = df_clean.groupby("numCustomers")

# =========================
# Create files
# =========================
for num_customers, group in groups:

    file_name = OUTPUT_DIR / f"customers_{int(num_customers)}.txt"

    problem_names = group["problemName"].sort_values().tolist()

    with open(file_name, "w") as f:
        for name in problem_names:
            f.write(f"{name}\n")

    print(f"Created: {file_name} ({len(problem_names)} problems)")

print("\nDone ✅ All files created.")