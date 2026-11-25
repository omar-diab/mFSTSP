"""Local improvement after repair (guide section 10).

* Reinsertion: take each customer out and put it back at its best option.
  This covers truck relocate, sortie relocation (other launch/recovery
  stops), UAV reassignment and service-mode change (truck <-> UAV).
* Truck 2-opt: reverse a stretch of the truck route.
Every move is checked with the full evaluator before it is kept.
"""

from __future__ import annotations

import random
import time

from ..solution.models import Solution
from .insertion import Evaluator, insert_customer, insertion_options, remove_customers

EPS = 1e-6


def reinsertion_pass(ev: Evaluator, sol: Solution, cfg, rng: random.Random, deadline: float) -> Solution:
    """Move single customers. A move is fully evaluated only when the estimate says it can help."""
    best = sol
    order = list(ev.instance.customers)
    rng.shuffle(order)
    for j in order:
        if time.time() > deadline:
            break
        route, sorties, removed = remove_customers(best.route, best.sorties, [j])
        if removed != [j]:
            continue  # j is a launch/recovery stop; moving it is left to destroy/repair
        partial = ev(route, sorties, partial=True, policies=(best.schedule.policy,))
        if not partial.feasible:
            continue
        saving = best.objective - partial.makespan
        opts = insertion_options(ev.instance, route, sorties, partial, j, cfg.max_sortie_span)
        if not opts or opts[0][0] >= saving - EPS:
            continue
        opts = [o for o in opts if o[0] < saving - EPS]
        res = insert_customer(ev, route, sorties, partial, j, cfg, partial=True, opts=opts)
        if res is None:
            continue
        cand = ev.full(Solution(res[0], res[1]))
        if cand.feasible and cand.objective < best.objective - EPS:
            best = cand
    return best


def two_opt_pass(ev: Evaluator, sol: Solution, rng: random.Random, deadline: float, max_len: int = 12) -> Solution:
    tau = ev.instance.truck_time
    best = sol
    r = best.route
    n = len(r)
    for i in range(1, n - 2):
        if time.time() > deadline:
            break
        for k in range(i + 1, min(n - 1, i + max_len)):
            r = best.route
            if k >= len(r) - 1:
                break
            seg = r[i:k + 1]
            old = tau[r[i - 1]][r[i]] + sum(tau[a][b] for a, b in zip(seg, seg[1:])) + tau[r[k]][r[k + 1]]
            rev = seg[::-1]
            new = tau[r[i - 1]][rev[0]] + sum(tau[a][b] for a, b in zip(rev, rev[1:])) + tau[rev[-1]][r[k + 1]]
            if new >= old - EPS:
                continue
            cand = ev.full(Solution(r[:i] + rev + r[k + 1:], list(best.sorties)))
            if cand.feasible and cand.objective < best.objective - EPS:
                best = cand
    return best


def truck_reoptimization(ev: Evaluator, sol: Solution, cfg, rng: random.Random) -> Solution:
    """Shorten the truck tour (or-opt + 2-opt on travel time), keep every sortie that still fits,
    and reinsert the customers of sorties whose launch would now come after their recovery."""
    from ..construction.initial_solution import improve_tour
    tau = ev.instance.truck_time
    new_route = improve_tour(tau, sol.route)
    if new_route == sol.route:
        return sol
    pos = {n: i for i, n in enumerate(new_route[:-1])}
    last = len(new_route) - 1
    keep, broken = [], []
    for s in sol.sorties:
        a = pos[s.launch_node]
        b = last if s.recovery_node == 0 else pos[s.recovery_node]
        (keep if a < b else broken).append(s)
    # A UAV's sorties must not overlap on the new route either.
    by_uav = {}
    for s in keep:
        by_uav.setdefault(s.uav_id, []).append(s)
    keep2 = []
    for v, items in by_uav.items():
        items.sort(key=lambda s: pos[s.launch_node])
        end = -1
        for s in items:
            a = pos[s.launch_node]
            b = last if s.recovery_node == 0 else pos[s.recovery_node]
            if a >= end:
                keep2.append(s)
                end = b
            else:
                broken.append(s)
    route, sorties = new_route, keep2
    partial = ev(route, sorties, partial=True)
    if not partial.feasible:
        return sol
    for s in broken:
        res = insert_customer(ev, route, sorties, partial, s.customer_id, cfg, partial=True)
        if res is None:
            return sol
        route, sorties, partial = res
    cand = ev.full(Solution(route, sorties))
    if cand.feasible and cand.objective < sol.objective - EPS:
        return cand
    return sol


def improve(ev: Evaluator, sol: Solution, cfg, rng: random.Random, deadline: float) -> Solution:
    best = sol
    for _ in range(max(1, cfg.local_search_max_passes)):
        before = best.objective
        best = truck_reoptimization(ev, best, cfg, rng)
        best = two_opt_pass(ev, best, rng, deadline)
        best = reinsertion_pass(ev, best, cfg, rng, deadline)
        if best.objective >= before - EPS or time.time() > deadline:
            break
    return best
