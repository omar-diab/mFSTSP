"""Operators never lose or duplicate customers; ALNS is reproducible and returns verified solutions."""

import random
from pathlib import Path

import pytest

from mfstsp_alns.alns.config import ALNSConfig
from mfstsp_alns.alns.solver import solve_alns
from mfstsp_alns.construction.initial_solution import construct_initial_solution
from mfstsp_alns.data.loader import load_instance
from mfstsp_alns.operators.destroy import DESTROY_OPERATORS
from mfstsp_alns.operators.insertion import Evaluator, remove_customers
from mfstsp_alns.operators.repair import REPAIR_OPERATORS
from mfstsp_alns.solution.validation import validate_structure
from mfstsp_alns.solution.verify import verify_schedule

PROBLEMS = Path(__file__).resolve().parents[3] / "old" / "Problems"
NAME = "20170608T121355407419"  # 8 customers; the paper's exact model proves 2397.07 s with vehicle 104, 4 UAVs


@pytest.fixture(scope="module")
def inst():
    return load_instance(PROBLEMS, NAME, 104, 4)


def test_loader_matches_paper_data(inst):
    assert inst.n_customers == 8
    assert len(inst.uavs) == 4
    assert inst.truck_time[0][1] == pytest.approx(31.022915)
    assert inst.nodes[2].parcel_lbs == 100.0  # too heavy for a UAV


def test_every_destroy_repair_pair_keeps_customers(inst):
    rng = random.Random(3)
    cfg = ALNSConfig()
    ev = Evaluator(inst)
    sol = construct_initial_solution(inst, ev, cfg, rng)
    assert validate_structure(inst, sol.route, sol.sorties) == []
    for d in DESTROY_OPERATORS:
        for r in REPAIR_OPERATORS:
            from mfstsp_alns.alns.solver import _detailed
            cur = _detailed(ev, ev.full(sol.copy()))
            chosen, hints = DESTROY_OPERATORS[d](inst, cur, 3, rng)
            route, sorties, removed = remove_customers(cur.route, cur.sorties, chosen)
            assert set(chosen) <= set(removed)
            served = set(route[1:-1]) | {s.customer_id for s in sorties}
            assert served.isdisjoint(removed)
            cand = REPAIR_OPERATORS[r](ev, type(sol)(route, sorties), removed, hints, cfg, rng)
            assert cand is not None, (d, r)
            assert validate_structure(inst, cand.route, cand.sorties) == [], (d, r)


def test_alns_reproducible_and_verified(inst):
    cfg = ALNSConfig(time_limit_seconds=None, max_iterations=150, time_limit_by_size={"8": 60.0, "100": 60.0})
    a = solve_alns(inst, cfg, seed=7)
    b = solve_alns(inst, cfg, seed=7)
    assert a.best.objective == pytest.approx(b.best.objective)
    assert a.best.route == b.best.route
    assert verify_schedule(inst, a.best.route, a.best.sorties, a.best.schedule) == []
    # best never gets worse over the run
    ms = [h["makespan"] for h in a.history]
    assert all(x >= y - 1e-9 for x, y in zip(ms, ms[1:]))
    # cannot beat the proven optimum
    assert a.best.objective >= 2397.07 - 0.01
