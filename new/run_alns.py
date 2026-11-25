#!/usr/bin/env python3
"""
Solve one mFSTSP instance with our ALNS.

    python run_alns.py <problemName> <vehicleFileID> <numUAVs> [--time 10] [--seed 1] [--json out.json]

Example:
    python run_alns.py 20170608T121355407419 101 2 --time 5
"""

import argparse
import json
from pathlib import Path

from mfstsp_alns.alns.config import ALNSConfig
from mfstsp_alns.alns.solver import solve_alns
from mfstsp_alns.data.loader import load_instance
from mfstsp_alns.evaluation.benchmark_runner import solution_payload
from mfstsp_alns.solution.verify import verify_schedule

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("problemName")
    ap.add_argument("vehicleFileID", type=int)
    ap.add_argument("numUAVs", type=int)
    ap.add_argument("--time", type=float, default=None, help="seconds (default: by customer count)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--etype", type=int, default=1)
    ap.add_argument("--json", default=None, help="write the full solution here")
    args = ap.parse_args()

    cfg = ALNSConfig(time_limit_seconds=args.time, endurance_model=args.etype)
    inst = load_instance(HERE.parent / "old" / "Problems", args.problemName, args.vehicleFileID, args.numUAVs,
                         args.etype)
    res = solve_alns(inst, cfg, seed=args.seed,
                     on_improvement=lambda h: print("  %7.2fs  iter %5d  makespan %.2f" % (h["time"], h["iteration"], h["makespan"])))
    best = res.best
    errors = verify_schedule(inst, best.route, best.sorties, best.schedule)
    print("Makespan: %.2f s (start %.2f s), %d iterations in %.1f s" % (best.objective, res.initial_objective, res.iterations, res.runtime))
    print("Truck route:", best.route)
    print("Sorties (uav, launch, customer, recovery):", [(s.uav_id, s.launch_node, s.customer_id, s.recovery_node) for s in best.sorties])
    print("Verified:", "yes" if not errors else errors)
    if args.json:
        Path(args.json).write_text(json.dumps(solution_payload(inst, res, cfg), indent=1))


if __name__ == "__main__":
    main()
