"""Resource-aware schedule evaluator (guide section 8).

Given a truck route and a set of sorties, compute every start/end time and
the makespan, following the timing rules of the paper's MILP
(solve_mfstsp_IP.py, requireTruckAtDepot = requireDriver = True):

* The truck arrives at a stop, then the driver performs, one at a time:
  - truck delivery (sigma_j, customers only),
  - each UAV recovery (s_R), which can start only when the UAV is there,
  - each UAV launch (s_L); a UAV recovered at this stop is relaunched only
    after its recovery.
  Launches and recoveries are always one at a time (launch/recovery queue).
  With require_driver=False, the delivery runs in parallel to the queue.
* The truck leaves the stop when every operation there is finished.
* A UAV leaves the truck when its launch ends, flies tau'_{ij}, serves for
  sigma'_j, flies tau'_{jk}, then hovers until its recovery starts.
* Endurance: recovery start - launch end <= eee[v][i][j][k] (constraint 30),
  so hovering counts against the battery.
* Makespan: the time the truck finishes at the depot with every UAV recovered.

The order of operations at a stop is a decision. The evaluator is a list
scheduler: it tries several priority policies (which class of operation the
driver prefers when several are ready) and keeps the best feasible schedule.
It is a feasible-schedule heuristic, not an exact solver of the timing problem.
"""

from __future__ import annotations

from itertools import permutations
from typing import Dict, List, Optional, Sequence, Tuple

from ..data.models import ProblemInstance
from ..solution.models import ScheduleResult, Sortie, SortieTiming
from ..solution.validation import validate_structure

# A policy = (class order, launch order, chain):
#   class order: which kind of operation the driver prefers when several are ready
#                (R = recovery, S = truck delivery, L = launch)
#   launch order: "due"   -> the UAV that must be back earliest on the route goes first
#                 "long"  -> the UAV with the longest flight goes first
#                 "short" -> the UAV with the shortest flight goes first
#   chain: a UAV recovered at a stop is relaunched right after its own recovery
ALL_POLICIES: Tuple[Tuple, ...] = tuple(
    order + (lo, ch) for ch in (False, True) for lo in ("due", "long", "short")
    for order in permutations(("R", "S", "L")))
FAST_POLICIES: Tuple[Tuple, ...] = (
    ("R", "S", "L", "due", False), ("R", "L", "S", "due", False), ("L", "R", "S", "due", False),
    ("R", "S", "L", "short", True), ("L", "R", "S", "long", False))

INF = float("inf")
EPS = 1e-7


def evaluate(instance: ProblemInstance, route: List[int], sorties: Sequence[Sortie],
             policies: Sequence[Tuple] = ALL_POLICIES, detailed: bool = False,
             check_structure: bool = True, partial: bool = False,
             max_repairs: Optional[int] = None) -> ScheduleResult:
    """Schedule a plan. partial=True allows unserved customers (used while repairing).

    max_repairs limits the endurance repairs tried per policy (None = 4 per sortie).
    """
    if not instance.require_truck_at_depot:
        raise NotImplementedError("Only requireTruckAtDepot = True (the paper's setting) is implemented")
    if check_structure:
        problems = validate_structure(instance, route, list(sorties), partial=partial)
        if problems:
            return ScheduleResult(False, INF, violations=problems)

    n_pos = len(route)
    last = n_pos - 1
    pos = {node: idx for idx, node in enumerate(route[:-1])}
    launches_at: List[List[int]] = [[] for _ in range(n_pos)]
    recoveries_at: List[List[int]] = [[] for _ in range(n_pos)]
    s_pos = []
    for idx, s in enumerate(sorties):
        a = pos[s.launch_node]
        b = last if s.recovery_node == 0 else pos[s.recovery_node]
        s_pos.append((a, b))
        launches_at[a].append(idx)
        recoveries_at[b].append(idx)
    consts = []
    for s in sorties:
        u = instance.uavs[s.uav_id]
        consts.append((u.launch_time, u.recovery_time,
                       instance.sortie_flight_time(s.uav_id, s.launch_node, s.customer_id, s.recovery_node),
                       instance.endurance(s.uav_id, s.launch_node, s.customer_id, s.recovery_node)))
    plan = (route, sorties, s_pos, launches_at, recoveries_at, consts)
    if max_repairs is None:
        max_repairs = 4 * len(sorties)

    best: Optional[ScheduleResult] = None
    first_failure: Optional[ScheduleResult] = None
    for policy in policies:
        late, urgent, delay = set(), set(), {}
        for attempt in range(max_repairs + 1):
            res = _forward_pass(instance, plan, policy, detailed, late, urgent, delay)
            si = res.failed_sortie
            if res.feasible or si is None or attempt == max_repairs:
                break
            # Endurance failure. Like the MILP, first launch that UAV last at its stop,
            # then recover it first, then hold its launch back (the truck waits) by the excess.
            if si not in late:
                late.add(si)
            elif si not in urgent:
                urgent.add(si)
            elif delay.get(si, 0.0) < 3600.0:
                delay[si] = delay.get(si, 0.0) + res.excess + 1e-6
            else:
                break
        res.flags = (frozenset(late), frozenset(urgent), dict(delay))
        if res.feasible:
            if best is None or res.makespan < best.makespan - EPS:
                best = res
        elif first_failure is None:
            first_failure = res
    if best is None:
        return first_failure
    if detailed and not best.operations:
        late, urgent, delay = best.flags
        best = _forward_pass(instance, plan, best.policy, True, late, urgent, delay)
    return best


def _forward_pass(instance, plan, policy, detailed, late=frozenset(), urgent=frozenset(), delay=None):
    route, sorties, s_pos, launches_at, recoveries_at, consts = plan
    rank = {c: i for i, c in enumerate(policy[:3])}
    r_rank, s_rank, l_rank = rank["R"], rank["S"], rank["L"]
    launch_order = policy[3] if len(policy) > 3 else "due"
    chain = bool(policy[4]) if len(policy) > 4 else False
    delay = delay or {}
    tau = instance.truck_time
    nodes = instance.nodes
    driver = instance.require_driver
    last = len(route) - 1

    n_s = len(sorties)
    launch_done = [0.0] * n_s
    ready = [0.0] * n_s
    rec_start = [0.0] * n_s
    rec_done = [0.0] * n_s
    launch_start = [0.0] * n_s
    if launch_order == "due":
        lkey = [(s_pos[i][1], -consts[i][2], i) for i in range(n_s)]
    elif launch_order == "long":
        lkey = [(-consts[i][2], s_pos[i][1], i) for i in range(n_s)]
    else:
        lkey = [(consts[i][2], s_pos[i][1], i) for i in range(n_s)]

    arrivals = [0.0] * len(route)
    departures = [0.0] * len(route)
    ops_log = [] if detailed else None

    truck_wait = 0.0
    hover_total = 0.0
    t = 0.0
    for p in range(len(route)):
        node = route[p]
        arrival = t
        rec_here = recoveries_at[p]
        lau_here = launches_at[p]
        service = nodes[node].truck_service if 0 < p < last else 0.0

        if not rec_here and not lau_here:
            # Fast path: only the delivery happens here.
            departure = arrival + service
            if detailed and service > 0:
                ops_log.append((p, "S", node, arrival, departure))
        else:
            pending = []
            for si in rec_here:
                pending.append((-1 if si in urgent else r_rank, 1, si, consts[si][1]))
            if service > 0 and driver:
                pending.append((s_rank, 0, -1, service))
            recovered_uav_here = {}
            for si in rec_here:
                recovered_uav_here[sorties[si].uav_id] = si
            n_late = 0
            for si in lau_here:
                if si in late:
                    rk = 9
                    n_late += 1
                elif chain and sorties[si].uav_id in recovered_uav_here:
                    rk = -2
                else:
                    rk = l_rank
                pending.append((rk, 2, si, consts[si][0]))
            n_normal = len(pending) - n_late

            busy = 0.0
            station_free = arrival
            while pending:
                best_idx = -1
                best_key = None
                next_release = INF
                for idx in range(len(pending)):
                    rk, kind, si, dur = pending[idx]
                    if kind == 1:
                        rel = ready[si] if ready[si] > arrival else arrival
                        key2 = (si,)
                    elif kind == 2:
                        if rk == 9 and n_normal:
                            continue  # a late launch waits until every other operation here is done
                        dep = recovered_uav_here.get(sorties[si].uav_id)
                        if dep is not None:
                            if rec_done[dep] == 0.0 and dep in rec_here and _pending_has(pending, dep):
                                continue  # must wait for this UAV's own recovery
                            rel = rec_done[dep] if rec_done[dep] > arrival else arrival
                        else:
                            rel = arrival
                        if si in delay and arrival + delay[si] > rel:
                            rel = arrival + delay[si]
                        key2 = lkey[si]
                    else:
                        rel = arrival
                        key2 = (-1,)
                    if rel <= station_free + EPS:
                        key = (rk, rel, key2)
                        if best_key is None or key < best_key:
                            best_key, best_idx = key, idx
                    elif rel < next_release:
                        next_release = rel
                if best_idx < 0:
                    station_free = next_release  # the driver idles until the next operation is ready
                    continue
                rk, kind, si, dur = pending.pop(best_idx)
                if rk != 9:
                    n_normal -= 1
                start = station_free
                end = start + dur
                station_free = end
                busy += dur
                if kind == 1:
                    rec_start[si] = start
                    rec_done[si] = end
                elif kind == 2:
                    launch_start[si] = start
                    launch_done[si] = end
                    ready[si] = end + consts[si][2]
                if detailed:
                    ops_log.append((p, "R" if kind == 1 else "L" if kind == 2 else "S",
                                    sorties[si].uav_id if si >= 0 else node, start, end))

            departure = station_free
            if service > 0 and not driver:
                departure = max(departure, arrival + service)
                busy = max(busy, service)
                if detailed:
                    ops_log.append((p, "S", node, arrival, arrival + service))
            truck_wait += max(0.0, departure - arrival - busy)

            # Endurance check for every UAV recovered here.
            for si in rec_here:
                airborne = rec_start[si] - launch_done[si]
                limit = consts[si][3]
                if airborne > limit + EPS:
                    bad = ScheduleResult(False, INF, policy=policy, violations=[
                        "sortie %s exceeds endurance: %.1f s in the air, limit %.1f s"
                        % (sorties[si], airborne, limit)])
                    bad.failed_sortie = si
                    bad.excess = airborne - limit
                    return bad
                hover_total += rec_start[si] - ready[si]

        arrivals[p] = arrival
        departures[p] = departure
        t = departure + tau[node][route[p + 1]] if p < last else departure

    res = ScheduleResult(True, t, policy=policy, truck_waiting=truck_wait, uav_waiting=hover_total)
    res.truck_arrival = arrivals
    res.truck_departure = departures
    if detailed:
        res.operations = ops_log
        for si, s in enumerate(sorties):
            res.sorties.append(SortieTiming(
                s, launch_start[si], launch_done[si], ready[si], rec_start[si], rec_done[si],
                rec_start[si] - ready[si], rec_start[si] - launch_done[si], consts[si][3]))
    return res


def _pending_has(pending, si) -> bool:
    for op in pending:
        if op[1] == 1 and op[2] == si:
            return True
    return False
