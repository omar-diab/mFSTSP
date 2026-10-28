"""Read-only adapter for the repository's existing full MILP.

Run with the isolated .venv interpreter. Never instantiate main.missionControl:
its constructor would run a different algorithm and overwrite existing results.
The observer changes logging and enforces the requested time budget only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
LIMIT = 1200
SIZES = [8, 10, 25, 50, 100]
LICENSE = "Restricted size-limited (not full Academic); expires 2027-11-29"
FIELDS = "problem_name customers drones trucks vehicle_file_id endurance_model require_truck_at_depot require_driver gurobi_version license_type algorithm execution_time_limit_seconds solver_time_limit_seconds runtime_wall_seconds solver_runtime_seconds solver_status raw_solver_status feasible_solution_found objective best_bound mip_gap optimality_proven variables constraints input_verified error log_file".split()


def plan():
    rows = []
    for count in SIZES:
        instance = (ROOT / "grouped_by_customers" / f"customers_{count}.txt").read_text().splitlines()[0].strip()
        p = ROOT / "Problems" / instance
        with (p / "tbl_locations.csv").open() as handle:
            locations = list(csv.reader(line for line in handle if not line.startswith("%")))
        with (p / "tbl_truck_travel_data_PG.csv").open() as handle:
            travel = list(csv.reader(line for line in handle if not line.startswith("%")))
        assert len(locations) == count+1, (instance, count, len(locations))
        assert len(travel) == (count+1)**2, (instance, "incomplete truck matrix")
        assert (ROOT / "Problems/tbl_vehicles_101.csv").exists()
        rows.append(dict(problem_name=instance, customers=count, drones=3, trucks=1, vehicle_file_id=101, endurance_model=1, require_truck_at_depot=True, require_driver=True, gurobi_version="13.0.3", license_type=LICENSE, algorithm="Existing full MILP: solve_mfstsp_IP.solve_mfstsp_IP", execution_time_limit_seconds=LIMIT, input_verified=True, optimality_proven=False))
    return rows


def worker(count):
    import gurobipy as gp
    import main as existing
    import solve_mfstsp_IP as solver

    row = next(r for r in plan() if r["customers"] == count)
    started = time.perf_counter()
    result_path = HERE / f"{count}_customers_result.json"
    log_path = HERE / f"{count}_customers_solver.log"
    if result_path.exists() or log_path.exists():
        raise FileExistsError("Refusing to overwrite existing test outputs")
    row["log_file"] = log_path.name
    statuses = {2:"OPTIMAL", 3:"INFEASIBLE", 4:"INF_OR_UNBD", 5:"UNBOUNDED", 6:"CUTOFF", 7:"ITERATION_LIMIT", 8:"NODE_LIMIT", 9:"TIME_LIMIT", 10:"SOLUTION_LIMIT", 11:"INTERRUPTED", 12:"NUMERIC", 13:"SUBOPTIMAL", 15:"USER_OBJ_LIMIT", 16:"WORK_LIMIT", 17:"MEM_LIMIT"}

    class ObservedModel(gp.Model):
        def optimize(self, *args, **kwargs):
            self.update()
            remaining = max(.001, LIMIT-(time.perf_counter()-started))
            self.Params.TimeLimit = min(LIMIT, remaining)
            self.Params.OutputFlag = 1
            self.Params.LogFile = str(log_path)
            row.update(variables=self.NumVars, constraints=self.NumConstrs, solver_time_limit_seconds=self.Params.TimeLimit)
            print("MODEL_SIZE", json.dumps({k:row[k] for k in ["variables", "constraints", "solver_time_limit_seconds"]}), flush=True)
            try:
                super().optimize(*args, **kwargs)
            except gp.GurobiError as error:
                row.update(solver_status="LICENSE_SIZE_LIMIT" if error.errno == 10010 else "SOLVER_ERROR", error=f"Gurobi {error.errno}: {error}", raw_solver_status=self.Status, feasible_solution_found=False)
                raise
            else:
                status = statuses.get(self.Status, f"STATUS_{self.Status}")
                if status == "TIME_LIMIT":
                    status += "_WITH_FEASIBLE_SOLUTION" if self.SolCount else "_WITHOUT_FEASIBLE_SOLUTION"
                row.update(solver_status=status, raw_solver_status=self.Status, feasible_solution_found=bool(self.SolCount), solver_runtime_seconds=self.Runtime, objective=self.ObjVal if self.SolCount else None, best_bound=self.ObjBound, mip_gap=self.MIPGap if self.SolCount else None, optimality_proven=self.Status == gp.GRB.OPTIMAL)
                if self.SolCount:
                    self.write(str(HERE / f"{count}_customers_incumbent.sol"))
                # Persist native solver results before legacy result-extraction code runs.
                result_path.write_text(json.dumps(row, indent=2), encoding="utf-8")

    solver.Model = ObservedModel
    try:
        # Reuse the existing input reader, deliberately bypassing its write/solve constructor.
        mission = existing.missionControl.__new__(existing.missionControl)
        directory = ROOT / "Problems" / row["problem_name"]
        mission.locationsFile = str(directory / "tbl_locations.csv")
        mission.distmatrixFile = str(directory / "tbl_truck_travel_data_PG.csv")
        mission.vehiclesFile = str(ROOT / "Problems/tbl_vehicles_101.csv")
        mission.node, mission.vehicle = {}, {}
        mission.travel = defaultdict(existing.make_dict)
        mission.readData(row["drones"])
        for v, vehicle in mission.vehicle.items():
            if vehicle.vehicleType != existing.TYPE_UAV:
                continue
            for i, origin in mission.node.items():
                for j, target in mission.node.items():
                    values = [0.0]*8 if i == j else existing.distance_functions.calcMultirotorTravelTime(vehicle.takeoffSpeed, vehicle.cruiseSpeed, vehicle.landingSpeed, vehicle.yawRateDeg, origin.altMeters, vehicle.cruiseAlt, target.altMeters, origin.latDeg, origin.lonDeg, target.latDeg, target.lonDeg, -361, -361)
                    mission.travel[v][i][j] = existing.make_travel(*values)
        print("Calling existing full MILP", row["problem_name"], "customers", count, "3 UAVs, 1 truck, vehicle 101, Etype 1, driver/depot required", flush=True)
        result = solver.solve_mfstsp_IP(mission.node, mission.vehicle, mission.travel, LIMIT, True, True, 1)
        row["legacy_return_objective"] = result[0]
    except BaseException as error:
        row.setdefault("solver_status", "EXPERIMENT_ERROR")
        row.setdefault("error", f"{type(error).__name__}: {error}")
        traceback.print_exc()
    finally:
        row["runtime_wall_seconds"] = time.perf_counter()-started
        result_path.write_text(json.dumps(row, indent=2), encoding="utf-8")
        print("RESULT", json.dumps(row), flush=True)


def file_hashes():
    paths = list((ROOT / "Problems").rglob("*")) + list((ROOT / "results").rglob("*"))
    paths += list(ROOT.glob("*.py")) + [ROOT/"performance_summary.csv", ROOT/"performance_summary_archive.csv"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}


def run():
    csv_path = HERE / "gurobi_test_results.csv"
    if csv_path.exists():
        raise FileExistsError("Prior results exist; refusing to overwrite")
    assert subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip() == "AHMED"
    before = file_hashes()
    rows, halted = [], ""
    for row in plan():
        count = row["customers"]
        if halted:
            row.update(solver_status="NOT_RUN", error="Stopped after smaller-instance failure: "+halted)
        else:
            log = HERE / f"{count}_customers_console.log"
            with log.open("x", encoding="utf-8") as output:
                child = subprocess.Popen([sys.executable, "-B", "-u", str(Path(__file__).resolve()), "--worker", str(count)], cwd=HERE, stdout=output, stderr=subprocess.STDOUT)
                try:
                    child.wait(timeout=LIMIT)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                    halted = "20-minute process wall limit reached"
                    row.update(solver_status="PROCESS_WALL_TIME_LIMIT", error=halted, runtime_wall_seconds=LIMIT)
            saved = HERE / f"{count}_customers_result.json"
            if saved.exists():
                row.update(json.loads(saved.read_text(encoding="utf-8")))
            elif not halted:
                row.update(solver_status="EXPERIMENT_ERROR", error=f"Worker exited {child.returncode} without result")
            if row["solver_status"] in ["LICENSE_SIZE_LIMIT", "SOLVER_ERROR", "EXPERIMENT_ERROR", "NUMERIC", "INF_OR_UNBD"]:
                halted = row.get("error", row["solver_status"])
        rows.append(row)
        print(f"{count} customers: {row['solver_status']}", flush=True)
    with csv_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
    after = file_hashes()
    preservation = {"checked_files": len(before), "unchanged": before == after, "changed_or_missing": [k for k,v in before.items() if after.get(k) != v], "unexpected_new_files": sorted(set(after)-set(before))}
    (HERE/"data_preservation_check.json").write_text(json.dumps(preservation, indent=2), encoding="utf-8")
    (HERE/"experiment_plan.json").write_text(json.dumps(plan(), indent=2), encoding="utf-8")
    assert preservation["unchanged"], preservation


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=int, choices=SIZES)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker)
    else:
        run()
