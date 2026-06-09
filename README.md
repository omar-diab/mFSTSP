# 🚁 mFSTSP — Multiple Flying Sidekick Traveling Salesman Problem
### A License-Free, Scenario-Specific Heuristic Framework for Truck–UAV Cooperative Delivery

[![Live Dashboard](https://img.shields.io/badge/Dashboard-Live%20at%20mfstsp.streamlit.app-brightgreen?style=for-the-badge&logo=streamlit)](https://mfstsp.streamlit.app)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)
[![Instances](https://img.shields.io/badge/Benchmark%20Instances-100-orange?style=for-the-badge)]()
[![OFV Win Rate](https://img.shields.io/badge/OFV%20Win%20Rate-88%25-success?style=for-the-badge)]()

---

## 📌 Overview

This repository implements a **fully custom, Gurobi-free heuristic optimization framework** for the **Multiple Flying Sidekick Traveling Salesman Problem (mFSTSP)**, as originally formulated by Murray & Raj (2019). The mFSTSP models a cooperative last-mile delivery system in which **one truck and up to three UAVs (drones)** work in parallel to serve geographically distributed customers in the minimum total mission time (makespan).

The original reference implementation requires a commercial **Gurobi** license — a critical barrier for academic and resource-constrained industrial use. This project eliminates that dependency entirely, delivering a **zero-cost, open-source platform** that outperforms the archived Gurobi-based heuristic baseline across all five benchmark scenario groups.

> **ENS001 – Application Development for Optimization**  
> Istinye University, Faculty of Engineering and Natural Sciences  
> **Team 18** | Capstone Project

---

## 🏆 Key Results at a Glance

| Scenario | Our Avg OFV | Baseline Avg OFV | Improvement | Win Rate |
|----------|-------------|------------------|-------------|----------|
| 8 customers | 1,847.3 s | 2,120.1 s | **21.8%** | 17/20 |
| 10 customers | 2,091.2 s | 2,471.8 s | **20.7%** | 16/20 |
| 25 customers | 5,121.6 s | 6,009.3 s | **17.5%** | 15/20 |
| 50 customers | 6,442.4 s | 9,023.1 s | **30.0%** | **20/20 ✅** |
| 100 customers | 9,165.2 s | 14,347.9 s | **36.6%** | **20/20 ✅** |
| **Overall** | — | — | **25.3%** | **88/100 (88%)** |

> The 50- and 100-customer scenarios achieved a **perfect 100% win rate** against the archived baseline.  
> Truck waiting time was reduced by up to **96.7%** for 100-customer problems (5,443 s → 179.7 s).

---

## 🗺️ Live Dashboard & Route Visualizations

**👉 [mfstsp.streamlit.app](https://mfstsp.streamlit.app)**

The interactive Streamlit dashboard provides:
- **Results Dashboard** — KPI cards, win/loss scorecards, per-metric comparison tables and charts across all 100 benchmark instances
- **Maps Page** — Geospatial route visualizations for the best problem instance in each scenario group, with depot (⭐), truck route (solid blue), and UAV sorties (dashed orange)

### Sample Route Map — 50 Customers (Best Instance)
> OFV = 3,796.20 s | Truck Customers = 7 | UAV Customers = 43 | 20 UAV Sorties

![50-customer route map showing truck route in blue and UAV sorties in orange dashed lines across a geographic area](/readmeImgs/Screenshot%202026-06-09%20at%203.03.15 pm.png)

### Sample Route Map — 100 Customers (Best Instance)
> OFV = 6,404.18 s | Truck Customers = 19 | UAV Customers = 81 | 43 UAV Sorties

![100-customer route map showing truck route in blue and UAV sorties in orange dashed lines](/readmeImgs/Screenshot%202026-06-09%20at%203.03.28 pm.png)

---

## 📐 Problem Definition

The mFSTSP is defined over a node set **N = {0, 1, ..., c, c+1}**, where:
- Node `0` and `c+1` represent the **depot** (start and end)
- Nodes `1` through `c` are **customer delivery locations**
- The objective is to minimize **makespan C_max** — the time at which all deliveries are complete and all vehicles have returned to the depot

A **UAV sortie** is a triple **(i, j, k)** where:
- `i` = launch node (truck stop)
- `j` = customer served by UAV mid-flight
- `k` = recovery node (truck stop, after `i`)

### Feasibility Constraints Enforced (11 total)

1. Every customer is served **exactly once** (truck or UAV, never both)
2. No customer may be assigned to both truck route and a UAV sortie simultaneously
3. A customer cannot be served by two different UAV sorties
4. Only **drone-eligible** customers may be assigned to UAVs (payload/eligibility checks)
5. Each sortie duration must not exceed the **UAV endurance limit**
6. Launch and recovery nodes must remain on the **truck route**
7. A physical UAV cannot be used for two **overlapping sorties** (no double-booking)
8. Maximum **3 concurrent active UAV sorties** at any time (physical fleet size)
9. Truck and UAV timelines must be **synchronized** at each recovery node
10. Waiting times computed as: `wait = max(0, other_arrival − own_arrival)`
11. Truck route must remain a valid **Hamiltonian path** over truck-assigned customers

---

## 🧠 Scenario-Specific Optimization Strategies

A defining contribution of this framework is applying **distinct algorithms per customer-size scenario**, rather than a single general-purpose solver:

| Scenario | Algorithm | Key Parameters |
|----------|-----------|----------------|
| **8 customers** | Clarke-Wright Savings + Multi-Start Local Search | 16 restarts, 5 rounds, 80 trials/round |
| **10 customers** | Exact TSP Seed + UAV-Aware Micro Genetic Algorithm | 20 starts, 6 rounds, 90 trials |
| **25 customers** | Multi-Start Insertion Heuristic + Local Search | 22 starts, 6 rounds, 85 trials |
| **50 customers** | Memetic Genetic Algorithm (parallel-UAV-aware) | Pop 34, 60 gen, elite 5, mut 0.32, cx 0.92 |
| **100 customers** | Stronger Memetic GA + Exact Final Simulation | Pop 42, 78 gen, elite 6, mut 0.36 |

All scenarios include:
- **Physical 3-UAV fleet scheduling** with availability calendars (prevents double-booking)
- **UAV-count expansion phase** to maximize drone utilization within OFV tolerance
- **Event-based final simulation** for exact timing and feasibility validation

---

## 📁 Repository Structure

```
mFSTSP/
│
├── main.py                          # Entry point; dispatches heuristic or MILP solver
├── proposed_heuristic_no_gurobi.py  # Core heuristic (1,987 lines, 65.7 KB)
├── run_all_problems.py              # Batch execution across all 100 instances
├── parseCSV.py                      # Input file parsing utilities
│
├── Problems/                        # 100 benchmark problem instance directories
│   └── <problem_id>/
│       ├── tbl_locations.csv                              # Customer coordinates & metadata
│       ├── tbl_truck_travel_data_PG.csv                   # Travel times (OpenStreetMap/pgRouting)
│       └── tbl_solutions_101_3_NoGurobiHeuristic.csv      # Solver output (generated)
│
├── grouped_by_customers/            # Scenario-group problem ID lists
│   ├── customers_8.txt
│   ├── customers_10.txt
│   ├── customers_25.txt
│   ├── customers_50.txt
│   └── customers_100.txt
│
├── performance_summary.csv          # Our heuristic results (100 rows)
├── performance_summary_archive.csv  # Archived baseline results (reference)
│
├── frontend/
│   ├── result_dashboard.py          # Streamlit dashboard main module
│   ├── frontend_data/               # Pre-built comparison CSVs for dashboard
│   └── maps/
│       ├── run_all_maps.py          # Map generation script
│       └── generated/               # Pre-generated PNG map images + JSON metadata
│
├── create_comparison_dashboard_data.py  # Merges results, computes winners
├── group_problems_by_customers.py       # Organizes problem IDs into scenario files
└── app.py                               # Streamlit Community Cloud entry point
```

---

## ⚙️ Installation & Setup

### Prerequisites

- Python 3.8 or higher
- pip

### Clone the Repository

```bash
git clone https://github.com/omar-diab/mFSTSP.git
cd mFSTSP
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

Core dependencies: `pandas`, `matplotlib`, `streamlit`  
No commercial solver licenses required.

---

## 🚀 Usage

### Run a Single Problem Instance

```bash
python main.py <problemName> 101 3600 2 3 -1 1 1 3 1
```

**Arguments:**
| Argument | Value | Description |
|----------|-------|-------------|
| `problemName` | e.g. `20170608T121949065533` | Problem instance ID |
| `101` | UAV type ID | High speed, low range UAV |
| `3600` | Time limit (s) | Max solver time |
| `2` | Problem type | `2` = heuristic mode (no Gurobi) |
| `3` | UAV count | Physical fleet size |
| `-1` | Unused | — |
| `1 1 3 1` | Flags | Endurance model, output options |

### Run All 100 Benchmark Instances (Batch)

```bash
python run_all_problems.py
```

Results are written to `performance_summary.csv`. Expected total runtime: **< 4 hours** on a standard laptop.

### Generate Comparison Dashboard Data

```bash
python create_comparison_dashboard_data.py
```

Merges `performance_summary.csv` with `performance_summary_archive.csv`, computes per-metric winners, and exports dashboard-ready files to `frontend/frontend_data/`.

### Generate Route Map Images

```bash
python frontend/maps/run_all_maps.py
```

Produces five PNG route maps (one per scenario group, best instance) and five JSON metadata files in `frontend/maps/generated/`.

### Launch the Dashboard Locally

```bash
streamlit run frontend/result_dashboard.py
```

Or from the repository root (mirrors Streamlit Community Cloud setup):

```bash
streamlit run app.py
```

---

## 📊 Performance Metrics

Six metrics are evaluated per problem instance, with defined winner rules:

| Metric | Description | Winner |
|--------|-------------|--------|
| **OFV** | Total mission makespan (seconds) | Lower ↓ |
| **totalTime** | Wall-clock solver runtime (seconds) | Lower ↓ |
| **waitingTruck** | Cumulative truck idle time waiting for UAVs | Lower ↓ |
| **waitingUAV** | Cumulative UAV idle time waiting for truck | Lower ↓ |
| **numUAVcust** | Number of customers served by UAVs | Higher ↑ |
| **numTruckCust** | Number of customers served by truck | Lower ↓ |

Dashboard color coding: 🟢 our win · 🔴 their win · 🟡 tie

---

## 🔬 Technical Architecture

### Three-Phase Heuristic Design (aligned with Murray & Raj 2019)

```
Phase 1 — Customer Partitioning
  Clarke-Wright Savings (n=8) or GA chromosomes (n=50/100)
  → Decides which customers the truck serves vs. UAVs

Phase 2 — UAV Sortie Assignment
  Generates feasible (launch, customer, recovery) triples
  → Physical fleet manager prevents UAV double-booking

Phase 3 — Timing & Synchronization
  Event-based simulation (replaces Gurobi LP)
  → Propagates timing dependencies, minimizes makespan
```

### Key Data Structures

```python
@dataclass(frozen=True)
class CandidateSpec:
    # UAV sortie candidate as a route-position template
    # Enables fast approximate fitness evaluation during search
    launch_pos: int
    customer_id: int
    recovery_pos: int
    estimated_improvement: float

@dataclass
class ScheduledSortie:
    # Concrete time-stamped sortie from exact simulation
    uav_id: int
    launch_node: int
    customer: int
    recovery_node: int
    launch_time: float
    recovery_time: float

@dataclass
class SimulationResult:
    # Full schedule output including activity log
    ofv: float
    truck_route: list
    sorties: list[ScheduledSortie]
    waiting_truck: float
    waiting_uav: float
    is_valid: bool
```

### Genetic Algorithm (50/100-customer scenarios)

- **Selection:** Tournament selection (size 4/6)
- **Crossover:** Order crossover (OX), rate 0.92
- **Mutation:** Swap mutation, rate 0.32–0.36
- **Elitism:** Top 5–6 individuals preserved unchanged
- **Elite polishing:** Exact greedy parallel scheduler applied after main GA loop
- **UAV-count expansion:** Secondary phase maximizes `numUAVcust` within OFV tolerance

---

## 📈 UAV Utilization Analysis

The framework's synchronized scheduling dramatically reduces wasted truck idle time compared to the baseline:

| Scenario | Avg Truck Wait — Ours | Avg Truck Wait — Baseline | Reduction |
|----------|-----------------------|---------------------------|-----------|
| 8 cust. | 42.9 s | 441.0 s | 90.3% |
| 10 cust. | 47.0 s | 390.3 s | 87.9% |
| 25 cust. | 34.6 s | 1,479.2 s | 97.7% |
| 50 cust. | 96.0 s | 2,888.6 s | 96.7% |
| **100 cust.** | **179.7 s** | **5,443.5 s** | **96.7%** |

UAV utilization in best instances:

| Scenario | Best OFV (s) | UAV Customers | UAV Utilization |
|----------|-------------|---------------|-----------------|
| 8 cust. | 392.59 | 7/8 | 87.5% |
| 10 cust. | 570.78 | 8/10 | 80.0% |
| 25 cust. | 1,177.59 | 22/25 | 88.0% |
| 50 cust. | 3,796.20 | 43/50 | 86.0% |
| 100 cust. | 6,404.18 | 81/100 | 81.0% |

---

## 🧪 Reproducibility

All experiments are fully reproducible:

```python
RANDOM_SEED = 42  # Set at module level in proposed_heuristic_no_gurobi.py
```

All 100 benchmark instances use the original `tbl_locations.csv` and `tbl_truck_travel_data_PG.csv` files from the Murray & Raj (2019) reference repository without modification.

---

## 🗂️ Benchmark Dataset

- **100 problem instances** from the reference mFSTSP repository
- **5 scenario groups** × 20 instances each: 8, 10, 25, 50, 100 customers
- **Travel data** derived from OpenStreetMap via pgRouting (real-world road network)
- **UAV type:** ID 101 (high speed, low range), Endurance model Etype 3

---

## 🔭 Future Work

1. **Multi-objective optimization** — incorporate CO₂ emissions or energy consumption as secondary criteria
2. **Stochastic mFSTSP** — probabilistic travel times and uncertain UAV flight durations
3. **Real UAV telemetry integration** — geofencing APIs and live flight path constraints
4. **Reinforcement learning parameter tuning** — auto-configure scenario-specific GA settings
5. **Multi-truck fleet extension** — generalize from 1 truck to k trucks
6. **Real-time re-optimization** — dynamic rerouting as new orders arrive mid-mission

---

## 📚 References

- Murray, C., & Raj, R. (2019). The multiple flying sidekicks traveling salesman problem: Parcel delivery with multiple drones. *SSRN Working Paper*. https://doi.org/10.2139/ssrn.3338436
- Murray, C. C., & Chu, A. G. (2015). The flying sidekick traveling salesman problem. *Transportation Research Part C*, 54, 86–109.
- Clarke, G., & Wright, J. W. (1964). Scheduling of vehicles from a central depot. *Operations Research*, 12(4), 568–581.
- Holland, J. H. (1992). *Adaptation in Natural and Artificial Systems*. MIT Press.
- Agatz, N., Bouman, P., & Schmidt, M. (2018). Optimization approaches for the TSP with drone. *Transportation Science*, 52(4), 965–981.

---

## 👥 Team

| Student ID | Name | Department
|------------|------|------------|
| 2309055120 | Sojod Kasmi | Industrial Engineering
| 2309085265 | Abdurrahman Hatir | Industrial Engineering
| 2305025325 | Lina El Frourgi | Computer Engineering
| 220911379 | Omar Diab | Software Engineering
| 220911683 | Muhammed R Y Altaweel | Software Engineering

**Course Instructors:** Assoc. Prof. Dr. Emre Çakma · Assoc. Prof. Dr. Noyan Sebla Sezer  
**Institution:** Istinye University, Faculty of Engineering and Natural Sciences

---

<p align="center">
  <a href="https://mfstsp.streamlit.app"><strong>🚀 View Live Dashboard</strong></a> ·
</p>
