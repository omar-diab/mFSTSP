# mFSTSP research workspace

A five-page Streamlit / Plotly frontend for the recorded experiments in this checkout.
The dashboard never imports a solver, generates solutions, or writes benchmark or result files.
Development stays on `AHMED`; nothing is committed or pushed by the application.

## Windows launch

Use Python 3.11 or newer (verified here with Python 3.14). From PowerShell:

```powershell
Set-Location C:\Users\USER\Desktop\mFSTSP
python -m pip install -r frontend\requirements.txt
python -m streamlit run app.py
```

Open the Local URL printed by Streamlit, normally `http://localhost:8501`.
The existing direct entry point also works:

```powershell
python -m streamlit run frontend\result_dashboard.py
```

The frontend requirements are independent of the legacy solver requirements: browsing does
not need a Gurobi license or Matplotlib. The theme is in `.streamlit/config.toml`.

## Navigation

The collapsible sidebar selects a page and customer counts (8, 10, 25, 50, 100).
KPI popovers explain their definitions. Tables include CSV exports. Refresh recorded data
invalidates caches; source file timestamps also invalidate the cached result data.

1. **Comparison dashboard** — select the proposed experiment, archive algorithm, metric,
   instances, vehicle types and fleet sizes. Inspect the pairing audit, outcome coverage,
   side-by-side result columns and descriptive distributions. Compatible solved pairs enable
   win counts, bars, improvement distributions and size trends.
2. **Our experimental results** — proposed-heuristic records only, separated by source file.
   Filter algorithms, configuration and instances; inspect runtime, quality, outcomes and routes.
3. **Original paper results** — archived reference-method metrics with separate original-method
   saved route files. The archive's attribution comes from repository provenance; publication
   tables and exact original experiment environments have not been independently authenticated.
4. **Algorithms explained** — six source-grounded explanations with interactive walkthroughs,
   flowcharts, pseudocode, real source functions, inputs/outputs, strengths and limitations.
5. **3D delivery studio** — choose a benchmark, saved solution, recorded snapshot and vehicle.
   Rotate/zoom, toggle vehicles, play/pause/restart, change speed, scrub the timeline, use an
   independent time probe and inspect activity/delivery tables. Optional geometric side-by-side
   comparison does not imply matched experimental conditions.

## Data sources and research rules

| Source | Use |
|---|---|
| `performance_summary.csv` | Headerless local summary, 812 records in the inspected checkout; 596 labeled No-Gurobi, plus original-method reruns |
| `performance_summary_archive.csv` | 1,920 archived reference records (1,600 heuristic, 320 IP) |
| `results/all_solved.csv` | 100 proposed-runner records, a separate experiment cohort |
| `results/all_not_solved.csv` | Explicit runner failures if present; currently empty |
| `Problems/*/tbl_locations.csv` | Real customer/depot coordinates; 100 benchmark instances |
| `Problems/*/tbl_truck_travel_data_PG.csv` | Dataset-presence inventory; road geometry is not reconstructed |
| `Problems/*/tbl_solutions_*.csv` | 2,020 saved solution files, including 100 NoGurobi files; original-format files may contain appended snapshots |

Per-size runner files duplicate aggregate records and are not double-counted. Local original-method
reruns are not relabeled as proposed results or archived publication results. All original data,
precomputed comparison files, map scripts and generated maps remain preserved.

Comparisons join on instance, customer count, vehicle type, UAV fleet, truck flag, depot/driver
requirements, endurance model, cutoff and iteration setting. Algorithm identity is selected
separately for the two cohorts. Unknown configuration values never match. Repeated runs are selected
by best positive finite makespan **within the exact configuration**, and record counts are exported.
This is a best-recorded-run comparison, not a statistical claim about expected algorithm performance.

For lower-is-better metrics, improvement is `(archive - proposed) / archive * 100`. For UAV service
counts, the sign is reversed. Service counts are utilization preferences, not independent quality
objectives. Zero reference values have undefined improvement percentages. Missing/negative metric
values are not ranked. A positive finite objective indicates a recorded solution, not a feasibility
certificate; `isOptimal` is an optimality flag and `bestBound=-1` means unavailable.

The inspected proposed experiments use Etype 3 and a 3,600-second cutoff; archived heuristic results
use Etype 1 and a 5-second cutoff. **There are currently no strict compatible solved pairs.**
The UI explains this and shows descriptive unmatched values without invented improvements or a
winner. Legacy precomputed comparison files ignore these configuration differences and are not used
for headline results. Hardware/software and actual modeling semantics are not established equal
even when recorded flags match; runtime is descriptive and legacy flags may be ignored by main.py.

## Playback accuracy and limitations

- Coordinates, saved truck travel timing and original assignment timing are real recorded data.
- Proposed files record sortie launch and recovery-arrival times but not customer arrival times.
  Their UAV flight legs and delivery highlights therefore use an **explicit illustrative midpoint**.
- Arc height is illustrative. The scene is a schematic in locally projected metres, not a measured
  altitude/road trajectory or a simulator validating solver feasibility.
- Some original-method files append multiple runs. A snapshot selector isolates them; their
  assignments and objectives are never combined. Block order is known; run dates are not recorded.
- Saved routes are separate snapshots, not automatically associated with a summary row or current
  source revision. Original-method files can contain local reruns rather than original publication runs.
- Saved validation is displayed as recorded. Detected UAV re-launch before the previous rendezvous is
  reported. These results are not corrected, relabeled feasible or recomputed.
- Unrecorded onboard vehicle positions are held at the last known node and explicitly labeled unknown.
- A return-depot ID `c+1` is mapped to depot coordinates for original-method routes.
- Distances are sums of straight-line projected segments, not road-network distances.
- No saved optimization trace was found. Algorithm execution mode explains why real generation/step
  playback is unavailable; the educational code walkthrough is kept separate from recorded evidence.

## Architecture

- `frontend/result_dashboard.py`: compatible entry point; `app.py` remains unchanged.
- `frontend/research/data.py`: CSV normalization, diagnostics, configuration matching, benchmark
  inventory, snapshot parsing, coordinate loading. No writes or solver imports.
- `frontend/research/visuals.py`: Plotly static/animated route scene and time probes.
- `frontend/research/algorithms.py`: source-grounded educational content.
- `frontend/research/app.py`: page composition, filters, exports, charts and styling.

## Verification

```powershell
python -m unittest discover -s frontend\tests -v
```

The suite verifies comparison directions, incompatible/unknown configurations, failure/missing
objectives, zero denominators, the actual configuration gap, benchmark coverage, malformed CSV
diagnostics, all saved solution snapshots, 3D frame serialization, real source functions, all five
pages, empty scopes, source walkthroughs, speed/time controls and route comparison.

Optional real-browser check using installed Chrome:

```powershell
python -m pip install playwright
# Terminal 1:
python -m streamlit run app.py --server.headless true --server.port 8511
# Terminal 2:
python frontend\tests\browser_smoke.py
```

The browser check exercises every page and real 3D play/pause/restart controls. Screenshots are
written to the OS temporary directory. It requires WebGL-capable Chrome or software rendering.
