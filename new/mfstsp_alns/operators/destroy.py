"""Destroy operators (guide section 6).

Each operator picks q customers to unassign from a complete solution and
returns (customers, hints). hints maps a customer to the service mode the
repair should avoid ('T' truck / 'D' drone); only mode_change uses it.
"""

from __future__ import annotations

import random
from typing import Dict, List, Tuple

from ..data.models import ProblemInstance
from ..solution.models import Solution
from ..solution.validation import positions


def _pick_ranked(scores: Dict[int, float], q: int, rng: random.Random, power: float = 3.0) -> List[int]:
    """Randomised greedy pick of the highest scores (Ropke & Pisinger: y^p selection)."""
    pool = sorted(scores, key=lambda c: scores[c], reverse=True)
    chosen = []
    while pool and len(chosen) < q:
        idx = int((rng.random() ** power) * len(pool))
        chosen.append(pool.pop(idx))
    return chosen


def random_removal(inst: ProblemInstance, sol: Solution, q: int, rng: random.Random):
    return rng.sample(inst.customers, min(q, len(inst.customers))), {}


def worst_removal(inst: ProblemInstance, sol: Solution, q: int, rng: random.Random):
    """Customers whose service costs the most: truck detours, and sorties with long waits."""
    tau = inst.truck_time
    r = sol.route
    scores: Dict[int, float] = {}
    for p in range(1, len(r) - 1):
        a, j, b = r[p - 1], r[p], r[p + 1]
        scores[j] = tau[a][j] + inst.nodes[j].truck_service + tau[j][b] - tau[a][b]
    timing = {t.sortie.customer_id: t for t in (sol.schedule.sorties if sol.schedule else [])}
    for s in sol.sorties:
        u = inst.uavs[s.uav_id]
        t = timing.get(s.customer_id)
        hover = t.hover if t else 0.0
        scores[s.customer_id] = u.launch_time + u.recovery_time + hover
    return _pick_ranked(scores, q, rng), {}


def related_removal(inst: ProblemInstance, sol: Solution, q: int, rng: random.Random):
    """A seed customer and the customers closest to it (by truck travel time)."""
    tau = inst.truck_time
    seed = rng.choice(inst.customers)
    others = sorted((c for c in inst.customers if c != seed),
                    key=lambda c: tau[seed][c] + tau[c][seed])
    return [seed] + others[:max(0, q - 1)], {}


def high_wait_removal(inst: ProblemInstance, sol: Solution, q: int, rng: random.Random):
    """Sorties that make the truck or the UAV wait, and the truck stop where it happens."""
    sched = sol.schedule
    scores: Dict[int, float] = {}
    if sched and sched.sorties:
        pos = positions(sol.route)
        last = len(sol.route) - 1
        stop_wait = {}
        for p in range(len(sol.route)):
            busy = sum(e - s for (pp, _, _, s, e) in sched.operations if pp == p)
            stop_wait[p] = max(0.0, sched.truck_departure[p] - sched.truck_arrival[p] - busy)
        for t in sched.sorties:
            s = t.sortie
            b = last if s.recovery_node == 0 else pos[s.recovery_node]
            scores[s.customer_id] = t.hover + stop_wait.get(b, 0.0)
            if s.recovery_node != 0:
                scores[s.recovery_node] = scores.get(s.recovery_node, 0.0) + stop_wait.get(b, 0.0)
    if not scores:
        return random_removal(inst, sol, q, rng)
    return _pick_ranked(scores, q, rng), {}


def expensive_sortie_removal(inst: ProblemInstance, sol: Solution, q: int, rng: random.Random):
    """Sorties close to their battery limit or with long flights."""
    sched = sol.schedule
    if not sched or not sched.sorties:
        return random_removal(inst, sol, q, rng)
    scores = {t.sortie.customer_id: (t.airborne / t.endurance if t.endurance > 0 else 1.0)
              for t in sched.sorties}
    return _pick_ranked(scores, q, rng), {}


def mode_change_removal(inst: ProblemInstance, sol: Solution, q: int, rng: random.Random):
    """Random customers that the repair must try to serve the other way (truck <-> UAV)."""
    chosen = rng.sample(inst.customers, min(q, len(inst.customers)))
    uav = set(sol.uav_customers())
    hints = {c: ("D" if c in uav else "T") for c in chosen}
    return chosen, hints


def segment_removal(inst: ProblemInstance, sol: Solution, q: int, rng: random.Random):
    """A run of consecutive truck stops (their sorties go with them)."""
    inner = sol.route[1:-1]
    if not inner:
        return random_removal(inst, sol, q, rng)
    length = max(1, min(len(inner), q // 2 + 1))
    start = rng.randrange(0, len(inner) - length + 1)
    return inner[start:start + length], {}


DESTROY_OPERATORS = {
    "random": random_removal,
    "worst": worst_removal,
    "related": related_removal,
    "high_wait": high_wait_removal,
    "expensive_sortie": expensive_sortie_removal,
    "mode_change": mode_change_removal,
    "segment": segment_removal,
}
