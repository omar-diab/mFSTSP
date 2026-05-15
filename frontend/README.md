# mFSTSP Frontend + Maps

This is the fresh frontend folder designed for the current project layout:

```text
mFSTSP/
├── grouped_by_customers/
├── Problems/
├── results/
├── performance_summary.csv
├── performance_summary_archive.csv
├── frontend/
│   ├── create_comparison_dashboard_data.py
│   ├── result_dashboard.py
│   ├── verify_frontend_install.py
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

## 2) Verify the frontend install

```bash
python frontend/verify_frontend_install.py
```

All checks should print `True`.

## 3) Build comparison dashboard data

```bash
python frontend/create_comparison_dashboard_data.py
```

## 4) Generate all maps

```bash
python frontend/maps/run_all_maps.py
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

## 5) Run Streamlit

```bash
streamlit run frontend/result_dashboard.py
```

Use the sidebar:

- `Results Dashboard`
- `Maps Page`
