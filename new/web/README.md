# mFSTSP Web Dashboard

Next.js (TypeScript, Tailwind CSS, GSAP) research dashboard for the recorded mFSTSP experiments. It is read-only: it never runs a solver or writes result files.

## Run it

```bash
cd new/web
npm install
npm run dev
```

Open http://localhost:3000. The splash animation plays once per browser session (click to skip).

`npm run dev` and `npm run build` first run `npm run data`, which reads the recorded experiments and writes JSON to `public/data/` (git-ignored). After new solver runs, restart the dev server or run `npm run data` and press **Refresh recorded data** in the sidebar.

## Pages

| Group | Page | What it shows |
|---|---|---|
| Results | Paper results | Murray & Raj (2019) archived results (`old/performance_summary_archive.csv`). |
| Results | Our results | Our re-run of the paper's original code with the free Gurobi license (`old/reproduction/our_results.csv`). |
| Results | Compare | The two side by side: exact matches, differences. |
| Our algorithm | Our algorithm | How our ALNS works, its rules, operators, settings, and the check of our schedule evaluator on the paper's own solutions. |
| Our algorithm | Our algorithm results | ALNS on the paper's 1,600 heuristic settings, with a route and timing viewer per run. |
| Our algorithm | Algorithm vs paper | ALNS vs the paper's heuristic (same problem, drone type, fleet), and vs the proven optima on 8 customers. |

The customer-count filter in the sidebar applies to every page. Every table exports to CSV.

## Data sources

`scripts/build-data.mjs` writes `public/data/reproduction.json` and copies the ALNS solutions to `public/data/alns/` (both git-ignored) from:

| Source | Use |
|---|---|
| `old/performance_summary_archive.csv` | Paper results |
| `old/reproduction/our_results.csv` | Our re-run of the paper's code |
| `new/results/alns/alns_results.csv` | ALNS runs (written by `new/run_alns_benchmark.py`) |
| `new/results/alns/evaluator_validation.csv` | Our evaluator on the paper's solutions |
| `new/results/alns/solutions/*.json` | ALNS routes and timings, joined with `old/Problems/*/tbl_locations.csv` |

## Older data notes

Read by `scripts/build-data.mjs` from `new/`:

| Source | Use |
|---|---|
| `performance_summary.csv` | Headerless local summary: Gurobi heuristic, legacy No-Gurobi heuristic and local reruns of the original methods |
| `performance_summary_archive.csv` | Archived reference results (heuristic and IP) |
| `results/all_solved.csv`, `results/all_not_solved.csv` | Runner results for the Gurobi heuristic (per-size copies are not double counted) |
| `results/gurobi_heuristic_results.csv` | Strategy label per run |
| `Problems/*/tbl_locations.csv` | Depot and customer coordinates |
| `Problems/*/tbl_solutions_*.csv` | Saved solutions for playback, including appended snapshots in original-format files |
| `proposed_heuristic_with_gurobi.py`, `../old/solve_mfstsp_*.py` | Function source shown on the algorithms page |

## Reading the numbers

- Strict comparisons join on instance, customer count, vehicle type, UAV and truck count, depot and driver flags, endurance model (Etype), cutoff and ITER. The proposed runs (Etype 3, 3,600 s) and the archived heuristic (Etype 1, 5 s) never match strictly, so strict mode shows descriptive distributions only.
- Relaxed mode pairs runs on instance, customer count, vehicle and UAV count only, and is labelled as a descriptive side-by-side rather than a controlled claim.
- Repeated runs keep the best positive makespan per configuration. Improvement is `(archive − proposed) / archive × 100` for lower-is-better metrics, and the sign is reversed for UAV customers.
- Proposed solution files record sortie launch and recovery times but not customer arrival, so UAV delivery times in playback use an illustrative midpoint. Arc height is illustrative, and distances are straight-line.

## Legacy map scripts

`create_comparison_dashboard_data.py` and `maps/` are the earlier Python helpers (need `pip install matplotlib`). The dashboard does not use their output.
