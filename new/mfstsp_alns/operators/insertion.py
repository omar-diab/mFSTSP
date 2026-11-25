"""Shared helpers for removing and inserting customers.

Insertion options are first ranked with a cheap estimate (built from the
current schedule's truck arrival/departure times); only the best few are
scheduled with the full evaluator, and only a full evaluation can make an
option feasible (guide section 7).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple

from ..data.models import ProblemInstance
from ..scheduling.evaluator import ALL_POLICIES, FAST_POLICIES, evaluate
from ..solution.models import ScheduleResult, Solution, Sortie

INF = float("inf")


class Evaluator:
    """Callable wrapper around evaluate() that counts calls."""

    def __init__(self, instance: ProblemInstance, policies=FAST_POLICIES, max_repairs: int = 3):
        self.instance = instance
        self.policies = tuple(policies)
        self.max_repairs = max_repairs
        self.calls = 0

    def __call__(self, route, sorties, partial=False, policies=None, detailed=False) -> ScheduleResult:
        self.calls += 1
        return evaluate(self.instance, route, sorties, policies or self.policies,
                        detailed=detailed, partial=partial, max_repairs=self.max_repairs)

    def full(self, solution: Solution) -> Solution:
        """Evaluate a complete solution with the search policies and attach the schedule."""
        solution.schedule = self(solution.route, solution.sorties)
        return solution

    def final(self, solution: Solution) -> Solution:
        """Best schedule over every policy, with full timing detail (for reporting)."""
        self.calls += 1
        solution.schedule = evaluate(self.instance, solution.route, solution.sorties, ALL_POLICIES,
                                     detailed=True)
        return solution


def uav_signature(instance: ProblemInstance, v: int) -> tuple:
    u = instance.uavs[v]
    return (u.takeoff_speed, u.cruise_speed, u.landing_speed, u.capacity_lbs, u.launch_time,
            u.recovery_time, u.battery_joules)


def remove_customers(route: List[int], sorties: List[Sortie], customers) -> Tuple[List[int], List[Sortie], List[int]]:
    """Unassign customers. A truck customer used as a launch/recovery point takes its sorties with it."""
    to_remove: Set[int] = set(customers)
    changed = True
    while changed:
        changed = False
        for s in sorties:
            if s.customer_id in to_remove:
                continue
            if s.launch_node in to_remove or (s.recovery_node != 0 and s.recovery_node in to_remove):
                to_remove.add(s.customer_id)
                changed = True
    new_route = [n for n in route if n == 0 or n not in to_remove]
    new_sorties = [s for s in sorties if s.customer_id not in to_remove]
    removed = [c for c in to_remove]
    return new_route, new_sorties, removed


def insertion_options(instance: ProblemInstance, route: List[int], sorties: Sequence[Sortie],
                      sched: ScheduleResult, j: int, max_span: int,
                      forbid_mode: Optional[str] = None, keep_long_hover: bool = True) -> List[Tuple[float, str, object]]:
    """All structurally possible ways to serve customer j, with an estimated makespan increase.

    Returns (estimate, 'T', position) for a truck insertion before route[position], and
    (estimate, 'D', Sortie) for a UAV sortie.
    """
    tau = instance.truck_time
    last = len(route) - 1
    arr, dep = sched.truck_arrival, sched.truck_departure
    opts: List[Tuple[float, str, object]] = []

    if forbid_mode != "T":
        sig = instance.nodes[j].truck_service
        for p in range(1, last + 1):
            a, b = route[p - 1], route[p]
            opts.append((tau[a][j] + sig + tau[j][b] - tau[a][b], "T", p))

    if forbid_mode != "D" and instance.uavs:
        # Busy position intervals per UAV.
        pos = {n: i for i, n in enumerate(route[:-1])}
        busy: Dict[int, List[Tuple[int, int]]] = {v: [] for v in instance.uavs}
        for s in sorties:
            a = pos.get(s.launch_node)
            b = last if s.recovery_node == 0 else pos.get(s.recovery_node)
            if a is not None and b is not None:
                busy[s.uav_id].append((a, b))
        seen_types = {}
        for v in instance.uav_ids():
            if not instance.can_carry(v, j):
                continue
            seen_types.setdefault(uav_signature(instance, v), []).append(v)
        for group in seen_types.values():
            v0 = group[0]
            u = instance.uavs[v0]
            t = instance.uav_time[v0]
            sj = instance.nodes[j].uav_service
            for a in range(0, last):
                la = route[a]
                out = t[la][j] + sj
                launch_done = dep[a] + u.launch_time
                for b in range(a + 1, min(last, a + max_span) + 1):
                    rb = 0 if b == last else route[b]
                    if la == rb and la != 0:
                        continue
                    flight = out + t[j][rb]
                    limit = instance.endurance(v0, la, j, rb)
                    if flight > limit:
                        continue
                    # First UAV of this type that is free over [a, b].
                    free = None
                    for v in group:
                        if all(not (a2 < b and a < b2) for a2, b2 in busy[v]):
                            free = v
                            break
                    if free is None:
                        continue
                    truck_at_b = arr[b] + u.launch_time
                    ready = launch_done + flight
                    est = u.launch_time + u.recovery_time + max(0.0, ready - truck_at_b)
                    # Would it hover too long? The evaluator can hold the launch back
                    # (the truck waits), so count that wait instead of dropping the option.
                    excess = max(ready, truck_at_b) - launch_done - limit
                    if excess > 0:
                        if not keep_long_hover:
                            continue
                        est += excess
                    opts.append((est, "D", Sortie(free, la, j, rb)))
    opts.sort(key=lambda o: o[0])
    return opts


def try_options(evaluator: Evaluator, route, sorties, j: int, opts, k: int, partial: bool,
                policies=None):
    """Fully evaluate up to k options (always including the best truck option) and return the best."""
    best = None
    chosen = opts[:k]
    if not any(o[1] == "T" for o in chosen):
        t = next((o for o in opts if o[1] == "T"), None)
        if t is not None:
            chosen = chosen + [t]
    for opt in chosen:
        if opt[1] == "T":
            r2 = route[:opt[2]] + [j] + route[opt[2]:]
            s2 = sorties
        else:
            r2 = route
            s2 = sorties + [opt[2]]
        res = evaluator(r2, s2, partial=partial, policies=policies)
        if res.feasible and (best is None or res.makespan < best[0]):
            best = (res.makespan, r2, s2, res, opt)
    return best


def insert_customer(evaluator: Evaluator, route, sorties, sched: ScheduleResult, j: int, cfg,
                    partial: bool, forbid_mode: Optional[str] = None, opts=None):
    """Insert j at its best fully evaluated option. Returns (route, sorties, schedule) or None."""
    inst = evaluator.instance
    keep = inst.n_customers <= cfg.hold_launch_options_up_to
    if opts is None:
        opts = insertion_options(inst, route, sorties, sched, j, cfg.max_sortie_span, forbid_mode, keep)
    if not opts and forbid_mode:
        opts = insertion_options(inst, route, sorties, sched, j, cfg.max_sortie_span, None, keep)
    policies = (sched.policy,) if sched.policy else None
    k = cfg.full_evaluations(inst.n_customers)
    best = try_options(evaluator, route, sorties, j, opts, k, partial, policies)
    if best is None and len(opts) > k:
        best = try_options(evaluator, route, sorties, j, opts[k:4 * k], 3 * k, partial, policies)
    if best is None:
        # Last resort: every truck position, every policy.
        truck = [o for o in opts if o[1] == "T"] or \
            [o for o in insertion_options(inst, route, sorties, sched, j, cfg.max_sortie_span) if o[1] == "T"]
        best = try_options(evaluator, route, sorties, j, truck, len(truck), partial, None)
    if best is None:
        return None
    return best[1], best[2], best[3]
