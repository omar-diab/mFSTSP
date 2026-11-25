"""Repair operators (guide section 7). Every removed customer is reinserted.

Each insertion picks among the best estimated options by a full schedule
evaluation. Truck, UAV-type and launch/recovery choices are all part of the
option list, so a repair can move a customer between truck and UAV, change
its UAV, or change its launch/recovery stops.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional

from ..solution.models import Solution
from .insertion import Evaluator, insert_customer, insertion_options

INF = float("inf")


def _repair_in_order(ev: Evaluator, sol: Solution, order: List[int], hints: Dict[int, str], cfg) -> Optional[Solution]:
    route, sorties = list(sol.route), list(sol.sorties)
    sched = ev(route, sorties, partial=True)
    if not sched.feasible:
        return None
    for j in order:
        res = insert_customer(ev, route, sorties, sched, j, cfg, partial=True, forbid_mode=hints.get(j))
        if res is None:
            return None
        route, sorties, sched = res
    return Solution(route, sorties)


def greedy_repair(ev, sol, removed, hints, cfg, rng: random.Random):
    """Insert in random order, each at its best option."""
    order = list(removed)
    rng.shuffle(order)
    return _repair_in_order(ev, sol, order, hints, cfg)


def constrained_first_repair(ev, sol, removed, hints, cfg, rng: random.Random):
    """Customers with the fewest UAV options (e.g. heavy parcels last) first."""
    route, sorties = sol.route, sol.sorties
    sched = ev(route, sorties, partial=True)
    if not sched.feasible:
        return None
    counts = {j: sum(1 for o in insertion_options(ev.instance, route, sorties, sched, j, cfg.max_sortie_span)
                     if o[1] == "D") for j in removed}
    order = sorted(removed, key=lambda j: (counts[j], rng.random()))
    return _repair_in_order(ev, sol, order, hints, cfg)


def regret_repair(ev, sol, removed, hints, cfg, rng: random.Random):
    """Regret-k: insert first the customer that loses most if it is not inserted now."""
    k = max(2, int(cfg.regret_k))
    route, sorties = list(sol.route), list(sol.sorties)
    sched = ev(route, sorties, partial=True)
    if not sched.feasible:
        return None
    left = list(removed)
    while left:
        best_j, best_regret, best_opts = None, -INF, None
        for j in left:
            opts = insertion_options(ev.instance, route, sorties, sched, j, cfg.max_sortie_span, hints.get(j))
            if not opts:
                opts = insertion_options(ev.instance, route, sorties, sched, j, cfg.max_sortie_span)
            if not opts:
                continue
            costs = [o[0] for o in opts[:k]]
            regret = sum(c - costs[0] for c in costs[1:]) if len(costs) > 1 else INF
            if regret > best_regret or (regret == best_regret and rng.random() < 0.5):
                best_j, best_regret, best_opts = j, regret, opts
        if best_j is None:
            return None
        res = insert_customer(ev, route, sorties, sched, best_j, cfg, partial=True,
                              forbid_mode=hints.get(best_j), opts=best_opts)
        if res is None:
            return None
        route, sorties, sched = res
        left.remove(best_j)
    return Solution(route, sorties)


REPAIR_OPERATORS = {
    "greedy": greedy_repair,
    "constrained_first": constrained_first_repair,
    "regret": regret_repair,
}
