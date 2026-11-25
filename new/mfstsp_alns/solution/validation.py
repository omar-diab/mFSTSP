"""Structural feasibility checks (guide section 8.1). No timing here."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..data.models import ProblemInstance
from .models import Sortie


def positions(route: List[int]) -> Dict[int, int]:
    """Route position of every truck node; the depot maps to position 0 (start)."""
    pos = {}
    for idx, node in enumerate(route[:-1]):
        pos[node] = idx
    return pos


def sortie_positions(route: List[int], pos: Dict[int, int], s: Sortie) -> Tuple[Optional[int], Optional[int]]:
    a = pos.get(s.launch_node)
    b = len(route) - 1 if s.recovery_node == 0 else pos.get(s.recovery_node)
    return a, b


def validate_structure(instance: ProblemInstance, route: List[int], sorties: List[Sortie],
                       partial: bool = False) -> List[str]:
    """Return a list of violations; an empty list means the plan is structurally valid.

    partial=True skips the "every customer is served" check (for partial plans during repair).
    """
    v: List[str] = []
    depot = instance.depot_id
    if len(route) < 2 or route[0] != depot or route[-1] != depot:
        v.append("route must start and end at the depot")
        return v
    inner = route[1:-1]
    if depot in inner:
        v.append("depot appears inside the route")
    if len(set(inner)) != len(inner):
        v.append("duplicate customer on the truck route")

    uav_customers = [s.customer_id for s in sorties]
    if len(set(uav_customers)) != len(uav_customers):
        v.append("customer served by two sorties")
    both = set(inner) & set(uav_customers)
    if both:
        v.append("customers on both truck and UAV: %s" % sorted(both))
    served = set(inner) | set(uav_customers)
    missing = set(instance.customers) - served
    if missing and not partial:
        v.append("customers not served: %s" % sorted(missing))
    extra = served - set(instance.customers)
    if extra:
        v.append("unknown nodes served: %s" % sorted(extra))

    pos = positions(route)
    by_uav: Dict[int, List[Tuple[int, int, Sortie]]] = {}
    for s in sorties:
        if s.uav_id not in instance.uavs:
            v.append("unknown UAV %d" % s.uav_id)
            continue
        a, b = sortie_positions(route, pos, s)
        if a is None or b is None:
            v.append("sortie %s: launch or recovery node not on the truck route" % (s,))
            continue
        if a >= b:
            v.append("sortie %s: recovery is not after launch" % (s,))
            continue
        if not instance.can_carry(s.uav_id, s.customer_id):
            v.append("sortie %s: parcel too heavy" % (s,))
        if not instance.sortie_possible(s.uav_id, s.launch_node, s.customer_id, s.recovery_node):
            v.append("sortie %s: minimum flight exceeds endurance" % (s,))
        by_uav.setdefault(s.uav_id, []).append((a, b, s))

    for uav, items in by_uav.items():
        items.sort(key=lambda x: (x[0], x[1]))
        for (a1, b1, s1), (a2, b2, s2) in zip(items, items[1:]):
            if a2 < b1:
                v.append("UAV %d reused before it is recovered (%s then %s)" % (uav, s1, s2))
    return v
