"""Check our schedule evaluator against the paper's own solutions.

For every saved paper solution (exact model and heuristic) we keep the
paper's truck route and sorties, let our evaluator compute the timing, and
compare the makespan. On the proven-optimal plans our makespan must never be
lower than the paper's (that would mean a broken rule); equal means the
evaluator found the same timing as the exact model.

    python -m mfstsp_alns.evaluation.validate_evaluator      (from new/)
writes results/alns/evaluator_validation.csv
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

from ..data.loader import load_instance
from ..scheduling.evaluator import evaluate
from ..solution.verify import verify_schedule
from .paper_solutions import read_paper_solution

HERE = Path(__file__).resolve().parents[2]  # new/


def main():
    archive = HERE.parent / "old" / "performance_summary_archive.csv"
    problems = HERE.parent / "old" / "Problems"
    out = HERE / "results" / "alns" / "evaluator_validation.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["problemName", "numCustomers", "vehicleFileID", "numUAVs", "method", "paperOptimal",
            "paperOfv", "ourOfv", "diffPct", "feasible", "verified", "message"]
    with open(archive, newline="") as f:
        runs = list(csv.DictReader(f, skipinitialspace=True))
    t0 = time.time()
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for i, r in enumerate(runs, 1):
            method = "IP" if int(r["problemType"]) == 1 else "Heuristic"
            name, v, u = r["problemName"].strip(), int(r["vehicleFileID"]), int(r["numUAVs"])
            inst = load_instance(problems, name, v, u)
            sol = read_paper_solution(problems / name / ("tbl_solutions_%d_%d_%s.csv" % (v, u, method)),
                                      inst.n_customers)
            row = {"problemName": name, "numCustomers": inst.n_customers, "vehicleFileID": v, "numUAVs": u,
                   "method": method, "paperOptimal": r["isOptimal"].strip() == "True"}
            if sol is None:
                row.update({"message": "no saved solution"})
            else:
                res = evaluate(inst, sol["route"], sol["sorties"], detailed=True)
                errors = verify_schedule(inst, sol["route"], sol["sorties"], res) if res.feasible else []
                row.update({
                    "paperOfv": "%.6f" % sol["ofv"], "feasible": res.feasible,
                    "ourOfv": "%.6f" % res.makespan if res.feasible else "",
                    "diffPct": "%.6f" % ((res.makespan - sol["ofv"]) / sol["ofv"] * 100) if res.feasible else "",
                    "verified": res.feasible and not errors,
                    "message": "; ".join(errors or res.violations)[:200],
                })
            w.writerow(row)
            if i % 200 == 0:
                print("%d/%d (%.0fs)" % (i, len(runs), time.time() - t0), flush=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
