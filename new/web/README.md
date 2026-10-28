# mFSTSP Web Dashboard + Maps

Next.js (TypeScript, Tailwind CSS, GSAP) dashboard plus the Python scripts that build its data:

```text
mFSTSP/
├── split_problems_by_customers_count/Problems/
├── Problems/
├── results/
├── performance_summary.csv
├── performance_summary_archive.csv
├── web/
│   ├── src/                     # Next.js app
│   ├── create_comparison_dashboard_data.py
│   ├── frontend_data/
│   └── maps/
│       ├── map_builder.py
│       ├── map_best_8.py
│       ├── map_best_10.py
│       ├── map_best_25.py
│       ├── map_best_50.py
│       ├── map_best_100.py
│       ├── run_all_maps.py
│       └── generated/
```

## 1) Install map dependency

```bash
pip install matplotlib
```

## 2) Build comparison dashboard data

```bash
python web/create_comparison_dashboard_data.py
```

## 3) Generate all maps

```bash
python web/maps/run_all_maps.py
```

The map parser reads your simple No-Gurobi summary files:

```text
Problems/<problem>/tbl_solutions_<vehicleFileID>_<numUAVs>_NoGurobiHeuristic.csv
```

It extracts:

- `Truck Route:`
- `UAV Sorties:`

and draws them over real coordinates from:

```text
Problems/<problem>/tbl_locations.csv
```

## 4) Run the dashboard

```bash
cd web
npm install
npm run dev
```

Open http://localhost:3000.
