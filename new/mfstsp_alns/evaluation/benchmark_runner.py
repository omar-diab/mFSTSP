"""Run ALNS on every (problem, vehicle file, UAV count) the paper's heuristic was run on."""

from __future__ import annotations

import csv
import json
import os
import time
import traceback
from multiprocessing import Pool
from pathlib import Path
from typing import Dict, List

from ..alns.config import ALNSConfig
from ..alns.solver import solve_alns
from ..data.loader import load_instance
from ..solution.verify import verify_schedule

COLUMNS = [
    "problemName", "numCustomers", "vehicleFileID", "numUAVs", "Etype", "requireTruckAtDepot",
    "requireDriver", "seed", "timeLimit", "status", "ofv", "initialOfv", "runtime", "iterations",
    "evaluations", "numUAVcust", "numTruckCust", "waitingTruck", "waitingUAV", "verified",
    "message", "timestamp",
]


def run_key(r) -> tuple:
    return (str(r["problemName"]), str(int(float(r["vehicleFileID"]))), str(int(float(r["numUAVs"]))),
            str(int(float(r["seed"]))))


def load_paper_runs(archive_csv) -> List[Dict]:
    """The paper's heuristic runs: one per (problem, vehicle file, number of UAVs)."""
    runs = []
    with open(archive_csv, newline="") as f:
        for r in csv.DictReader(f, skipinitialspace=True):
            if int(r["problemType"]) != 2:
                continue
            runs.append({"problemName": r["problemName"].strip(), "vehicleFileID": int(r["vehicleFileID"]),
                         "numUAVs": int(r["numUAVs"]), "numCustomers": int(r["numCustomers"]),
                         "Etype": int(r["Etype"])})
    runs.sort(key=lambda r: (r["numCustomers"], r["problemName"], r["vehicleFileID"], r["numUAVs"]))
    return runs


def solution_payload(inst, result, cfg) -> Dict:
    best = result.best
    sched = best.schedule
    return {
        "problemName": inst.name, "vehicleFileID": inst.vehicle_file_id, "numUAVs": len(inst.uavs),
        "numCustomers": inst.n_customers, "makespan": best.objective,
        "truck_route": best.route,
        "sorties": [
            {"uav": t.sortie.uav_id, "launch": t.sortie.launch_node, "customer": t.sortie.customer_id,
             "recovery": t.sortie.recovery_node, "launch_start": round(t.launch_start, 3),
             "launch_end": round(t.launch_done, 3), "ready": round(t.ready_at_recovery, 3),
             "recovery_start": round(t.recovery_start, 3), "recovery_end": round(t.recovery_done, 3),
             "hover": round(t.hover, 3), "airborne": round(t.airborne, 3), "endurance": round(t.endurance, 3)}
            for t in sched.sorties],
        "truck_arrival": [round(x, 3) for x in sched.truck_arrival],
        "truck_departure": [round(x, 3) for x in sched.truck_departure],
        "operations": [[p, k, i, round(s, 3), round(e, 3)] for (p, k, i, s, e) in sched.operations],
        "schedule_policy": list(sched.policy),
        "history": result.history,
        "destroy_operators": result.destroy_stats,
        "repair_operators": result.repair_stats,
        "config": cfg.to_dict(),
    }


def _solve_one(args):
    run, problems_dir, solutions_dir, cfg_dict, seed = args
    cfg = ALNSConfig(**cfg_dict)
    row = {"problemName": run["problemName"], "numCustomers": run["numCustomers"],
           "vehicleFileID": run["vehicleFileID"], "numUAVs": run["numUAVs"], "Etype": cfg.endurance_model,
           "requireTruckAtDepot": cfg.require_truck_at_depot, "requireDriver": cfg.require_driver,
           "seed": seed, "timeLimit": cfg.time_limit(run["numCustomers"])}
    try:
        inst = load_instance(problems_dir, run["problemName"], run["vehicleFileID"], run["numUAVs"],
                             cfg.endurance_model, cfg.require_truck_at_depot, cfg.require_driver)
        result = solve_alns(inst, cfg, seed=seed)
        best = result.best
        errors = verify_schedule(inst, best.route, best.sorties, best.schedule) if best.feasible else ["infeasible"]
        row.update({
            "status": "solved" if best.feasible and not errors else "invalid",
            "ofv": "%.6f" % best.objective, "initialOfv": "%.6f" % result.initial_objective,
            "runtime": "%.3f" % result.runtime, "iterations": result.iterations,
            "evaluations": result.evaluations, "numUAVcust": len(best.sorties),
            "numTruckCust": len(best.route) - 2,
            "waitingTruck": "%.6f" % best.schedule.truck_waiting,
            "waitingUAV": "%.6f" % best.schedule.uav_waiting,
            "verified": not errors, "message": "; ".join(errors)[:300],
        })
        if solutions_dir:
            out = Path(solutions_dir) / ("%s_%d_%d.json" % (run["problemName"], run["vehicleFileID"], run["numUAVs"]))
            out.write_text(json.dumps(solution_payload(inst, result, cfg), separators=(",", ":")))
    except Exception as exc:  # keep the batch running; the row records the failure
        row.update({"status": "error", "message": ("%s: %s" % (type(exc).__name__, exc))[:300]})
        traceback.print_exc()
    row["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return row


def run_benchmark(archive_csv, problems_dir, out_csv, solutions_dir=None, cfg: ALNSConfig = None,
                  seed: int = 1, workers: int = 1, sizes=None, limit=None, log=print):
    cfg = cfg or ALNSConfig()
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if solutions_dir:
        Path(solutions_dir).mkdir(parents=True, exist_ok=True)
    done = set()
    if out_csv.exists():
        with open(out_csv, newline="") as f:
            done = {run_key(r) for r in csv.DictReader(f) if r.get("status") in ("solved", "invalid")}
    runs = [r for r in load_paper_runs(archive_csv) if sizes is None or r["numCustomers"] in sizes]
    todo = [r for r in runs if run_key({**r, "seed": seed}) not in done]
    log("%d paper runs, %d already done, %d to go (workers=%d)" % (len(runs), len(runs) - len(todo), len(todo), workers))
    if limit:
        todo = todo[:limit]
    jobs = [(r, str(problems_dir), solutions_dir and str(solutions_dir), cfg.to_dict(), seed) for r in todo]
    new_file = not out_csv.exists()
    with open(out_csv, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new_file:
            w.writeheader()
        pool = Pool(workers) if workers > 1 else None
        it = pool.imap_unordered(_solve_one, jobs) if pool else map(_solve_one, jobs)
        for i, row in enumerate(it, 1):
            w.writerow({k: row.get(k, "") for k in COLUMNS})
            f.flush()
            log("[%d/%d] %s %sc v%s %suav -> %s %s (%ss)" % (
                i, len(jobs), row["problemName"], row["numCustomers"], row["vehicleFileID"], row["numUAVs"],
                row.get("status"), row.get("ofv", ""), row.get("runtime", "")))
        if pool:
            pool.close()
            pool.join()
