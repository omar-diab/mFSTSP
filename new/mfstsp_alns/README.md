# mfstsp_alns — our ALNS for the mFSTSP

An Adaptive Large Neighborhood Search for the multiple flying sidekicks TSP
(one truck, up to four UAVs), built as an independent Python package. It needs
no Gurobi license and follows the rules of the Murray & Raj (2019) model, so its
makespans can be compared with the paper's.

This is our proposed method. It is not the paper's three-phase heuristic.

## Run it (from `new/`)

```bash
python run_alns.py 20170608T121355407419 104 4 --time 5     # one problem: name, vehicle file, number of UAVs
python run_alns_benchmark.py --workers 4                    # the 1,600 settings of the paper's heuristic (resumes)
python -m mfstsp_alns.evaluation.validate_evaluator         # re-time the paper's own solutions with our evaluator
python -m pytest mfstsp_alns/tests -q                       # unit tests
```

Only the standard library is needed to run (pandas/pytest for tests and scripts).

Outputs:

| File | Content |
|---|---|
| `results/alns/alns_results.csv` | one row per run: makespan, runtime, iterations, verified, … |
| `results/alns/solutions/<problem>_<vehicle>_<uavs>.json` | truck route, sorties, every start/end time, improvement history, settings |
| `results/alns/evaluator_validation.csv` | our evaluator on each of the paper's 1,920 saved solutions |

## Model (same as every paper run)

* Etype 1: the paper's non-linear energy model (`data/endurance.py`, ported line by line).
  The time from launch to recovery, **including hovering**, must fit the battery.
* Driver required: at a stop the delivery, each launch and each recovery happen one at a time.
* The truck must end at the depot; makespan = truck back with every UAV recovered.
* UAV travel times use the paper's own `distance_functions.py` (copied as `data/paper_distance.py`).

## Layout

```
data/          instance model, loader (reads old/Problems), endurance, UAV travel times
solution/      Solution / Sortie, structural checks, independent schedule verifier
scheduling/    evaluator.py: resource-aware list scheduler (36 priority policies)
construction/  initial solution: truck TSP + moving customers to UAVs
operators/     destroy (7), repair (3), insertion helpers, local search
alns/          config, adaptive weights, simulated annealing, main loop
evaluation/    benchmark runner, paper-solution reader, evaluator validation
tests/         hand-checkable tiny instances + operator / reproducibility tests
```

## How we know the timing is right

1. **Paper solutions:** we re-timed all 1,920 solutions the paper saved. All 320
   exact-model plans are feasible with our rules; on 193 of the 212 proven optima we get
   the same makespan, and we never get a shorter one than a proven optimum (that would mean
   a broken rule).
2. **Independent verifier** (`solution/verify.py`): re-reads every start/end time and checks each
   rule directly. Every ALNS result is verified before it is saved.
3. **Unit tests** on tiny instances whose schedules are worked out by hand.

The evaluator is a heuristic for the timing (not an exact solver): it never breaks a rule,
but on some plans it finds a slower timing than the paper's exact model.

## Settings

All in `alns/config.py`, saved with every solution, and overridable with a JSON file
(`python run_alns_benchmark.py --config my.json`).
