"""Independent check of a finished, timed schedule.

It does not reuse the evaluator's logic: it reads the times the evaluator
wrote and checks each rule of the paper's model directly. Every reported
ALNS result is passed through verify_schedule().
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from ..data.models import ProblemInstance
from .models import ScheduleResult, Sortie
from .validation import positions, validate_structure

TOL = 1e-5


def verify_schedule(instance: ProblemInstance, route: List[int], sorties: List[Sortie],
                    sched: ScheduleResult) -> List[str]:
    errors = list(validate_structure(instance, route, sorties))
    if errors:
        return errors
    if not sched.feasible or not sched.operations:
        return ["no detailed schedule to verify"]
    tau = instance.truck_time
    last = len(route) - 1
    arr, dep = sched.truck_arrival, sched.truck_departure

    # Truck: starts at 0, travels exactly tau between stops, leaves after it arrives.
    if abs(arr[0]) > TOL:
        errors.append("truck does not start at time 0")
    for p in range(last):
        if abs(arr[p + 1] - (dep[p] + tau[route[p]][route[p + 1]])) > TOL:
            errors.append("truck travel time wrong between positions %d and %d" % (p, p + 1))
        if dep[p] < arr[p] - TOL:
            errors.append("truck leaves position %d before arriving" % p)

    ops: Dict[Tuple[int, str, int], Tuple[float, float]] = {}
    by_pos: Dict[int, List[Tuple[str, float, float]]] = {}
    for p, kind, ident, start, end in sched.operations:
        key = (p, kind, ident)
        if key in ops:
            errors.append("operation %s appears twice" % (key,))
        ops[key] = (start, end)
        by_pos.setdefault(p, []).append((kind, start, end))
        if start < arr[p] - TOL or end > dep[p] + TOL:
            errors.append("operation %s happens while the truck is not at the stop" % (key,))

    # Truck deliveries.
    for p in range(1, last):
        j = route[p]
        o = ops.get((p, "S", j))
        if o is None:
            errors.append("no delivery for truck customer %d" % j)
        elif abs((o[1] - o[0]) - instance.nodes[j].truck_service) > TOL:
            errors.append("delivery at %d has the wrong duration" % j)

    # One operation at a time (driver); launches/recoveries always one at a time.
    for p, items in by_pos.items():
        seq = sorted(i for i in items if instance.require_driver or i[0] != "S")
        seq.sort(key=lambda x: x[1])
        for (k1, s1, e1), (k2, s2, e2) in zip(seq, seq[1:]):
            if s2 < e1 - TOL:
                errors.append("overlapping operations at position %d (%s and %s)" % (p, k1, k2))

    pos = positions(route)
    per_uav: Dict[int, List[Tuple[float, float]]] = {}
    for s in sorties:
        a = pos[s.launch_node]
        b = last if s.recovery_node == 0 else pos[s.recovery_node]
        u = instance.uavs[s.uav_id]
        lo = ops.get((a, "L", s.uav_id))
        ro = ops.get((b, "R", s.uav_id))
        if lo is None or ro is None:
            errors.append("sortie %s has no launch or recovery operation" % (s,))
            continue
        if abs((lo[1] - lo[0]) - u.launch_time) > TOL:
            errors.append("launch of %s has the wrong duration" % (s,))
        if abs((ro[1] - ro[0]) - u.recovery_time) > TOL:
            errors.append("recovery of %s has the wrong duration" % (s,))
        flight = instance.sortie_flight_time(s.uav_id, s.launch_node, s.customer_id, s.recovery_node)
        if ro[0] < lo[1] + flight - TOL:
            errors.append("sortie %s is recovered before it can fly back" % (s,))
        limit = instance.endurance(s.uav_id, s.launch_node, s.customer_id, s.recovery_node)
        if ro[0] - lo[1] > limit + TOL:
            errors.append("sortie %s exceeds its endurance (%.1f > %.1f s)" % (s, ro[0] - lo[1], limit))
        per_uav.setdefault(s.uav_id, []).append((lo[0], ro[1]))
    for v, spans in per_uav.items():
        spans.sort()
        for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
            if s2 < e1 - TOL:
                errors.append("UAV %d starts a launch before its previous recovery ends" % v)

    end = max([dep[last]] + [e for (_, _, e) in sum(by_pos.values(), [])])
    if abs(sched.makespan - dep[last]) > TOL or end > dep[last] + TOL:
        errors.append("makespan does not match the last activity")
    return errors
