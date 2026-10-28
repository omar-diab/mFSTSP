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

| Page | What it shows |
|---|---|
| Comparison dashboard | Proposed Gurobi heuristic vs archived reference runs. Strict matching (every recorded flag) or relaxed matching (same instance and fleet), wins, per-pair improvement, coverage and a configuration audit. |
| Our experimental results | Proposed-heuristic runs: outcomes, distributions by size, runtime vs makespan, records and saved routes. |
| Original paper results | Archived three-phase heuristic and IP results, with local reruns of the original methods as an opt-in source. |
| Algorithms explained | Walkthroughs, flow diagrams, pseudocode and the real source of each component of `proposed_heuristic_with_gurobi.py` and the original methods. |
| 3D delivery studio | Interactive 3D replay of any saved solution: rotate, zoom, play/pause, speed, timeline, vehicle toggles and side-by-side comparison. |

The customer-count filter in the sidebar applies to every page. Every table exports to CSV.

## Data sources

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
