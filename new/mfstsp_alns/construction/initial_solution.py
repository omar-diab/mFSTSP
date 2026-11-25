"""Initial feasible solution (guide section 5).

1. Truck-only tour: nearest neighbour, then or-opt and 2-opt on the
   (asymmetric) road travel times.
2. Move customers to UAVs one at a time, hardest customers first, keeping a
   move only if the complete schedule stays feasible and the makespan drops.
"""

from __future__ import annotations

import random
from typing import List

from ..data.models import ProblemInstance
from ..solution.models import Solution
from ..operators.insertion import Evaluator, insert_customer, insertion_options, remove_customers

EPS = 1e-9


def tour_cost(tau, route: List[int]) -> float:
    return sum(tau[a][b] for a, b in zip(route, route[1:]))


def truck_tsp(instance: ProblemInstance) -> List[int]:
    tau = instance.truck_time
    left = set(instance.customers)
    route = [0]
    while left:
        cur = route[-1]
        nxt = min(left, key=lambda c: (tau[cur][c], c))
        route.append(nxt)
        left.remove(nxt)
    route.append(0)
    return improve_tour(tau, route)


def improve_tour(tau, route: List[int]) -> List[int]:
    """Or-opt (blocks of 1-3) and 2-opt until no move shortens the truck tour."""
    route = list(route)
    improved = True
    while improved:
        improved = False
        # or-opt: move a block of 1-3 customers to a better place (O(1) delta)
        for size in (1, 2, 3):
            n = len(route)
            for i in range(1, n - size):
                f, l = route[i], route[i + size - 1]
                prev, nxt = route[i - 1], route[i + size]
                gain = tau[prev][f] + tau[l][nxt] - tau[prev][nxt]
                rest = route[:i] + route[i + size:]
                best_p, best_d = None, 1e-6
                for p in range(1, len(rest)):
                    if p == i:
                        continue  # that is where the block came from
                    a, b = rest[p - 1], rest[p]
                    d = gain - (tau[a][f] + tau[l][b] - tau[a][b])
                    if d > best_d:
                        best_p, best_d = p, d
                if best_p is not None:
                    route = rest[:best_p] + route[i:i + size] + rest[best_p:]
                    improved = True
                    break
            if improved:
                break
        if improved:
            continue
        # 2-opt with prefix sums (the matrix is asymmetric, so reversed arcs are summed separately)
        n = len(route)
        fwd = [0.0] * n
        bwd = [0.0] * n
        for t in range(1, n):
            fwd[t] = fwd[t - 1] + tau[route[t - 1]][route[t]]
            bwd[t] = bwd[t - 1] + tau[route[t]][route[t - 1]]
        for i in range(1, n - 2):
            for k in range(i + 1, n - 1):
                old = tau[route[i - 1]][route[i]] + (fwd[k] - fwd[i]) + tau[route[k]][route[k + 1]]
                new = tau[route[i - 1]][route[k]] + (bwd[k] - bwd[i]) + tau[route[i]][route[k + 1]]
                if new < old - 1e-6:
                    route = route[:i] + route[i:k + 1][::-1] + route[k + 1:]
                    improved = True
                    break
            if improved:
                break
    return route


def construct_initial_solution(instance: ProblemInstance, ev: Evaluator, cfg, rng: random.Random) -> Solution:
    sol = ev.full(Solution(truck_tsp(instance), []))
    if not sol.feasible:
        raise RuntimeError("Truck-only tour is not feasible: %s" % sol.schedule.violations)
    if not instance.uavs:
        return sol

    # Constrained-first: customers with the fewest UAV options are tried first.
    sched = sol.schedule
    counts = {}
    for j in instance.customers:
        opts = insertion_options(instance, sol.route, sol.sorties, sched, j, cfg.max_sortie_span, "T")
        counts[j] = len(opts)
    order = [j for j in sorted(instance.customers, key=lambda j: (counts[j], j)) if counts[j] > 0]

    for j in order:
        if j not in sol.route:
            continue
        route, sorties, removed = remove_customers(sol.route, sol.sorties, [j])
        if removed != [j]:
            continue  # j is a launch/recovery stop; leave it on the truck
        partial = ev(route, sorties, partial=True)
        if not partial.feasible:
            continue
        res = insert_customer(ev, route, sorties, partial, j, cfg, partial=True, forbid_mode="T")
        if res is None:
            continue
        cand = ev.full(Solution(res[0], res[1]))
        if cand.feasible and cand.objective < sol.objective - EPS:
            sol = cand
    return sol
