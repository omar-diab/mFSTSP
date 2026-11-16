#!/usr/bin/env python3
"""
Re-run the original Murray & Raj (2019) code on every run listed in
performance_summary_archive.csv, and save what we get next to theirs.

    python reproduce.py                 # run everything (resumes where it stopped)
    python reproduce.py --ip-cutoff 60  # cap each exact-model (IP) run at 60 s

Each run happens in a throw-away folder, so the paper's original files in
Problems/ are never touched. Results go to reproduction/our_results.csv.

Status values:
    solved           the run finished
    time_capped      exact model stopped at our --ip-cutoff (smaller than the paper's)
    license_needed   Gurobi refused: model too large for the free size-limited license
    error            anything else (see the message column)

When one run hits the license limit, every remaining run in the same
(method, number of customers, number of UAVs) group is marked
license_needed without running it, unless --try-all is given.

To redo runs (for example after installing a full license), delete their
rows from reproduction/our_results.csv and run this script again.
"""

import argparse
import csv
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE / "performance_summary_archive.csv"
OUT_DIR = HERE / "reproduction"
OUT_CSV = OUT_DIR / "our_results.csv"

COLUMNS = [
    "problemName", "vehicleFileID", "problemType", "method", "numUAVs",
    "numCustomers", "cutoffTime", "ITER", "status", "ofv", "bestBound",
    "totalTime", "isOptimal", "numUAVcust", "numTruckCust", "waitingTruck",
    "waitingUAV", "message", "timestamp",
]

LICENSE_TEXT = "size-limited license"


def run_key(r):
    return (r["problemName"], str(r["vehicleFileID"]), str(r["problemType"]), str(r["numUAVs"]))


def load_archive():
    runs = []
    with open(ARCHIVE, newline="") as f:
        for r in csv.DictReader(f):
            runs.append({
                "problemName": r["problemName"].strip(),
                "vehicleFileID": int(r["vehicleFileID"]),
                "problemType": int(r["problemType"]),
                "method": "IP" if int(r["problemType"]) == 1 else "Heuristic",
                "numUAVs": int(r["numUAVs"]),
                "numCustomers": int(r["numCustomers"]),
                "cutoffTime": float(r["cutoffTime"]),
                "ITER": int(r["ITER"]),
            })
    # Cheapest first: heuristic before IP, small problems before big ones.
    runs.sort(key=lambda r: (r["problemType"] == 1, r["numCustomers"], r["numUAVs"],
                             r["vehicleFileID"], r["problemName"]))
    return runs


def load_done():
    if not OUT_CSV.exists():
        return {}
    with open(OUT_CSV, newline="") as f:
        return {run_key(r): r for r in csv.DictReader(f)}


def append(row):
    new = not OUT_CSV.exists()
    with open(OUT_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in COLUMNS})


def run_one(run, cutoff, timeout):
    work = Path(tempfile.mkdtemp(prefix="mfstsp_"))
    try:
        prob = run["problemName"]
        (work / "Problems" / prob).mkdir(parents=True)
        for py in HERE.glob("*.py"):
            if py.name != "reproduce.py":
                os.symlink(py, work / py.name)
        for v in HERE.glob("Problems/tbl_vehicles_*.csv"):
            shutil.copy(v, work / "Problems" / v.name)
        for name in ("tbl_locations.csv", "tbl_truck_travel_data_PG.csv"):
            shutil.copy(HERE / "Problems" / prob / name, work / "Problems" / prob / name)

        args = [sys.executable, "main.py", prob, str(run["vehicleFileID"]), f"{cutoff:g}",
                str(run["problemType"]), str(run["numUAVs"]), "-1", "1", "1", "1", str(run["ITER"])]
        try:
            p = subprocess.run(args, cwd=work, capture_output=True, text=True, timeout=timeout)
            log = p.stdout + p.stderr
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": f"no result after {timeout}s"}

        if LICENSE_TEXT in log:
            return {"status": "license_needed", "message": "Model too large for size-limited license"}

        summary = work / "performance_summary.csv"
        if p.returncode != 0 or not summary.exists():
            last = [l for l in log.strip().splitlines() if l.strip()][-1:] or ["unknown failure"]
            return {"status": "error", "message": last[0][:300]}

        f = [x.strip() for x in summary.read_text().strip().splitlines()[-1].split(",")]
        # Columns after the runString: numCustomers, timestamp, ofv, bestBound, totalTime,
        # isOptimal, numUAVcust, numTruckCust, waitingTruck, waitingUAV
        tail = f[-10:]
        res = {
            "ofv": tail[2], "bestBound": tail[3], "totalTime": tail[4], "isOptimal": tail[5],
            "numUAVcust": tail[6], "numTruckCust": tail[7], "waitingTruck": tail[8],
            "waitingUAV": tail[9], "status": "solved", "message": "",
        }
        if run["problemType"] == 1 and tail[5] != "True" and cutoff < run["cutoffTime"]:
            res["status"] = "time_capped"
            res["message"] = f"Stopped at {cutoff:g}s (paper allowed {run['cutoffTime']:g}s)"
        return res
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip-cutoff", type=float, default=None,
                    help="seconds per exact-model run (default: the paper's own cutoff)")
    ap.add_argument("--only", choices=["IP", "Heuristic"], default=None)
    ap.add_argument("--try-all", action="store_true",
                    help="try every run, even in a group that already hit the license limit")
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    runs = load_archive()
    done = load_done()
    blocked = {(r["method"], int(r["numCustomers"]), int(r["numUAVs"]))
               for r in done.values() if r["status"] == "license_needed"}

    todo = [r for r in runs if run_key({k: str(v) for k, v in r.items()}) not in done
            and (args.only is None or r["method"] == args.only)]
    print(f"{len(runs)} runs in archive, {len(done)} already done, {len(todo)} to go", flush=True)

    for i, run in enumerate(todo, 1):
        group = (run["method"], run["numCustomers"], run["numUAVs"])
        cutoff = run["cutoffTime"]
        if run["problemType"] == 1 and args.ip_cutoff is not None:
            cutoff = min(cutoff, args.ip_cutoff)

        if group in blocked and not args.try_all:
            res = {"status": "license_needed", "message": "Skipped: this group already hit the license limit"}
        else:
            t0 = time.time()
            res = run_one(run, cutoff, timeout=max(600, cutoff * 3))
            if res["status"] == "license_needed":
                blocked.add(group)
            print(f"[{i}/{len(todo)}] {run['method']} {run['numCustomers']}c {run['numUAVs']}uav "
                  f"v{run['vehicleFileID']} {run['problemName']} -> {res['status']} "
                  f"{res.get('ofv', '')} ({time.time() - t0:.1f}s)", flush=True)

        append({**run, "cutoffTime": cutoff, **res,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})


if __name__ == "__main__":
    main()
