# Gurobi mFSTSP test report

## Outcome

Gurobi 13.0.3 is installed and operational in the isolated environment.
The active license is **Restricted size-limited (not full Academic); expires 2027-11-29**. It is not a full Academic License.
The tiny one-variable license smoke test returned OPTIMAL; it is not a benchmark result.

The existing full MILP was actually invoked on the 8-customer instance. It created
**644 variables and 4347 constraints**. Optimization was rejected
with **Gurobi error 10010: model too large for size-limited license**. No incumbent was found,
no objective/bound/gap was obtained, and no optimality proof exists for this run. Raw status 1
means the model remained LOADED; this is neither INFEASIBLE nor TIME_LIMIT.

The restricted license permits at most 2,000 variables and 2,000 linear constraints
([official explanation](https://support.gurobi.com/hc/en-us/articles/29682074018833-What-does-Restricted-license-for-non-production-use-only-mean)).
The constraint count alone blocks this 8-customer model. The size-limit error is not evidence
that Gurobi cannot solve the problem with a full license.

Following the requested stop-on-serious-error rule, **no larger benchmark was attempted**.
There are no fabricated results or placeholder solver logs for unexecuted tests.

| Customers | Instance (first ID in each existing size list) | Outcome | End-to-end runtime |
|---|---|---|---|
| 8 | 20170608T121355407419 | LICENSE_SIZE_LIMIT | 0.555 s |
| 10 | 20170608T121632668184 | NOT_RUN | Not run |
| 25 | 20170606T113038113409 | NOT_RUN | Not run |
| 50 | 20170606T114000833192 | NOT_RUN | Not run |
| 100 | 20170606T115437348436 | NOT_RUN | Not run |

## Environment and experimental configuration

- Repository: `C:\Users\USER\Desktop\mFSTSP`; branch `AHMED`, upstream `origin/AHMED`.
- Existing uncommitted frontend work was present and preserved.
- Python interpreter: `C:\Users\USER\Desktop\mFSTSP\experiments\gurobi_test\.venv\Scripts\python.exe`; Python 3.14.7.
- The system Python initially had no gurobipy. Only `gurobipy==13.0.3`
  was installed in `experiments/gurobi_test/.venv`; system site packages are disabled.
- Vehicle file 101; **3 UAVs and 1 physical truck**; depot return and driver required; Etype 1.
  Legacy `numTrucks=-1` in summaries is a CLI sentinel, not a negative physical fleet size.
- Test instances are deterministic first entries in `grouped_by_customers/customers_N.txt`,
  not claimed to be statistically representative of all instances at that size.
- Location row counts, full truck travel matrix row counts, and vehicle input availability
  were checked for every planned instance. All five input sets are available.
- Each process has a 1,200-second hard wall limit. The actual 8-customer model TimeLimit
  was 1199.456668 seconds, reduced for input/model preparation.
  It failed after 0.555002 seconds, before numerical optimization.
  No time limit was removed. The hard process limit includes worker startup/build/extraction;
  the solver TimeLimit only bounds optimize().
- Hardware recorded by Gurobi: Intel Core Ultra 9 275HX, 24 physical / 24 logical cores,
  Windows. Detailed output is in the logs.

## Which algorithm was tested

- `main.py` currently rejects problemType 1 and runs only the No-Gurobi implementation
  for problemType 2. Running `python main.py ... 1 ...` is NOT a valid exact-solver command.
  Its constructor also writes existing solution/result paths; it was never instantiated.
- `solve_mfstsp_IP.solve_mfstsp_IP(node, vehicle, travel, cutoffTime, depotFlag, driverFlag, Etype)`
  constructs the complete joint routing/assignment/timing MILP as implemented in this repository.
  This is the tested solver, not a TSP-only test and not the Gurobi-assisted heuristic.
- The IP source includes an extra `MIN.LTL` lower bound on truck customers, explicitly marked
  `NOT IN THE IP MODEL` in its comment. Any future optimality certificate applies to this
  implemented model/configuration, not automatically every formulation of mFSTSP.
- The original `solve_mfstsp_heuristic.py` uses phase 1 partitioning/truck TSP, phase 2 UAV assignment,
  and phase 3 Gurobi timing, plus local search. `solve_tsp_callback.py` solves truck TSP using
  lazy subtour constraints with a hard-coded 600-second limit. `checkP2Feasibility.py` constructs
  a feasibility assignment model with SolutionLimit=1 but no explicit TimeLimit.
  Solving those subproblems to optimality does not establish global mFSTSP optimality.
- `mfstsp_heuristic_2_asgn_uavs.py` imports Gurobi but does not itself call optimize().
  `mfstsp_heuristic_3_timing.py` accepts a per-model cutoff.
- The legacy IP result-extraction logic reads objVal without first reliably testing SolCount
  and marks some non-TIME_LIMIT statuses as optimal. The observer records native Gurobi Status,
  SolCount, ObjBound and MIPGap before that code runs. Optimality is accepted only for GRB.OPTIMAL.
  No algorithm source or formulation was changed.

## Actual execution command

```powershell
Set-Location C:\Users\USER\Desktop\mFSTSP
.\experiments\gurobi_test\.venv\Scripts\python.exe -B -u experiments/gurobi_test/run_benchmarks.py
```

This experiment-only adapter reuses the existing input reader (without its constructor),
vehicle/node/travel classes, UAV travel-time function, and exact MILP function.
An observer subclass enables logs, enforces the remaining time budget, and captures solver
attributes. It adds no optimization constraints, relaxations, alternate algorithms or warm starts.
It refuses to overwrite recorded results; **do not rerun into this completed directory**.
The runner metadata describes the license/version observed for this session; it must be refreshed
in a separate output directory after license activation rather than reusing stale metadata.

## Comparisons with recorded results

There is **no new feasible Gurobi objective or runtime-to-solution**, so quality/runtime
differences against either baseline are unavailable. Failure-to-license runtime is not solve runtime.

For the same 8-customer instance, vehicle 101 and 3 UAVs, the archive contains:

| Archived method | Etype | Budget | Recorded makespan | Recorded runtime | Recorded proof flag |
|---|---|---|---|---|---|
| IP | 1 | 3,600 s | 3257.554229 s | 7.705566 s | isOptimal=True (archive claim) |
| Original heuristic | 1 | 5 s | 3282.737488 s | 0.041588 s | isOptimal=False |

These are existing records, not new measurements or independently verified proofs. Hardware,
solver version and execution budgets differ; no controlled runtime comparison is made.
Local No-Gurobi rows for that instance use Etype 3 and include repeated runs. Current main.py
also approximates endurance by a range-based fixed allowance rather than the original Etype 1
energy model. Identical instance IDs and a makespan objective alone do not make these results
comparable. No cross-model improvement percentage is calculated.
All matching vehicle/instance reference records, without best-run cherry-picking, are exported
to `existing_reference_rows.csv` with source record numbers and comparison limitations.

## What is required next

1. Obtain a full-size academic license if eligible. Register as an academic user and request
   an Academic Named-User license in the Gurobi User Portal.
2. On this Windows machine, use the portal's exact `grbgetkey YOUR-LICENSE-KEY` command while
   connected to the university network or a full-tunnel university VPN. Obtain grbgetkey from
   the official Gurobi tools/Optimizer installer if it is not installed. Accept the recommended
   license-file location. Do not put keys or license secrets in this repository/chat.
3. Alternatively configure an eligible Academic WLS license using the official WLS instructions.
   Do not confuse an active restricted license with a full-size academic entitlement.
4. Verify that the isolated Python process now detects the academic/full-size license. Preserve
   these results, refresh experiment metadata, and use a new run directory for the five-size pilot.
5. Only after a successful pilot, plan an all-100-instance sweep with matching vehicle/endurance/
   driver/depot settings, fixed limits, checkpointed logs and sufficient memory. At a sequential
   20-minute cap, 100 tests can consume up to **33 hours 20 minutes**, excluding setup/analysis.
   Full licensing removes size limits but cannot guarantee 50/100-customer optimality within 20 minutes.

Official guidance:
- [Academic license eligibility/setup](https://support.gurobi.com/hc/en-us/articles/360040541251-How-do-I-obtain-a-free-academic-license)
- [Retrieve an Academic Named-User license](https://support.gurobi.com/hc/en-us/articles/13207658935185-How-do-I-retrieve-an-Academic-Named-User-license)

## Saved artifacts and preservation

- `gurobi_test_results.csv`: five planned sizes; measured first attempt plus explicit NOT_RUN rows.
- `8_customers_console.log` and `8_customers_solver.log`: actual experiment/error evidence.
- `8_customers_result.json`: native model dimensions, error and measured wall runtime.
- `license_check.log`, `license_smoke_solver.log`, `environment_check.json`: installation/license evidence.
- `experiment_plan.json`: selected instances/configurations; `source_audit.json`: source hashes/functions.
- `data_preservation_check.json`: SHA-256 check of **2,357 input/result/source files**, all unchanged,
  with no unexpected additions to existing benchmark/result folders.

All new outputs are under `experiments/gurobi_test/`. No solver source, original benchmark result,
solution file, main branch, existing frontend work, commit or remote repository was modified by this test.
