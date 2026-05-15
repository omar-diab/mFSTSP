import subprocess
import pandas as pd
from pathlib import Path
import re
import time

BASE_DIR = Path(__file__).resolve().parent

GROUPED_DIR = BASE_DIR / "grouped_by_customers"
RESULT_DIR = BASE_DIR / "result_no_gurobi"

CUSTOMER_COUNTS = [8, 10, 25, 50, 100]

PYTHON_CMD = "python"

# Main.py arguments
VEHICLE_FILE_ID = 101
CUTOFF_TIME = 3600
PROBLEM_TYPE = 2
NUM_UAVS = 3
NUM_TRUCKS = -1
REQUIRE_TRUCK_AT_DEPOT = 1
REQUIRE_DRIVER = 1
ETYPE = 3
ITER = 1

TIMEOUT_SECONDS = 1200


def load_problem_names(file_path: Path):
    if not file_path.exists():
        print(f"Missing file: {file_path}")
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


def extract_number(pattern, text, default=None):
    match = re.search(pattern, text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return default
    return default


def extract_list_line(label, text):
    pattern = rf"{re.escape(label)}:\s*(.*)"
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    return ""


def parse_main_output(stdout):
    return {
        "objective": extract_number(r"Objective Function Value:\s*([0-9.]+)", stdout),
        "totalTime": extract_number(r"Total time for the whole process:\s*([0-9.]+)", stdout),
        "truckWaitingTime": extract_number(r"Truck Waiting Time:\s*([0-9.]+)", stdout),
        "uavWaitingTime": extract_number(r"UAV Waiting Time:\s*([0-9.]+)", stdout),
        "numTruckCustomers": extract_number(r"Number of Truck Customers:\s*([0-9.]+)", stdout),
        "numUAVCustomers": extract_number(r"Number of UAV Customers:\s*([0-9.]+)", stdout),
        "truckRoute": extract_list_line("Truck route", stdout),
        "uavSorties": extract_list_line("UAV sorties", stdout),
    }


def classify_result(returncode, stdout, stderr):
    text = ((stdout or "") + "\n" + (stderr or "")).lower()

    if returncode == 0 and "no-gurobi heuristic is done" in text:
        return "solved"

    if returncode == 0:
        return "solved"

    if "model too large for size-limited license" in text:
        return "blocked_by_license"

    if "gurobi" in text and "license" in text:
        return "blocked_by_license"

    if "timeout" in text:
        return "timeout"

    return "other_error"


def save_group_results(output_dir, solved_rows, not_solved_rows):
    pd.DataFrame(solved_rows).to_csv(output_dir / "solved.csv", index=False)
    pd.DataFrame(not_solved_rows).to_csv(output_dir / "not_solved.csv", index=False)


def main():
    RESULT_DIR.mkdir(exist_ok=True)

    all_solved_rows = []
    all_not_solved_rows = []

    for customer_count in CUSTOMER_COUNTS:
        input_file = GROUPED_DIR / f"customers_{customer_count}.txt"
        output_dir = RESULT_DIR / f"try_solve_{customer_count}_customers"
        output_dir.mkdir(parents=True, exist_ok=True)

        solved_file = output_dir / "solved.csv"
        not_solved_file = output_dir / "not_solved.csv"

        problems = load_problem_names(input_file)

        print("\n" + "=" * 80)
        print(f"Running {customer_count}-customer problems")
        print(f"Input file: {input_file}")
        print(f"Output folder: {output_dir}")
        print(f"Total problems: {len(problems)}")
        print("=" * 80)

        solved_rows = []
        not_solved_rows = []

        for index, problem_name in enumerate(problems, start=1):
            cmd = build_command(problem_name)

            print(f"\n[{index}/{len(problems)}] {customer_count} customers | {problem_name}")
            print("Command:", " ".join(cmd))

            start = time.time()

            try:
                completed = subprocess.run(
                    cmd,
                    cwd=BASE_DIR,
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT_SECONDS,
                )

                runtime = time.time() - start

                category = classify_result(
                    completed.returncode,
                    completed.stdout,
                    completed.stderr,
                )

                if category == "solved":
                    parsed = parse_main_output(completed.stdout)

                    row = {
                        "problemName": problem_name,
                        "customerCount": customer_count,
                        "status": "solved",
                        "vehicleFileID": VEHICLE_FILE_ID,
                        "cutoffTime": CUTOFF_TIME,
                        "problemType": PROBLEM_TYPE,
                        "numUAVs": NUM_UAVS,
                        "numTrucks": NUM_TRUCKS,
                        "requireTruckAtDepot": REQUIRE_TRUCK_AT_DEPOT,
                        "requireDriver": REQUIRE_DRIVER,
                        "Etype": ETYPE,
                        "ITER": ITER,
                        "runtimeSecondsByRunner": runtime,
                        "returncode": completed.returncode,
                        **parsed,
                    }

                    solved_rows.append(row)
                    all_solved_rows.append(row)

                    print("Solved")
                    print(f"Objective: {parsed.get('objective')}")
                    print(f"Truck customers: {parsed.get('numTruckCustomers')}")
                    print(f"UAV customers: {parsed.get('numUAVCustomers')}")

                else:
                    reason = (completed.stderr or completed.stdout or "Unknown error").strip()

                    row = {
                        "problemName": problem_name,
                        "customerCount": customer_count,
                        "status": "not_solved",
                        "reasonType": category,
                        "reason": reason[-1500:],
                        "runtimeSecondsByRunner": runtime,
                        "returncode": completed.returncode,
                    }

                    not_solved_rows.append(row)
                    all_not_solved_rows.append(row)

                    print(f"Not solved: {category}")

            except subprocess.TimeoutExpired:
                runtime = time.time() - start

                row = {
                    "problemName": problem_name,
                    "customerCount": customer_count,
                    "status": "not_solved",
                    "reasonType": "timeout",
                    "reason": "TimeoutExpired",
                    "runtimeSecondsByRunner": runtime,
                    "returncode": "TIMEOUT",
                }

                not_solved_rows.append(row)
                all_not_solved_rows.append(row)

                print("Not solved: timeout")

            # Save after every problem, so you do not lose progress
            save_group_results(output_dir, solved_rows, not_solved_rows)

            pd.DataFrame(all_solved_rows).to_csv(
                RESULT_DIR / "all_solved.csv",
                index=False
            )

            pd.DataFrame(all_not_solved_rows).to_csv(
                RESULT_DIR / "all_not_solved.csv",
                index=False
            )

        print(f"\nDone with {customer_count}-customer problems")
        print(f"Saved: {solved_file}")
        print(f"Saved: {not_solved_file}")

    print("\nAll customer groups finished.")
    print(f"All solved results: {RESULT_DIR / 'all_solved.csv'}")
    print(f"All not solved results: {RESULT_DIR / 'all_not_solved.csv'}")


if __name__ == "__main__":
    main()