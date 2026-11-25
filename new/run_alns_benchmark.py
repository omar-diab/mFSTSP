#!/usr/bin/env python3
"""
Run our ALNS on the same runs as the Murray & Raj (2019) heuristic and save the results.

    python run_alns_benchmark.py                       # all 1,600 runs, resumes where it stopped
    python run_alns_benchmark.py --workers 4           # parallel
    python run_alns_benchmark.py --sizes 8 10          # only some customer counts
    python run_alns_benchmark.py --config my.json      # override ALNS settings (see mfstsp_alns/alns/config.py)

Each run uses the paper's settings (Etype 1 non-linear endurance, driver required,
truck must end at the depot). Output:
    results/alns/alns_results.csv           one row per run
    results/alns/solutions/<problem>_<vehicleFile>_<numUAVs>.json   route, sorties and full timing
"""

import argparse
import os
from pathlib import Path

from mfstsp_alns.alns.config import ALNSConfig
from mfstsp_alns.evaluation.benchmark_runner import run_benchmark

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 0))
    ap.add_argument("--sizes", type=int, nargs="*", default=None)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--config", default=None, help="JSON file with ALNS settings")
    ap.add_argument("--limit", type=int, default=None, help="only the first N remaining runs (testing)")
    ap.add_argument("--out", default=str(HERE / "results" / "alns" / "alns_results.csv"))
    ap.add_argument("--solutions", default=str(HERE / "results" / "alns" / "solutions"))
    args = ap.parse_args()

    cfg = ALNSConfig.from_json(args.config) if args.config else ALNSConfig()
    run_benchmark(HERE.parent / "old" / "performance_summary_archive.csv", HERE.parent / "old" / "Problems",
                  args.out, args.solutions, cfg, seed=args.seed, workers=args.workers,
                  sizes=set(args.sizes) if args.sizes else None, limit=args.limit,
                  log=lambda m: print(m, flush=True))


if __name__ == "__main__":
    main()
