"""Coverage, structure, endurance, queues, UAV reuse and makespan on hand-checkable cases.

Run from new/:  python -m pytest mfstsp_alns/tests -q
"""

import random

import pytest

from mfstsp_alns.scheduling.evaluator import evaluate
from mfstsp_alns.solution.models import Sortie
from mfstsp_alns.solution.validation import validate_structure
from mfstsp_alns.solution.verify import verify_schedule

from .helpers import tiny_instance


# ---------- customer coverage and structure ----------

def test_truck_only_makespan_by_hand():
    inst = tiny_instance(3)
    res = evaluate(inst, [0, 1, 2, 3, 0], [], detailed=True)
    # 4 legs of 100 s + 3 deliveries of 30 s
    assert res.feasible and res.makespan == pytest.approx(490.0)
    assert verify_schedule(inst, [0, 1, 2, 3, 0], [], res) == []


def test_missing_customer_is_rejected():
    inst = tiny_instance(3)
    assert any("not served" in v for v in validate_structure(inst, [0, 1, 2, 0], []))


def test_customer_on_truck_and_uav_is_rejected():
    inst = tiny_instance(3)
    v = validate_structure(inst, [0, 1, 2, 3, 0], [Sortie(2, 1, 3, 2)])
    assert any("both truck and UAV" in x for x in v)


def test_duplicate_truck_customer_is_rejected():
    inst = tiny_instance(3)
    assert any("duplicate" in x for x in validate_structure(inst, [0, 1, 2, 2, 3, 0], []))


def test_recovery_before_launch_is_rejected():
    inst = tiny_instance(3)
    v = validate_structure(inst, [0, 1, 2, 0], [Sortie(2, 2, 3, 1)])
    assert any("not after launch" in x for x in v)


def test_launch_node_must_be_on_route():
    inst = tiny_instance(3)
    v = validate_structure(inst, [0, 1, 0], [Sortie(2, 2, 3, 0)])
    assert v  # 2 is neither on the route nor served


def test_heavy_parcel_cannot_fly():
    inst = tiny_instance(2, parcel=10.0)  # capacity 5 lbs
    v = validate_structure(inst, [0, 1, 0], [Sortie(2, 0, 2, 1)])
    assert any("too heavy" in x for x in v)


# ---------- one sortie by hand ----------

def test_single_sortie_timing_by_hand():
    inst = tiny_instance(2)
    route, sorties = [0, 1, 0], [Sortie(2, 0, 2, 1)]
    res = evaluate(inst, route, sorties, detailed=True)
    # depot: launch 0-60, truck leaves 60, arrives at 1 at 160.
    # UAV ready at 1: 60 + 50 + 60 + 50 = 220.
    # Policy R first: delivery runs 160-190 (UAV not ready), recovery 220-250, leave 250, back at 350.
    assert res.feasible
    assert res.makespan == pytest.approx(350.0)
    t = res.sorties[0]
    assert t.launch_done == pytest.approx(60.0)
    assert t.ready_at_recovery == pytest.approx(220.0)
    assert t.recovery_start == pytest.approx(220.0)
    assert verify_schedule(inst, route, sorties, res) == []


# ---------- queues ----------

def test_two_launches_at_one_stop_are_queued():
    inst = tiny_instance(3, n_uavs=2)
    route, sorties = [0, 1, 0], [Sortie(2, 0, 2, 1), Sortie(3, 0, 3, 1)]
    res = evaluate(inst, route, sorties, detailed=True)
    launches = sorted((s, e) for (p, k, i, s, e) in res.operations if k == "L")
    assert launches[0][1] <= launches[1][0] + 1e-9  # second starts after the first ends
    recoveries = sorted((s, e) for (p, k, i, s, e) in res.operations if k == "R")
    assert recoveries[0][1] <= recoveries[1][0] + 1e-9
    assert verify_schedule(inst, route, sorties, res) == []


def test_driver_cannot_deliver_and_launch_at_once():
    inst = tiny_instance(3, n_uavs=1)
    route, sorties = [0, 1, 2, 0], [Sortie(2, 1, 3, 2)]
    res = evaluate(inst, route, sorties, detailed=True)
    ops = sorted((s, e) for (p, k, i, s, e) in res.operations if p == 1)
    assert len(ops) == 2 and ops[0][1] <= ops[1][0] + 1e-9


def test_truck_waits_for_late_uav():
    inst = tiny_instance(2, uav_leg=400.0)  # long flight
    route, sorties = [0, 1, 0], [Sortie(2, 0, 2, 1)]
    res = evaluate(inst, route, sorties, detailed=True)
    # UAV ready at 1: 60 + 400 + 60 + 400 = 920; truck there at 160, done delivering at 190.
    assert res.truck_waiting == pytest.approx(920.0 - 190.0)
    assert res.makespan == pytest.approx(920 + 30 + 100)


def test_uav_hover_is_counted():
    inst = tiny_instance(2, truck_leg=1000.0)  # truck slow, UAV fast
    route, sorties = [0, 1, 0], [Sortie(2, 0, 2, 1)]
    res = evaluate(inst, route, sorties, detailed=True)
    t = res.sorties[0]
    assert t.hover > 0
    assert t.airborne == pytest.approx(t.recovery_start - t.launch_done)


# ---------- UAV reuse ----------

def test_uav_reuse_needs_recovery_first():
    inst = tiny_instance(4, n_uavs=1)
    overlapping = [Sortie(2, 0, 3, 2), Sortie(2, 1, 4, 0)]  # second launch before first recovery
    assert any("reused" in x for x in validate_structure(inst, [0, 1, 2, 0], overlapping))


def test_uav_relaunched_after_recovery_at_same_stop():
    inst = tiny_instance(4, n_uavs=1)
    route, sorties = [0, 1, 2, 0], [Sortie(2, 0, 3, 1), Sortie(2, 1, 4, 0)]
    res = evaluate(inst, route, sorties, detailed=True)
    assert res.feasible
    t1, t2 = res.sorties
    assert t2.launch_start >= t1.recovery_done - 1e-9
    assert verify_schedule(inst, route, sorties, res) == []


# ---------- endurance ----------

def test_endurance_boundary_fixed_model():
    # Etype 3 with battery 562990 J gives 1400 s. Flight = 2 * leg + 60 s service.
    ok = tiny_instance(2, endurance_type=3, uav_leg=670.0, truck_leg=10.0)   # 1400 s exactly
    too_long = tiny_instance(2, endurance_type=3, uav_leg=671.0, truck_leg=10.0)
    route, sorties = [0, 1, 0], [Sortie(2, 0, 2, 1)]
    assert ok.sortie_possible(2, 0, 2, 1)
    assert not too_long.sortie_possible(2, 0, 2, 1)
    assert evaluate(ok, route, sorties).feasible
    assert not evaluate(too_long, route, sorties).feasible


def test_hover_can_break_endurance():
    # Flight fits (1000 s) but the truck arrives very late, so hovering exceeds 1400 s.
    inst = tiny_instance(2, endurance_type=3, uav_leg=470.0, truck_leg=3000.0)
    res = evaluate(inst, [0, 1, 0], [Sortie(2, 0, 2, 1)])
    assert not res.feasible and "endurance" in res.violations[0]


# ---------- randomised consistency ----------

def test_random_plans_always_verify():
    rng = random.Random(0)
    inst = tiny_instance(6, n_uavs=2, uav_leg=120.0)
    checked = 0
    for _ in range(300):
        customers = list(range(1, 7))
        rng.shuffle(customers)
        k = rng.randint(0, 3)
        drone, truck = customers[:k], customers[k:]
        route = [0] + truck + [0]
        sorties = []
        free_from = {2: 0, 3: 0}
        if any(free_from[v] > len(route) - 2 for v in free_from):
            continue
        for j in drone:
            v = rng.choice([2, 3])
            if free_from[v] > len(route) - 2:
                break
            a = rng.randint(free_from[v], len(route) - 2)
            b = rng.randint(a + 1, len(route) - 1)
            sorties.append(Sortie(v, route[a], j, 0 if b == len(route) - 1 else route[b]))
            free_from[v] = b
        if len(sorties) != len(drone):
            continue
        res = evaluate(inst, route, sorties, detailed=True)
        if res.feasible:
            checked += 1
            assert verify_schedule(inst, route, sorties, res) == []
    assert checked > 50
