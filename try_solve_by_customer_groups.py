import subprocess
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

GROUPED_DIR = BASE_DIR / "grouped_by_customers"
RESULT_DIR = BASE_DIR / "result"

CUSTOMER_COUNTS = [8, 10, 25, 50, 100]

PYTHON_CMD = "python"

# Heuristic only
VEHICLE_FILE_ID = 101
CUTOFF_TIME = 5
PROBLEM_TYPE = 2
NUM_UAVS = 1
NUM_TRUCKS = -1
REQUIRE_TRUCK_AT_DEPOT = 1
REQUIRE_DRIVER = 1
ETYPE = 1
ITER = 1

TIMEOUT_SECONDS = 600


def load_problem_names(file_path: Path):
    if not file_path.exists():
        print(f"⚠️ Missing file: {file_path}")
        return []

    with open(file_path, "r") as f:
        return [line.strip() for line in f if line.strip()]


def build_command(problem_name: str):
    return [
        PYTHON_CMD,
        "main.py",
        problem_name,
        str(VEHICLE_FILE_ID),
        str(CUTOFF_TIME),
        str(PROBLEM_TYPE),
        str(NUM_UAVS),
        str(NUM_TRUCKS),
        str(REQUIRE_TRUCK_AT_DEPOT),
        str(REQUIRE_DRIVER),
        str(ETYPE),
        str(ITER),
    ]


def classify_result(returncode, stdout, stderr):
    text = ((stdout or "") + "\n" + (stderr or "")).lower()

    if returncode == 0:
        return "solved"

    if "model too large for size-limited license" in text:
        return "blocked_by_licence"

    if "restricted license - for non-production use only" in text and returncode != 0:
        return "blocked_by_licence"

    return "other_error"


def save_results(solved_rows, not_solved_rows, output_dir):
    pd.DataFrame(solved_rows).to_csv(output_dir / "solved.csv", index=False)
    pd.DataFrame(not_solved_rows).to_csv(output_dir / "not_solved.csv", index=False)


def main():
    RESULT_DIR.mkdir(exist_ok=True)

    for customer_count in CUSTOMER_COUNTS:
        input_file = GROUPED_DIR / f"customers_{customer_count}.txt"
        output_dir = RESULT_DIR / f"try_solve_{customer_count}_customer"
        output_dir.mkdir(parents=True, exist_ok=True)

        solved_file = output_dir / "solved.csv"
        not_solved_file = output_dir / "not_solved.csv"

        problems = load_problem_names(input_file)

        print("\n" + "=" * 70)
        print(f"Trying to solve problems with {customer_count} customers")
        print(f"Input file: {input_file}")
        print(f"Output folder: {output_dir}")
        print(f"Total problems: {len(problems)}")
        print("=" * 70)

        solved_rows = []
        not_solved_rows = []

        for index, problem_name in enumerate(problems, start=1):
            cmd = build_command(problem_name)

            print(f"\n[{index}/{len(problems)}] {customer_count} customers | {problem_name}")
            print("Command:", " ".join(cmd))

            try:
                completed = subprocess.run(
                    cmd,
                    cwd=BASE_DIR,
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT_SECONDS,
                )

                category = classify_result(
                    completed.returncode,
                    completed.stdout,
                    completed.stderr,
                )

                if category == "solved":
                    solved_rows.append({
                        "problemName": problem_name,
                        "customerCount": customer_count,
                        "solver": "Heuristic",
                        "vehicleFileID": VEHICLE_FILE_ID,
                        "cutoffTime": CUTOFF_TIME,
                        "problemType": PROBLEM_TYPE,
                        "numUAVs": NUM_UAVS,
                        "returncode": completed.returncode,
                    })

                    print("✅ Solved")

                else:
                    reason = (completed.stderr or completed.stdout or "Unknown error").strip()

                    not_solved_rows.append({
                        "problemName": problem_name,
                        "customerCount": customer_count,
                        "solver": "Heuristic",
                        "reasonType": category,
                        "reason": reason[-1000:],
                        "returncode": completed.returncode,
                    })

                    print(f"❌ Not solved: {category}")

            except subprocess.TimeoutExpired:
                not_solved_rows.append({
                    "problemName": problem_name,
                    "customerCount": customer_count,
                    "solver": "Heuristic",
                    "reasonType": "timeout",
                    "reason": "TimeoutExpired",
                    "returncode": "TIMEOUT",
                })

                print("❌ Not solved: timeout")

            # Save after every problem
            pd.DataFrame(solved_rows).to_csv(solved_file, index=False)
            pd.DataFrame(not_solved_rows).to_csv(not_solved_file, index=False)

        print(f"\nDone with {customer_count} customers")
        print(f"Saved: {solved_file}")
        print(f"Saved: {not_solved_file}")

    print("\n✅ All customer groups finished.")


if __name__ == "__main__":
    main()