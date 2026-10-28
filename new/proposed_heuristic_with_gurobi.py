#!/usr/bin/env python3
"""
----------------

GUROBI-assisted version of the proposed mFSTSP heuristic.

This file holds the whole heuristic framework (route search, candidate
sortie templates, event-based schedule simulation, UAV-count expansion)
and uses Gurobi in two places:

1) Truck route seed (n <= 25 customers):
    - Exact asymmetric TSP on the truck travel times, solved by Gurobi with
      lazy subtour-elimination constraints.
    - The optimal truck-only tour (raw and after the UAV-aware local search)
      competes with the no-Gurobi route search result.
    - The route search ranks orders with an approximate fitness, so the simple
      construction seeds (Clarke-Wright, insertion, nearest neighbor) also compete.
      Every candidate order is scheduled exactly and the best one is kept.

2) UAV sortie selection MIP (all sizes):
    - For a fixed truck order, choose the set of sorties (launch, customer, recovery)
      that maximizes total estimated makespan improvement.
    - Constraints:
        * every customer is served by at most one sortie,
        * a node used as launch/recovery cannot be served by a UAV,
        * at most |UAVs| sorties can be in the air over any route segment.
    - Gurobi returns a pool of good selections. Every pool solution is evaluated
      by the exact event simulation, repaired (drop sorties that hurt, then greedily
      add sorties that help) and compared with the no-Gurobi greedy scheduler.
      The best exact makespan is kept, so the MIP can only improve the schedule.

License note:
    The free pip license of gurobipy is size-limited (2000 variables and
    2000 constraints). Every model here is capped to stay below that limit.
    If Gurobi fails for any reason, the step falls back to the no-Gurobi logic
    and the failure is counted in solution["metadata"]["gurobi"].

"""

from __future__ import annotations

import csv
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional, Set

import gurobipy as gp
from gurobipy import GRB


# ============================================================
# Reproducibility
# ============================================================

RANDOM_SEED = 42
random.seed(RANDOM_SEED)


# ============================================================
# Tunable optimization settings
# ============================================================

# Candidate sortie generation: route windows are intentionally limited
# for runtime, then enlarged slightly in final evaluation.
CANDIDATE_SETTINGS = {
    8:   {"fitness_window": None, "final_window": None, "top_per_customer": 10},
    10:  {"fitness_window": None, "final_window": None, "top_per_customer": 12},
    25:  {"fitness_window": 11,   "final_window": 15,   "top_per_customer": 8},
    50:  {"fitness_window": 8,    "final_window": 13,   "top_per_customer": 6},
    100: {"fitness_window": 6,    "final_window": 11,   "top_per_customer": 5},
}

# OFV is still the main target.
# These settings only add a *small* secondary preference for serving
# more customers by UAV, which directly targets avg_numUAVcust.
UAV_COUNT_SETTINGS = {
    8: {
        "candidate_min_estimated_improvement": 0.0,
        "route_bonus_seconds_per_uav": 0.30,
        "final_count_makespan_tolerance_ratio": 0.0005,
        "final_count_makespan_tolerance_seconds": 0.50,
    },
    10: {
        "candidate_min_estimated_improvement": -6.0,
        "route_bonus_seconds_per_uav": 1.50,
        "final_count_makespan_tolerance_ratio": 0.0025,
        "final_count_makespan_tolerance_seconds": 3.00,
    },
    25: {
        "candidate_min_estimated_improvement": -8.0,
        "route_bonus_seconds_per_uav": 1.20,
        "final_count_makespan_tolerance_ratio": 0.0020,
        "final_count_makespan_tolerance_seconds": 5.00,
    },
    50: {
        "candidate_min_estimated_improvement": -10.0,
        "route_bonus_seconds_per_uav": 0.90,
        "final_count_makespan_tolerance_ratio": 0.0015,
        "final_count_makespan_tolerance_seconds": 7.00,
    },
    100: {
        "candidate_min_estimated_improvement": -12.0,
        "route_bonus_seconds_per_uav": 0.70,
        "final_count_makespan_tolerance_ratio": 0.0010,
        "final_count_makespan_tolerance_seconds": 10.00,
    },
}

GA_SETTINGS = {
    50: {
        "population_size": 34,
        "generations": 60,
        "elite_size": 5,
        "tournament_size": 4,
        "mutation_rate": 0.32,
        "crossover_rate": 0.92,
        "elite_polish_rounds": 2,
        "elite_polish_trials": 22,
    },
    100: {
        "population_size": 42,
        "generations": 78,
        "elite_size": 6,
        "tournament_size": 5,
        "mutation_rate": 0.36,
        "crossover_rate": 0.92,
        "elite_polish_rounds": 2,
        "elite_polish_trials": 18,
    },
}

LOCAL_SEARCH_SETTINGS = {
    8:   {"starts": 16, "rounds": 5, "trials": 80},
    10:  {"starts": 20, "rounds": 6, "trials": 90},
    25:  {"starts": 22, "rounds": 6, "trials": 85},
}

FINAL_SCHEDULE_SETTINGS = {
    8:   {"candidate_limit": 220, "max_insertions": 8,   "improvement_trials": 50, "count_expansion_rounds": 2},
    10:  {"candidate_limit": 360, "max_insertions": 10,  "improvement_trials": 75, "count_expansion_rounds": 3},
    25:  {"candidate_limit": 460, "max_insertions": 20,  "improvement_trials": 70, "count_expansion_rounds": 3},
    50:  {"candidate_limit": 620, "max_insertions": 34,  "improvement_trials": 80, "count_expansion_rounds": 3},
    100: {"candidate_limit": 760, "max_insertions": 50,  "improvement_trials": 90, "count_expansion_rounds": 3},
}


# ============================================================
# Data containers
# ============================================================

@dataclass(frozen=True)
class CandidateSpec:
    """
    Candidate UAV delivery template, independent of exact calendar timing.
    """
    launch_pos: int
    customer_pos: int
    recovery_pos: int
    launch_node: int
    customer: int
    recovery_node: int
    eligible_uav_durations: Tuple[Tuple[int, float], ...]  # (uav_id, duration)
    estimated_improvement: float
    original_segment_time: float
    reduced_truck_segment_time: float

    def best_duration(self) -> float:
        return min(duration for _, duration in self.eligible_uav_durations)

    def interval(self) -> Tuple[int, int]:
        return self.launch_pos, self.recovery_pos


@dataclass
class ScheduledSortie:
    """
    A concrete sortie assigned to a physical UAV in the final simulation.
    """
    uav_id: int
    launch_node: int
    customer: int
    recovery_node: int
    launch_time: float
    arrival_to_recovery_time: float
    sortie_duration: float
    recovery_truck_arrival_time: float = 0.0
    truck_waiting_time: float = 0.0
    uav_waiting_time: float = 0.0
    estimated_improvement: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "uav": self.uav_id,
            "launch": self.launch_node,
            "customer": self.customer,
            "recovery": self.recovery_node,
            "launch_time": round(self.launch_time, 6),
            "arrival_to_recovery_time": round(self.arrival_to_recovery_time, 6),
            "sortie_duration": round(self.sortie_duration, 6),
            "recovery_truck_arrival_time": round(self.recovery_truck_arrival_time, 6),
            "truck_waiting_time": round(self.truck_waiting_time, 6),
            "uav_waiting_time": round(self.uav_waiting_time, 6),
            "estimated_improvement": round(self.estimated_improvement, 6),
        }


@dataclass
class SimulationResult:
    valid: bool
    makespan: float
    truck_route: List[int]
    scheduled_sorties: List[ScheduledSortie]
    truck_waiting_time: float
    uav_waiting_time: float
    max_parallel_uavs_used: int
    validation: Dict[str, Any]
    activity_log: List[Dict[str, Any]] = field(default_factory=list)


# ============================================================
# Basic access helpers
# ============================================================

def _depot(problem: Dict[str, Any]) -> int:
    return int(problem["depot"])


def _customers(problem: Dict[str, Any]) -> List[int]:
    return list(problem["customers"])


def _uavs(problem: Dict[str, Any]) -> List[int]:
    return list(problem.get("uavs", []))


def _truck_time(problem: Dict[str, Any], i: int, j: int) -> float:
    return float(problem["truck_time"][i][j])


def _uav_time(problem: Dict[str, Any], uav_id: int, i: int, j: int) -> float:
    return float(problem["uav_time"][uav_id][i][j])


def _truck_service(problem: Dict[str, Any], customer: int) -> float:
    return float(problem["truck_service_time"].get(customer, 0.0))


def _uav_service(problem: Dict[str, Any], uav_id: int, customer: int) -> float:
    return float(problem["uav_service_time"].get(uav_id, {}).get(customer, 0.0))


def _launch_time(problem: Dict[str, Any], uav_id: int) -> float:
    return float(problem["launch_time"].get(uav_id, {}).get("default", 0.0))


def _recovery_time(problem: Dict[str, Any], uav_id: int) -> float:
    return float(problem["recovery_time"].get(uav_id, {}).get("default", 0.0))


def _endurance(problem: Dict[str, Any], uav_id: int) -> float:
    return float(problem["uav_endurance"].get(uav_id, float("inf")))


def _group_key(n_customers: int) -> int:
    if n_customers <= 8:
        return 8
    if n_customers <= 10:
        return 10
    if n_customers <= 25:
        return 25
    if n_customers <= 50:
        return 50
    return 100


def _uav_count_settings_for_order(order: List[int]) -> Dict[str, float]:
    return UAV_COUNT_SETTINGS[_group_key(len(order))]


def _candidate_min_estimated_improvement(order: List[int]) -> float:
    return float(_uav_count_settings_for_order(order)["candidate_min_estimated_improvement"])


# ============================================================
# Route helpers and truck-only objective
# ============================================================

def route_from_order(problem: Dict[str, Any], order: List[int]) -> List[int]:
    depot = _depot(problem)
    return [depot] + order[:] + [depot]


def order_from_route(problem: Dict[str, Any], route: List[int]) -> List[int]:
    depot = _depot(problem)
    return [node for node in route if node != depot]


def truck_only_makespan(problem: Dict[str, Any], order: List[int]) -> float:
    route = route_from_order(problem, order)
    total = 0.0

    for idx in range(len(route) - 1):
        total += _truck_time(problem, route[idx], route[idx + 1])

    for customer in order:
        total += _truck_service(problem, customer)

    return total


def route_prefix_data(problem: Dict[str, Any], route: List[int]) -> Tuple[List[float], List[float]]:
    """
    prefix_travel[p] = travel time from route[0] to route[p].
    prefix_service[p] = service times for route[0]..route[p-1].
    """
    n = len(route)
    prefix_travel = [0.0] * n
    prefix_service = [0.0] * (n + 1)

    for p in range(1, n):
        prefix_travel[p] = prefix_travel[p - 1] + _truck_time(problem, route[p - 1], route[p])

    depot = _depot(problem)
    for p in range(n):
        prefix_service[p + 1] = prefix_service[p]
        node = route[p]
        if node != depot:
            prefix_service[p + 1] += _truck_service(problem, node)

    return prefix_travel, prefix_service


def original_segment_time(
    route: List[int],
    prefix_travel: List[float],
    prefix_service: List[float],
    launch_pos: int,
    recovery_pos: int,
) -> float:
    """
    Time from launch position to recovery position on original truck route.

    Includes:
    - truck travel between launch and recovery
    - truck service at interior customer positions
    """
    travel = prefix_travel[recovery_pos] - prefix_travel[launch_pos]
    service = prefix_service[recovery_pos] - prefix_service[launch_pos + 1]
    return travel + service


def reduced_segment_time_skip_customer(
    problem: Dict[str, Any],
    route: List[int],
    launch_pos: int,
    customer_pos: int,
    recovery_pos: int,
) -> float:
    """
    Truck segment time after skipping one UAV-served customer.
    """
    segment = route[launch_pos:recovery_pos + 1]
    skipped_customer = route[customer_pos]
    reduced = [node for node in segment if node != skipped_customer]

    total = 0.0
    for idx in range(len(reduced) - 1):
        total += _truck_time(problem, reduced[idx], reduced[idx + 1])

    depot = _depot(problem)
    for node in reduced[1:-1]:
        if node != depot:
            total += _truck_service(problem, node)

    return total


# ============================================================
# Candidate UAV sortie generation
# ============================================================

def generate_candidate_specs(
    problem: Dict[str, Any],
    order: List[int],
    max_window: Optional[int],
    top_per_customer: int,
    minimum_improvement: float = 1e-9,
) -> List[CandidateSpec]:
    """
    Generate route-position UAV candidate templates.

    One customer can produce many possible candidates:
      launch at route[a], serve customer at route[p], recover at route[b]
      with a < p < b.

    Runtime control:
      - max_window limits b - a
      - top_per_customer keeps only the strongest estimated options for each customer
    """
    route = route_from_order(problem, order)
    depot = _depot(problem)
    droneable = set(problem.get("droneable_customers", []))
    uavs = _uavs(problem)

    if not droneable or not uavs or len(route) < 4:
        return []

    prefix_travel, prefix_service = route_prefix_data(problem, route)
    last_pos = len(route) - 1
    candidates_by_customer: Dict[int, List[CandidateSpec]] = {}

    for customer_pos in range(1, last_pos):
        customer = route[customer_pos]
        if customer not in droneable:
            continue

        local_candidates: List[CandidateSpec] = []

        for launch_pos in range(0, customer_pos):
            launch_node = route[launch_pos]

            min_recovery = customer_pos + 1
            max_recovery = last_pos

            if max_window is not None:
                max_recovery = min(max_recovery, launch_pos + max_window)

            if min_recovery > max_recovery:
                continue

            for recovery_pos in range(min_recovery, max_recovery + 1):
                recovery_node = route[recovery_pos]

                original_time = original_segment_time(
                    route,
                    prefix_travel,
                    prefix_service,
                    launch_pos,
                    recovery_pos,
                )
                reduced_time = reduced_segment_time_skip_customer(
                    problem,
                    route,
                    launch_pos,
                    customer_pos,
                    recovery_pos,
                )

                eligible: List[Tuple[int, float]] = []

                for uav_id in uavs:
                    duration = (
                        _launch_time(problem, uav_id)
                        + _uav_time(problem, uav_id, launch_node, customer)
                        + _uav_service(problem, uav_id, customer)
                        + _uav_time(problem, uav_id, customer, recovery_node)
                        + _recovery_time(problem, uav_id)
                    )

                    if duration <= _endurance(problem, uav_id) + 1e-9:
                        eligible.append((uav_id, duration))

                if not eligible:
                    continue

                best_duration = min(duration for _, duration in eligible)
                synchronized = max(reduced_time, best_duration)
                estimated_improvement = original_time - synchronized

                if estimated_improvement <= minimum_improvement:
                    continue

                spec = CandidateSpec(
                    launch_pos=launch_pos,
                    customer_pos=customer_pos,
                    recovery_pos=recovery_pos,
                    launch_node=launch_node,
                    customer=customer,
                    recovery_node=recovery_node,
                    eligible_uav_durations=tuple(sorted(eligible, key=lambda x: x[1])),
                    estimated_improvement=estimated_improvement,
                    original_segment_time=original_time,
                    reduced_truck_segment_time=reduced_time,
                )
                local_candidates.append(spec)

        local_candidates.sort(key=lambda c: c.estimated_improvement, reverse=True)
        candidates_by_customer[customer] = local_candidates[:top_per_customer]

    result: List[CandidateSpec] = []
    for customer_specs in candidates_by_customer.values():
        result.extend(customer_specs)

    result.sort(key=lambda c: c.estimated_improvement, reverse=True)
    return result


# ============================================================
# Fast approximate parallel-UAV fitness for route search
# ============================================================

def approximate_parallel_sortie_selection(
    problem: Dict[str, Any],
    order: List[int],
    max_window: Optional[int],
    top_per_customer: int,
) -> Tuple[float, List[CandidateSpec], float]:
    """
    Fast approximate parallel-UAV scheduling for route search.

    It is not the final exact calendar schedule.
    It is used only to guide local search / GA.

    Rules:
    - A customer can appear at most once.
    - Launch/recovery customer nodes cannot already be selected as UAV-served customers.
    - Route-position concurrency cannot exceed number of UAVs.
      This gives a useful approximation of "up to 3 drones can be active."
    """
    baseline = truck_only_makespan(problem, order)
    candidates = generate_candidate_specs(
        problem,
        order,
        max_window=max_window,
        top_per_customer=top_per_customer,
        minimum_improvement=_candidate_min_estimated_improvement(order),
    )

    if not candidates:
        return baseline, [], 0.0

    n_route_positions = len(order) + 2
    capacity = max(1, len(_uavs(problem)))
    interval_load = [0] * max(1, n_route_positions)

    selected: List[CandidateSpec] = []
    selected_drone_customers: Set[int] = set()
    protected_truck_nodes: Set[int] = set()

    total_benefit = 0.0

    for cand in candidates:
        if cand.customer in selected_drone_customers:
            continue

        # Do not use a node as launch/recovery if we already removed it to a UAV.
        if cand.launch_node in selected_drone_customers:
            continue
        if cand.recovery_node in selected_drone_customers:
            continue

        # If this customer has become a protected launch/recovery node for another accepted sortie,
        # do not remove it from the truck route.
        if cand.customer in protected_truck_nodes:
            continue

        # Approximate concurrency check by route intervals.
        start, end = cand.interval()
        if any(interval_load[pos] >= capacity for pos in range(start, end)):
            continue

        selected.append(cand)
        selected_drone_customers.add(cand.customer)
        protected_truck_nodes.add(cand.launch_node)
        protected_truck_nodes.add(cand.recovery_node)

        for pos in range(start, end):
            interval_load[pos] += 1

        total_benefit += cand.estimated_improvement

    settings = _uav_count_settings_for_order(order)
    uav_count_bonus = float(settings["route_bonus_seconds_per_uav"]) * len(selected)

    # Primary signal is still makespan.  The small bonus only breaks near-ties
    # toward routes that create more UAV deliveries, helping avg_numUAVcust.
    approx_makespan = baseline - total_benefit - uav_count_bonus
    return approx_makespan, selected, total_benefit


def approximate_route_fitness(
    problem: Dict[str, Any],
    order: List[int],
    max_window: Optional[int],
    top_per_customer: int,
) -> float:
    score, _, _ = approximate_parallel_sortie_selection(
        problem,
        order,
        max_window=max_window,
        top_per_customer=top_per_customer,
    )
    return score


# ============================================================
# Exact-ish final event simulation for selected sorties
# ============================================================

def final_truck_route_from_selection(
    problem: Dict[str, Any],
    order: List[int],
    selected_specs: List[CandidateSpec],
) -> List[int]:
    depot = _depot(problem)
    drone_customers = {spec.customer for spec in selected_specs}
    return [depot] + [customer for customer in order if customer not in drone_customers] + [depot]


def max_parallel_sorties(scheduled: List[ScheduledSortie]) -> int:
    events: List[Tuple[float, int]] = []
    for s in scheduled:
        events.append((s.launch_time, +1))
        events.append((s.arrival_to_recovery_time, -1))

    # Recoveries at same exact moment free capacity before launches at that moment.
    events.sort(key=lambda x: (x[0], x[1]))
    current = 0
    best = 0
    for _, delta in events:
        current += delta
        best = max(best, current)
    return best


def simulate_schedule(
    problem: Dict[str, Any],
    order: List[int],
    selected_specs: List[CandidateSpec],
) -> SimulationResult:
    """
    Simulate truck/UAV calendar timing.

    Key assumptions, consistent with the no-Gurobi heuristic framework:
    - UAV launch time and recovery time are embedded in sortie duration.
    - Truck departure timing is primarily driven by travel, truck service,
      and waiting at recovery nodes when UAVs arrive later.
    - A UAV cannot be assigned to another sortie before its prior sortie returns.
    """
    depot = _depot(problem)
    all_customers = set(_customers(problem))
    uavs = _uavs(problem)
    droneable = set(problem.get("droneable_customers", []))

    selected_customers = [spec.customer for spec in selected_specs]
    selected_customer_set = set(selected_customers)

    # Basic customer uniqueness.
    if len(selected_customers) != len(selected_customer_set):
        return invalid_simulation(problem, order, selected_specs, "duplicate_uav_customer")

    # Launch/recovery nodes must stay on truck route.
    for spec in selected_specs:
        if spec.launch_node in selected_customer_set:
            return invalid_simulation(problem, order, selected_specs, "launch_node_removed_from_truck")
        if spec.recovery_node in selected_customer_set:
            return invalid_simulation(problem, order, selected_specs, "recovery_node_removed_from_truck")
        if spec.customer not in droneable:
            return invalid_simulation(problem, order, selected_specs, "customer_not_droneable")

    truck_route = final_truck_route_from_selection(problem, order, selected_specs)
    route_position = {node: idx for idx, node in enumerate(truck_route)}

    # Check route ordering of launch before recovery.
    for spec in selected_specs:
        if spec.launch_node not in route_position or spec.recovery_node not in route_position:
            return invalid_simulation(problem, order, selected_specs, "launch_or_recovery_not_on_truck_route")
        if route_position[spec.launch_node] >= route_position[spec.recovery_node]:
            return invalid_simulation(problem, order, selected_specs, "recovery_before_launch")

    launches_by_node: Dict[int, List[CandidateSpec]] = {}
    recoveries_by_node: Dict[int, List[ScheduledSortie]] = {}

    for spec in selected_specs:
        launches_by_node.setdefault(spec.launch_node, []).append(spec)

    # UAV availability calendar.
    uav_available_time: Dict[int, float] = {uav_id: 0.0 for uav_id in uavs}

    time_now = 0.0
    scheduled: List[ScheduledSortie] = []
    truck_waiting_total = 0.0
    uav_waiting_total = 0.0
    activity_log: List[Dict[str, Any]] = []

    # Truck route traversal.
    for idx, node in enumerate(truck_route):
        # At node: process recoveries that are due at this node.
        recovery_list = recoveries_by_node.get(node, [])
        if recovery_list:
            latest_drone_arrival = max(s.arrival_to_recovery_time for s in recovery_list)
            truck_arrival_before_wait = time_now
            if latest_drone_arrival > time_now:
                truck_wait = latest_drone_arrival - time_now
                truck_waiting_total += truck_wait
                time_now = latest_drone_arrival

            for sortie in recovery_list:
                sortie.recovery_truck_arrival_time = truck_arrival_before_wait
                sortie.truck_waiting_time = max(0.0, sortie.arrival_to_recovery_time - truck_arrival_before_wait)
                sortie.uav_waiting_time = max(0.0, truck_arrival_before_wait - sortie.arrival_to_recovery_time)
                uav_waiting_total += sortie.uav_waiting_time

            activity_log.append({
                "type": "recovery_node",
                "node": node,
                "time_after_recovery_sync": round(time_now, 6),
                "num_recoveries": len(recovery_list),
            })

        # Service at truck-served customer node.
        if node != depot:
            service = _truck_service(problem, node)
            if service > 0:
                time_now += service
                activity_log.append({
                    "type": "truck_service",
                    "node": node,
                    "duration": round(service, 6),
                    "time_after_service": round(time_now, 6),
                })

        # Launch selected UAV sorties from this node after local truck service.
        specs_here = launches_by_node.get(node, [])
        if specs_here:
            # More promising sorties first.
            specs_here = sorted(specs_here, key=lambda s: s.estimated_improvement, reverse=True)

            for spec in specs_here:
                assigned = None

                # Pick the fastest feasible UAV that is available now.
                for uav_id, duration in spec.eligible_uav_durations:
                    if uav_id not in uav_available_time:
                        continue
                    if uav_available_time[uav_id] <= time_now + 1e-9:
                        assigned = (uav_id, duration)
                        break

                if assigned is None:
                    return invalid_simulation(problem, order, selected_specs, "no_uav_available_at_launch")

                uav_id, duration = assigned
                return_time = time_now + duration
                uav_available_time[uav_id] = return_time

                sortie = ScheduledSortie(
                    uav_id=uav_id,
                    launch_node=spec.launch_node,
                    customer=spec.customer,
                    recovery_node=spec.recovery_node,
                    launch_time=time_now,
                    arrival_to_recovery_time=return_time,
                    sortie_duration=duration,
                    estimated_improvement=spec.estimated_improvement,
                )
                scheduled.append(sortie)
                recoveries_by_node.setdefault(spec.recovery_node, []).append(sortie)

                activity_log.append({
                    "type": "uav_launch",
                    "uav": uav_id,
                    "launch_node": spec.launch_node,
                    "customer": spec.customer,
                    "recovery_node": spec.recovery_node,
                    "launch_time": round(time_now, 6),
                    "expected_recovery_arrival": round(return_time, 6),
                })

        # Travel to next truck route node.
        if idx < len(truck_route) - 1:
            nxt = truck_route[idx + 1]
            travel = _truck_time(problem, node, nxt)
            time_now += travel
            activity_log.append({
                "type": "truck_travel",
                "from": node,
                "to": nxt,
                "duration": round(travel, 6),
                "arrival_time": round(time_now, 6),
            })

    # Any recovery that should have happened at depot / last node was processed in the loop.
    makespan = time_now

    truck_customers = [node for node in truck_route if node != depot]
    uav_customers = [s.customer for s in scheduled]

    served_once = (
        set(truck_customers).union(uav_customers) == all_customers
        and len(truck_customers) == len(set(truck_customers))
        and len(uav_customers) == len(set(uav_customers))
        and set(truck_customers).isdisjoint(set(uav_customers))
    )

    max_parallel = max_parallel_sorties(scheduled)
    fleet_capacity_ok = max_parallel <= len(uavs)

    endurance_ok = True
    for sortie in scheduled:
        if sortie.sortie_duration > _endurance(problem, sortie.uav_id) + 1e-9:
            endurance_ok = False
            break

    validation = {
        "valid": served_once and fleet_capacity_ok and endurance_ok,
        "served_every_customer_exactly_once": served_once,
        "max_parallel_uavs_used": max_parallel,
        "fleet_capacity_ok": fleet_capacity_ok,
        "endurance_ok": endurance_ok,
        "num_physical_uavs": len(uavs),
        "num_selected_uav_customers": len(uav_customers),
        "num_truck_customers": len(truck_customers),
    }

    return SimulationResult(
        valid=validation["valid"],
        makespan=makespan,
        truck_route=truck_route,
        scheduled_sorties=scheduled,
        truck_waiting_time=truck_waiting_total,
        uav_waiting_time=uav_waiting_total,
        max_parallel_uavs_used=max_parallel,
        validation=validation,
        activity_log=activity_log,
    )


def invalid_simulation(
    problem: Dict[str, Any],
    order: List[int],
    selected_specs: List[CandidateSpec],
    reason: str,
) -> SimulationResult:
    return SimulationResult(
        valid=False,
        makespan=float("inf"),
        truck_route=route_from_order(problem, order),
        scheduled_sorties=[],
        truck_waiting_time=0.0,
        uav_waiting_time=0.0,
        max_parallel_uavs_used=0,
        validation={"valid": False, "reason": reason},
        activity_log=[],
    )


# ============================================================
# Final sortie selection using exact simulation
# ============================================================

def _num_uav_customers_in_result(result: SimulationResult) -> int:
    return len(result.scheduled_sorties)


def _uav_count_allowed_makespan(reference_result: SimulationResult, group: int) -> float:
    """
    Upper makespan bound used only for the avg_numUAVcust expansion phase.
    It is relative to the best OFV schedule found *before* expansion, so the
    tolerance does not accumulate across accepted additions.
    """
    settings = UAV_COUNT_SETTINGS[group]
    ratio_slack = reference_result.makespan * float(settings["final_count_makespan_tolerance_ratio"])
    absolute_slack = float(settings["final_count_makespan_tolerance_seconds"])
    return reference_result.makespan + max(ratio_slack, absolute_slack)


def _strict_ofv_better(candidate: SimulationResult, incumbent: SimulationResult) -> bool:
    return candidate.valid and (
        (not incumbent.valid) or candidate.makespan + 1e-9 < incumbent.makespan
    )


def _uav_count_better_within_tolerance(
    candidate: SimulationResult,
    incumbent: SimulationResult,
    reference_ofv_result: SimulationResult,
    group: int,
) -> bool:
    """
    Secondary objective:
    - Do not accept an invalid solution.
    - Do not exceed a tiny allowed makespan band around the best OFV solution.
    - Prefer more UAV-served customers.
    - For the same UAV count, prefer lower makespan.
    """
    if not candidate.valid:
        return False

    allowed_makespan = _uav_count_allowed_makespan(reference_ofv_result, group)
    if candidate.makespan > allowed_makespan + 1e-9:
        return False

    cand_uav = _num_uav_customers_in_result(candidate)
    inc_uav = _num_uav_customers_in_result(incumbent)

    if cand_uav > inc_uav:
        return True

    if cand_uav == inc_uav and candidate.makespan + 1e-9 < incumbent.makespan:
        return True

    return False


def exact_greedy_parallel_scheduler(
    problem: Dict[str, Any],
    order: List[int],
    max_window: Optional[int],
    top_per_customer: int,
    candidate_limit: int,
    max_insertions: int,
) -> Tuple[SimulationResult, List[CandidateSpec]]:
    """
    Build a valid multi-UAV schedule iteratively.

    Algorithm:
    - Start with truck-only route.
    - Generate promising UAV candidate specs.
    - At each iteration, test adding one candidate to the current selected set.
    - Accept the candidate producing the greatest exact makespan improvement.
    - Stop when no exact improvement remains.
    """
    all_candidates = generate_candidate_specs(
        problem,
        order,
        max_window=max_window,
        top_per_customer=top_per_customer,
    )[:candidate_limit]

    selected: List[CandidateSpec] = []
    current = simulate_schedule(problem, order, selected)

    if not current.valid:
        return current, selected

    selected_customers: Set[int] = set()
    protected_nodes: Set[int] = set()

    for _ in range(max_insertions):
        best_candidate = None
        best_result = current

        for cand in all_candidates:
            if cand.customer in selected_customers:
                continue
            if cand.customer in protected_nodes:
                continue
            if cand.launch_node in selected_customers:
                continue
            if cand.recovery_node in selected_customers:
                continue

            trial_specs = selected + [cand]
            trial_result = simulate_schedule(problem, order, trial_specs)

            if not trial_result.valid:
                continue

            if _strict_ofv_better(trial_result, best_result):
                best_result = trial_result
                best_candidate = cand

        if best_candidate is None:
            break

        selected.append(best_candidate)
        selected_customers.add(best_candidate.customer)
        protected_nodes.add(best_candidate.launch_node)
        protected_nodes.add(best_candidate.recovery_node)
        current = best_result

    return current, selected


def final_schedule_improvement_trials(
    problem: Dict[str, Any],
    order: List[int],
    current_result: SimulationResult,
    current_specs: List[CandidateSpec],
    max_window: Optional[int],
    top_per_customer: int,
    candidate_limit: int,
    trials: int,
) -> Tuple[SimulationResult, List[CandidateSpec]]:
    """
    Small post-processing improvement:
    - Try adding one new candidate.
    - Try replacing one selected candidate by another.
    This helps remove greedy selection mistakes.
    """
    all_candidates = generate_candidate_specs(
        problem,
        order,
        max_window=max_window,
        top_per_customer=top_per_customer,
    )[:candidate_limit]

    best_result = current_result
    best_specs = current_specs[:]

    if not all_candidates:
        return best_result, best_specs

    for _ in range(trials):
        move_type = random.choice(["add", "replace"])

        if move_type == "add" or not best_specs:
            cand = random.choice(all_candidates)
            if cand.customer in {s.customer for s in best_specs}:
                continue
            trial_specs = best_specs + [cand]
        else:
            remove_idx = random.randrange(len(best_specs))
            cand = random.choice(all_candidates)
            remaining = best_specs[:remove_idx] + best_specs[remove_idx + 1:]
            if cand.customer in {s.customer for s in remaining}:
                continue
            trial_specs = remaining + [cand]

        trial_result = simulate_schedule(problem, order, trial_specs)
        if _strict_ofv_better(trial_result, best_result):
            best_result = trial_result
            best_specs = trial_specs

    return best_result, best_specs


def uav_count_expansion_phase(
    problem: Dict[str, Any],
    order: List[int],
    current_result: SimulationResult,
    current_specs: List[CandidateSpec],
    max_window: Optional[int],
    top_per_customer: int,
    candidate_limit: int,
    rounds: int,
) -> Tuple[SimulationResult, List[CandidateSpec], int]:
    """
    V4 secondary optimization phase for avg_numUAVcust.

    It tries to add or replace UAV sorties in order to serve more customers by UAV,
    while keeping exact simulated makespan within a very small tolerance band around
    the best OFV solution available at the start of this phase.
    """
    group = _group_key(len(order))
    reference_ofv_result = current_result

    all_candidates = generate_candidate_specs(
        problem,
        order,
        max_window=max_window,
        top_per_customer=top_per_customer,
        minimum_improvement=_candidate_min_estimated_improvement(order),
    )[:candidate_limit]

    best_result = current_result
    best_specs = current_specs[:]
    accepted_moves = 0

    if not all_candidates:
        return best_result, best_specs, accepted_moves

    for _ in range(rounds):
        improved_this_round = False

        # A) Try additions first: directly increases numUAVcust.
        for cand in all_candidates:
            if cand.customer in {s.customer for s in best_specs}:
                continue

            trial_specs = best_specs + [cand]
            trial_result = simulate_schedule(problem, order, trial_specs)

            if _uav_count_better_within_tolerance(
                trial_result,
                best_result,
                reference_ofv_result,
                group,
            ):
                best_result = trial_result
                best_specs = trial_specs
                accepted_moves += 1
                improved_this_round = True

        # B) Try one-for-one replacement: can create room for a later addition
        # or improve OFV while keeping the same UAV count.
        for cand in all_candidates:
            if not best_specs:
                break

            if cand.customer in {s.customer for s in best_specs}:
                continue

            for remove_idx in range(len(best_specs)):
                trial_specs = best_specs[:remove_idx] + best_specs[remove_idx + 1:] + [cand]
                trial_result = simulate_schedule(problem, order, trial_specs)

                if _uav_count_better_within_tolerance(
                    trial_result,
                    best_result,
                    reference_ofv_result,
                    group,
                ):
                    best_result = trial_result
                    best_specs = trial_specs
                    accepted_moves += 1
                    improved_this_round = True
                    break

        if not improved_this_round:
            break

    return best_result, best_specs, accepted_moves


# ============================================================
# Constructive routes
# ============================================================

def clarke_wright_order(problem: Dict[str, Any]) -> List[int]:
    """
    Single-route Clarke-Wright Savings construction.
    """
    depot = _depot(problem)
    customers = _customers(problem)

    if len(customers) <= 1:
        return customers[:]

    fragments: List[List[int]] = [[c] for c in customers]
    savings: List[Tuple[float, int, int]] = []

    for i in customers:
        for j in customers:
            if i == j:
                continue
            saving = (
                _truck_time(problem, depot, i)
                + _truck_time(problem, depot, j)
                - _truck_time(problem, i, j)
            )
            savings.append((saving, i, j))

    savings.sort(key=lambda x: x[0], reverse=True)

    def find_fragment(node: int) -> Optional[int]:
        for idx, frag in enumerate(fragments):
            if node in frag:
                return idx
        return None

    for _, i, j in savings:
        if len(fragments) == 1:
            break

        fi = find_fragment(i)
        fj = find_fragment(j)

        if fi is None or fj is None or fi == fj:
            continue

        a = fragments[fi]
        b = fragments[fj]
        merged: Optional[List[int]] = None

        if a[-1] == i and b[0] == j:
            merged = a + b
        elif a[0] == i and b[-1] == j:
            merged = b + a
        elif a[0] == i and b[0] == j:
            merged = list(reversed(a)) + b
        elif a[-1] == i and b[-1] == j:
            merged = a + list(reversed(b))

        if merged is None:
            continue

        for idx in sorted([fi, fj], reverse=True):
            fragments.pop(idx)
        fragments.append(merged)

    # Connect remaining fragments greedily.
    while len(fragments) > 1:
        best = None
        for a_idx in range(len(fragments)):
            for b_idx in range(len(fragments)):
                if a_idx == b_idx:
                    continue
                a = fragments[a_idx]
                b = fragments[b_idx]
                options = [
                    (_truck_time(problem, a[-1], b[0]), a + b),
                    (_truck_time(problem, a[-1], b[-1]), a + list(reversed(b))),
                    (_truck_time(problem, a[0], b[0]), list(reversed(a)) + b),
                    (_truck_time(problem, a[0], b[-1]), list(reversed(a)) + list(reversed(b))),
                ]
                for cost, merged in options:
                    if best is None or cost < best[0]:
                        best = (cost, a_idx, b_idx, merged)

        assert best is not None
        _, a_idx, b_idx, merged = best
        for idx in sorted([a_idx, b_idx], reverse=True):
            fragments.pop(idx)
        fragments.append(merged)

    return fragments[0]


def insertion_order(
    problem: Dict[str, Any],
    randomized: bool = False,
    top_k: int = 1,
) -> List[int]:
    """
    Cheapest-insertion route construction.
    """
    depot = _depot(problem)
    remaining = set(_customers(problem))

    if not remaining:
        return []
    if len(remaining) == 1:
        return [next(iter(remaining))]

    start_options = sorted(
        remaining,
        key=lambda c: _truck_time(problem, depot, c) + _truck_time(problem, c, depot),
    )
    if randomized:
        first = random.choice(start_options[: max(1, min(top_k, len(start_options)))])
    else:
        first = start_options[0]

    order = [first]
    remaining.remove(first)

    while remaining:
        route = route_from_order(problem, order)
        options: List[Tuple[float, int, int]] = []

        for customer in remaining:
            for pos in range(len(route) - 1):
                i = route[pos]
                j = route[pos + 1]
                delta = (
                    _truck_time(problem, i, customer)
                    + _truck_time(problem, customer, j)
                    - _truck_time(problem, i, j)
                )
                options.append((delta, customer, pos))

        options.sort(key=lambda x: x[0])
        chosen = random.choice(options[: max(1, min(top_k, len(options)))])
        _, customer, route_edge_pos = chosen

        # order insertion index equals edge position in route.
        order.insert(route_edge_pos, customer)
        remaining.remove(customer)

    return order


def nearest_neighbor_order(
    problem: Dict[str, Any],
    randomized_top_k: int = 1,
) -> List[int]:
    depot = _depot(problem)
    remaining = set(_customers(problem))
    current = depot
    order: List[int] = []

    while remaining:
        nearest = sorted(remaining, key=lambda c: _truck_time(problem, current, c))
        customer = random.choice(nearest[: max(1, min(randomized_top_k, len(nearest)))])
        order.append(customer)
        remaining.remove(customer)
        current = customer

    return order


# ============================================================
# Mutation and crossover
# ============================================================

def mutate_swap(order: List[int]) -> List[int]:
    result = order[:]
    if len(result) < 2:
        return result
    i, j = random.sample(range(len(result)), 2)
    result[i], result[j] = result[j], result[i]
    return result


def mutate_reverse(order: List[int]) -> List[int]:
    result = order[:]
    if len(result) < 3:
        return result
    i, j = sorted(random.sample(range(len(result)), 2))
    result[i:j + 1] = reversed(result[i:j + 1])
    return result


def mutate_relocate(order: List[int]) -> List[int]:
    result = order[:]
    if len(result) < 3:
        return result
    i, j = random.sample(range(len(result)), 2)
    value = result.pop(i)
    result.insert(j, value)
    return result


def mutate_mixed(order: List[int]) -> List[int]:
    r = random.random()
    if r < 0.34:
        return mutate_swap(order)
    if r < 0.67:
        return mutate_reverse(order)
    return mutate_relocate(order)


def order_crossover(parent1: List[int], parent2: List[int]) -> List[int]:
    n = len(parent1)
    if n < 2:
        return parent1[:]

    a, b = sorted(random.sample(range(n), 2))
    child: List[Optional[int]] = [None] * n
    child[a:b + 1] = parent1[a:b + 1]

    fill = [gene for gene in parent2 if gene not in child]
    fill_idx = 0

    for idx in list(range(0, a)) + list(range(b + 1, n)):
        child[idx] = fill[fill_idx]
        fill_idx += 1

    return [int(gene) for gene in child]


# ============================================================
# Local search using approximate parallel-UAV fitness
# ============================================================

def local_search_order(
    problem: Dict[str, Any],
    seed: List[int],
    max_window: Optional[int],
    top_per_customer: int,
    rounds: int,
    trials_per_round: int,
) -> List[int]:
    best = seed[:]
    best_score = approximate_route_fitness(
        problem,
        best,
        max_window=max_window,
        top_per_customer=top_per_customer,
    )

    for _ in range(rounds):
        improved = False

        for _ in range(trials_per_round):
            candidate = mutate_mixed(best)
            score = approximate_route_fitness(
                problem,
                candidate,
                max_window=max_window,
                top_per_customer=top_per_customer,
            )

            if score + 1e-9 < best_score:
                best = candidate
                best_score = score
                improved = True

        if not improved:
            # One small diversification jump.
            candidate = mutate_mixed(mutate_mixed(best))
            score = approximate_route_fitness(
                problem,
                candidate,
                max_window=max_window,
                top_per_customer=top_per_customer,
            )
            if score + 1e-9 < best_score:
                best = candidate
                best_score = score

    return best


def exact_truck_tsp_seed_for_10(problem: Dict[str, Any]) -> List[int]:
    """
    Held-Karp dynamic-programming seed for the directed/asymmetric truck route.

    For 10 customers this is cheap enough and gives a much stronger route seed
    than Clarke-Wright alone. Truck service times are order-independent, so the
    DP minimizes truck travel time; the UAV-aware search then refines it.
    """
    customers = _customers(problem)
    n = len(customers)
    depot = _depot(problem)

    if n == 0:
        return []
    if n > 12:
        return insertion_order(problem)

    # dp[(mask, last_idx)] = (cost, previous_idx)
    dp: Dict[Tuple[int, int], Tuple[float, Optional[int]]] = {}

    for i, customer in enumerate(customers):
        dp[(1 << i, i)] = (_truck_time(problem, depot, customer), None)

    for mask in range(1, 1 << n):
        for last in range(n):
            key = (mask, last)
            if key not in dp:
                continue

            cost, _ = dp[key]
            for nxt in range(n):
                if mask & (1 << nxt):
                    continue
                new_mask = mask | (1 << nxt)
                new_cost = cost + _truck_time(problem, customers[last], customers[nxt])
                new_key = (new_mask, nxt)

                if new_key not in dp or new_cost + 1e-9 < dp[new_key][0]:
                    dp[new_key] = (new_cost, last)

    full_mask = (1 << n) - 1
    best_last = None
    best_cost = float("inf")

    for last in range(n):
        key = (full_mask, last)
        if key not in dp:
            continue
        total_cost = dp[key][0] + _truck_time(problem, customers[last], depot)
        if total_cost + 1e-9 < best_cost:
            best_cost = total_cost
            best_last = last

    if best_last is None:
        return insertion_order(problem)

    # Reconstruct backwards.
    order_idx_rev: List[int] = []
    mask = full_mask
    last = best_last

    while last is not None:
        order_idx_rev.append(last)
        _, prev = dp[(mask, last)]
        mask = mask & ~(1 << last)
        last = prev

    order_idx_rev.reverse()
    return [customers[idx] for idx in order_idx_rev]


def micro_ga_search_10(problem: Dict[str, Any]) -> List[int]:
    """
    V4 replacement for the weak 10-customer CW+insertion pipeline.

    It uses:
    - exact truck-TSP DP seed,
    - Clarke-Wright/insertion/nearest-neighbor seeds,
    - a small UAV-aware genetic search,
    - local search polish.
    """
    group = 10
    settings = CANDIDATE_SETTINGS[group]

    population_size = 34
    generations = 62
    elite_size = 5
    tournament_size = 4
    mutation_rate = 0.34
    crossover_rate = 0.92

    population: List[List[int]] = [
        exact_truck_tsp_seed_for_10(problem),
        clarke_wright_order(problem),
        insertion_order(problem),
        nearest_neighbor_order(problem),
    ]

    while len(population) < 18:
        if random.random() < 0.55:
            population.append(insertion_order(problem, randomized=True, top_k=5))
        else:
            population.append(nearest_neighbor_order(problem, randomized_top_k=5))

    customers = _customers(problem)
    while len(population) < population_size:
        candidate = customers[:]
        random.shuffle(candidate)
        population.append(candidate)

    global_best = None
    global_best_score = float("inf")

    for _ in range(generations):
        fitnesses = [
            approximate_route_fitness(
                problem,
                order,
                max_window=settings["fitness_window"],
                top_per_customer=settings["top_per_customer"],
            )
            for order in population
        ]

        ranked = sorted(zip(fitnesses, population), key=lambda x: x[0])

        if ranked[0][0] + 1e-9 < global_best_score:
            global_best_score = ranked[0][0]
            global_best = ranked[0][1][:]

        next_population: List[List[int]] = [order[:] for _, order in ranked[:elite_size]]

        # Strong local polish on the top few.
        for elite_idx in range(min(3, len(next_population))):
            next_population[elite_idx] = local_search_order(
                problem,
                next_population[elite_idx],
                max_window=settings["fitness_window"],
                top_per_customer=settings["top_per_customer"],
                rounds=2,
                trials_per_round=48,
            )

        while len(next_population) < population_size:
            p1 = tournament_select(population, fitnesses, tournament_size)
            p2 = tournament_select(population, fitnesses, tournament_size)

            if random.random() < crossover_rate:
                child = order_crossover(p1, p2)
            else:
                child = p1[:]

            if random.random() < mutation_rate:
                child = mutate_mixed(child)
                if random.random() < 0.18:
                    child = mutate_mixed(child)

            next_population.append(child)

        population = next_population

    candidates = population[:]
    if global_best is not None:
        candidates.append(global_best)

    best_order = min(
        candidates,
        key=lambda order: approximate_route_fitness(
            problem,
            order,
            max_window=settings["fitness_window"],
            top_per_customer=settings["top_per_customer"],
        ),
    )

    best_order = local_search_order(
        problem,
        best_order,
        max_window=settings["fitness_window"],
        top_per_customer=settings["top_per_customer"],
        rounds=3,
        trials_per_round=80,
    )

    return best_order


def small_group_search(problem: Dict[str, Any], group: int) -> List[int]:
    settings = CANDIDATE_SETTINGS[group]
    ls = LOCAL_SEARCH_SETTINGS[group]

    seeds: List[List[int]] = [
        clarke_wright_order(problem),
        insertion_order(problem),
        nearest_neighbor_order(problem),
    ]

    for _ in range(max(0, ls["starts"] - len(seeds))):
        roll = random.random()
        if roll < 0.50:
            seeds.append(insertion_order(problem, randomized=True, top_k=4))
        else:
            seeds.append(nearest_neighbor_order(problem, randomized_top_k=4))

    best_order = None
    best_score = float("inf")

    for seed in seeds:
        improved = local_search_order(
            problem,
            seed,
            max_window=settings["fitness_window"],
            top_per_customer=settings["top_per_customer"],
            rounds=ls["rounds"],
            trials_per_round=ls["trials"],
        )
        score = approximate_route_fitness(
            problem,
            improved,
            max_window=settings["fitness_window"],
            top_per_customer=settings["top_per_customer"],
        )
        if score + 1e-9 < best_score:
            best_score = score
            best_order = improved

    assert best_order is not None
    return best_order


# ============================================================
# Memetic Genetic Algorithm for 50 / 100
# ============================================================

def seed_population(problem: Dict[str, Any], population_size: int) -> List[List[int]]:
    population: List[List[int]] = [
        clarke_wright_order(problem),
        insertion_order(problem),
        nearest_neighbor_order(problem),
    ]

    while len(population) < max(10, population_size // 2):
        if random.random() < 0.55:
            population.append(insertion_order(problem, randomized=True, top_k=5))
        else:
            population.append(nearest_neighbor_order(problem, randomized_top_k=5))

    customers = _customers(problem)
    while len(population) < population_size:
        candidate = customers[:]
        random.shuffle(candidate)
        population.append(candidate)

    return population


def tournament_select(population: List[List[int]], fitnesses: List[float], size: int) -> List[int]:
    indexes = random.sample(range(len(population)), k=min(size, len(population)))
    best_idx = min(indexes, key=lambda idx: fitnesses[idx])
    return population[best_idx][:]


def memetic_ga_search(problem: Dict[str, Any], group: int) -> List[int]:
    ga = GA_SETTINGS[group]
    candidate_settings = CANDIDATE_SETTINGS[group]

    pop_size = ga["population_size"]
    population = seed_population(problem, pop_size)

    # Light polish on strongest constructive seeds.
    for idx in range(min(5, len(population))):
        population[idx] = local_search_order(
            problem,
            population[idx],
            max_window=candidate_settings["fitness_window"],
            top_per_customer=candidate_settings["top_per_customer"],
            rounds=1,
            trials_per_round=20,
        )

    global_best = None
    global_best_score = float("inf")

    for _ in range(ga["generations"]):
        fitnesses = [
            approximate_route_fitness(
                problem,
                order,
                max_window=candidate_settings["fitness_window"],
                top_per_customer=candidate_settings["top_per_customer"],
            )
            for order in population
        ]

        ranked = sorted(zip(fitnesses, population), key=lambda x: x[0])

        if ranked[0][0] + 1e-9 < global_best_score:
            global_best_score = ranked[0][0]
            global_best = ranked[0][1][:]

        next_population: List[List[int]] = [order[:] for _, order in ranked[:ga["elite_size"]]]

        # Memetic polish on a few elites.
        for elite_idx in range(min(3, len(next_population))):
            next_population[elite_idx] = local_search_order(
                problem,
                next_population[elite_idx],
                max_window=candidate_settings["fitness_window"],
                top_per_customer=candidate_settings["top_per_customer"],
                rounds=ga["elite_polish_rounds"],
                trials_per_round=ga["elite_polish_trials"],
            )

        while len(next_population) < pop_size:
            p1 = tournament_select(population, fitnesses, ga["tournament_size"])
            p2 = tournament_select(population, fitnesses, ga["tournament_size"])

            if random.random() < ga["crossover_rate"]:
                child = order_crossover(p1, p2)
            else:
                child = p1[:]

            if random.random() < ga["mutation_rate"]:
                child = mutate_mixed(child)
                if random.random() < 0.20:
                    child = mutate_mixed(child)

            next_population.append(child)

        population = next_population

    final_pool = population[:]
    if global_best is not None:
        final_pool.append(global_best)

    best_order = min(
        final_pool,
        key=lambda order: approximate_route_fitness(
            problem,
            order,
            max_window=candidate_settings["fitness_window"],
            top_per_customer=candidate_settings["top_per_customer"],
        ),
    )

    return best_order[:]


# ============================================================
# Gurobi settings
# ============================================================

# Size-limited (free) license: 2000 variables / 2000 linear constraints.
LICENSE_MAX_VARS = 1900
LICENSE_MAX_CONSTRS = 1900

# The asymmetric TSP has n * (n + 1) binary arcs, so it only fits for small n.
TSP_MAX_CUSTOMERS = 25
TSP_TIME_LIMIT = 30.0

# Sortie-selection MIP settings per customer group.
# top_per_customer is larger than in the no-Gurobi version because the MIP
# can search the bigger candidate set exactly.
MIP_SETTINGS = {
    8:   {"top_per_customer": 20, "pool_solutions": 12, "time_limit": 5.0,  "repair_insertions": 6},
    10:  {"top_per_customer": 20, "pool_solutions": 12, "time_limit": 5.0,  "repair_insertions": 8},
    25:  {"top_per_customer": 14, "pool_solutions": 10, "time_limit": 8.0,  "repair_insertions": 10},
    50:  {"top_per_customer": 10, "pool_solutions": 8,  "time_limit": 10.0, "repair_insertions": 12},
    100: {"top_per_customer": 8,  "pool_solutions": 6,  "time_limit": 15.0, "repair_insertions": 12},
}

GUROBI_STATS: Dict[str, int] = {}

_ENV: Optional[gp.Env] = None


def _reset_stats() -> None:
    GUROBI_STATS.clear()
    GUROBI_STATS.update({
        "tsp_solves": 0,
        "tsp_failures": 0,
        "tsp_seed_used": 0,
        "mip_solves": 0,
        "mip_optimal": 0,
        "mip_failures": 0,
        "pool_solutions_evaluated": 0,
        "mip_schedule_wins": 0,
    })


def _env() -> gp.Env:
    global _ENV
    if _ENV is None:
        _ENV = gp.Env(empty=True)
        _ENV.setParam("OutputFlag", 0)
        _ENV.start()
    return _ENV


# ============================================================
# 1) Exact truck TSP seed with lazy subtour elimination
# ============================================================

def _subtours(nodes: List[int], succ: Dict[int, int]) -> List[List[int]]:
    unvisited = set(nodes)
    cycles: List[List[int]] = []

    while unvisited:
        start = next(iter(unvisited))
        cycle = []
        node = start
        while node in unvisited:
            unvisited.remove(node)
            cycle.append(node)
            node = succ[node]
        cycles.append(cycle)

    return cycles


def gurobi_truck_tsp_order(problem: Dict[str, Any]) -> Optional[List[int]]:
    """
    Minimize truck travel time over depot + customers (asymmetric).
    Truck service times are order-independent, so they are not in the objective.
    """
    customers = _customers(problem)
    depot = _depot(problem)
    nodes = [depot] + customers
    n_arcs = len(nodes) * (len(nodes) - 1)

    if len(customers) < 3 or n_arcs > LICENSE_MAX_VARS:
        return None

    try:
        model = gp.Model("truck_tsp", env=_env())
        model.Params.TimeLimit = TSP_TIME_LIMIT
        model.Params.LazyConstraints = 1

        arcs = [(i, j) for i in nodes for j in nodes if i != j]
        x = model.addVars(arcs, vtype=GRB.BINARY, name="x")
        model.setObjective(
            gp.quicksum(_truck_time(problem, i, j) * x[i, j] for i, j in arcs),
            GRB.MINIMIZE,
        )
        model.addConstrs((x.sum(i, "*") == 1 for i in nodes), name="out")
        model.addConstrs((x.sum("*", j) == 1 for j in nodes), name="in")

        def subtour_callback(m: gp.Model, where: int) -> None:
            if where != GRB.Callback.MIPSOL:
                return
            values = m.cbGetSolution(x)
            succ = {i: j for (i, j), v in values.items() if v > 0.5}
            for cycle in _subtours(nodes, succ):
                if len(cycle) < len(nodes):
                    m.cbLazy(
                        gp.quicksum(x[i, j] for i in cycle for j in cycle if i != j)
                        <= len(cycle) - 1
                    )

        model.optimize(subtour_callback)

        if model.SolCount == 0:
            GUROBI_STATS["tsp_failures"] += 1
            return None

        succ = {i: j for (i, j) in arcs if x[i, j].X > 0.5}
        order: List[int] = []
        node = succ[depot]
        while node != depot and len(order) <= len(customers):
            order.append(node)
            node = succ[node]

        GUROBI_STATS["tsp_solves"] += 1

        if sorted(order) != sorted(customers):
            GUROBI_STATS["tsp_failures"] += 1
            return None

        return order

    except gp.GurobiError as exc:
        print("WARNING: Gurobi TSP failed, using no-Gurobi route only: %s" % exc)
        GUROBI_STATS["tsp_failures"] += 1
        return None


# ============================================================
# 2) Sortie-selection MIP
# ============================================================

def select_sorties_mip(
    problem: Dict[str, Any],
    order: List[int],
    candidates: List[CandidateSpec],
    pool_solutions: int,
    time_limit: float,
) -> List[List[CandidateSpec]]:
    """
    Return a pool of sortie selections (best estimated benefit first).
    """
    if not candidates:
        return []

    num_uavs = max(1, len(_uavs(problem)))
    route_len = len(order) + 2

    # simulate_schedule() visits the depot twice (start and end) and would
    # launch a depot sortie again at the end, so it rejects depot launches.
    depot = _depot(problem)
    candidates = [c for c in candidates if c.launch_node != depot]

    # Keep the strongest candidates if the license limit would be exceeded.
    candidates = sorted(candidates, key=lambda c: c.estimated_improvement, reverse=True)
    candidates = candidates[:LICENSE_MAX_VARS]

    customers_used = {c.customer for c in candidates}
    protected_nodes = {c.launch_node for c in candidates} | {c.recovery_node for c in candidates}
    conflict_nodes = customers_used & protected_nodes
    n_constrs = len(customers_used) + len(conflict_nodes) + (route_len - 1)

    if n_constrs > LICENSE_MAX_CONSTRS:
        return []

    bonus = float(_uav_count_settings_for_order(order)["route_bonus_seconds_per_uav"])

    try:
        model = gp.Model("sortie_selection", env=_env())
        model.Params.TimeLimit = time_limit
        model.Params.PoolSearchMode = 2
        model.Params.PoolSolutions = pool_solutions

        x = model.addVars(len(candidates), vtype=GRB.BINARY, name="x")
        model.setObjective(
            gp.quicksum((c.estimated_improvement + bonus) * x[k] for k, c in enumerate(candidates)),
            GRB.MAXIMIZE,
        )

        by_customer: Dict[int, List[int]] = {}
        uses_node: Dict[int, List[int]] = {}
        for k, c in enumerate(candidates):
            by_customer.setdefault(c.customer, []).append(k)
            uses_node.setdefault(c.launch_node, []).append(k)
            uses_node.setdefault(c.recovery_node, []).append(k)

        # Each customer is served by at most one sortie.
        for customer, ks in by_customer.items():
            model.addConstr(gp.quicksum(x[k] for k in ks) <= 1, name="cust_%d" % customer)

        # A launch/recovery node must stay on the truck route.
        # At most num_uavs sorties launch from, and num_uavs recover at, one node,
        # so 2 * num_uavs is a valid big-M.
        big_m = 2 * num_uavs
        for node in conflict_nodes:
            model.addConstr(
                gp.quicksum(x[k] for k in uses_node[node])
                + big_m * gp.quicksum(x[k] for k in by_customer[node])
                <= big_m,
                name="keep_%d" % node,
            )

        # Physical fleet size over each route segment.
        for pos in range(route_len - 1):
            covering = [
                k for k, c in enumerate(candidates)
                if c.launch_pos <= pos < c.recovery_pos
            ]
            if len(covering) > num_uavs:
                model.addConstr(gp.quicksum(x[k] for k in covering) <= num_uavs, name="fleet_%d" % pos)

        model.optimize()
        GUROBI_STATS["mip_solves"] += 1

        if model.Status == GRB.OPTIMAL:
            GUROBI_STATS["mip_optimal"] += 1

        selections: List[List[CandidateSpec]] = []
        for sol in range(model.SolCount):
            model.Params.SolutionNumber = sol
            chosen = [candidates[k] for k in range(len(candidates)) if x[k].Xn > 0.5]
            selections.append(chosen)

        return selections

    except gp.GurobiError as exc:
        print("WARNING: Gurobi sortie MIP failed, using greedy schedule: %s" % exc)
        GUROBI_STATS["mip_failures"] += 1
        return []


# ============================================================
# Exact repair of a MIP selection
# ============================================================

def _drop_descent(
    problem: Dict[str, Any],
    order: List[int],
    result: SimulationResult,
    specs: List[CandidateSpec],
) -> Tuple[SimulationResult, List[CandidateSpec]]:
    """
    The MIP benefit is additive, while the simulation is not.
    Remove sorties one at a time while that improves the exact makespan.
    """
    best_result = result
    best_specs = specs[:]

    while best_specs:
        move_result = best_result
        move_specs = None

        for idx in range(len(best_specs)):
            trial_specs = best_specs[:idx] + best_specs[idx + 1:]
            trial_result = simulate_schedule(problem, order, trial_specs)
            if _strict_ofv_better(trial_result, move_result):
                move_result = trial_result
                move_specs = trial_specs

        if move_specs is None:
            break

        best_result = move_result
        best_specs = move_specs

    return best_result, best_specs


def _greedy_extend(
    problem: Dict[str, Any],
    order: List[int],
    result: SimulationResult,
    specs: List[CandidateSpec],
    candidates: List[CandidateSpec],
    max_insertions: int,
) -> Tuple[SimulationResult, List[CandidateSpec]]:
    """
    Same acceptance rule as exact_greedy_parallel_scheduler, but starting
    from an existing selection.
    """
    best_result = result
    best_specs = specs[:]

    for _ in range(max_insertions):
        selected_customers = {s.customer for s in best_specs}
        protected_nodes = {s.launch_node for s in best_specs} | {s.recovery_node for s in best_specs}

        move_result = best_result
        move_cand = None

        for cand in candidates:
            if cand.customer in selected_customers or cand.customer in protected_nodes:
                continue
            if cand.launch_node in selected_customers or cand.recovery_node in selected_customers:
                continue

            trial_result = simulate_schedule(problem, order, best_specs + [cand])
            if _strict_ofv_better(trial_result, move_result):
                move_result = trial_result
                move_cand = cand

        if move_cand is None:
            break

        best_result = move_result
        best_specs = best_specs + [move_cand]

    return best_result, best_specs


def gurobi_parallel_scheduler(
    problem: Dict[str, Any],
    order: List[int],
    max_window: Optional[int],
    top_per_customer: int,
    candidate_limit: int,
    max_insertions: int,
) -> Tuple[SimulationResult, List[CandidateSpec]]:
    """
    Best of:
      - the no-Gurobi exact greedy scheduler,
      - every Gurobi pool selection after exact repair.
    """
    group = _group_key(len(order))
    mip = MIP_SETTINGS[group]

    best_result, best_specs = exact_greedy_parallel_scheduler(
        problem,
        order,
        max_window=max_window,
        top_per_customer=top_per_customer,
        candidate_limit=candidate_limit,
        max_insertions=max_insertions,
    )

    mip_candidates = generate_candidate_specs(
        problem,
        order,
        max_window=max_window,
        top_per_customer=max(top_per_customer, mip["top_per_customer"]),
        minimum_improvement=_candidate_min_estimated_improvement(order),
    )

    selections = select_sorties_mip(
        problem,
        order,
        mip_candidates,
        pool_solutions=mip["pool_solutions"],
        time_limit=mip["time_limit"],
    )

    # Drop-descent every pool solution, then extend only the best one
    # (greedy extension is the expensive part).
    pool_best_result: Optional[SimulationResult] = None
    pool_best_specs: List[CandidateSpec] = []

    for selection in selections:
        GUROBI_STATS["pool_solutions_evaluated"] += 1
        trial_result = simulate_schedule(problem, order, selection)
        if not trial_result.valid:
            continue

        trial_result, trial_specs = _drop_descent(problem, order, trial_result, selection)

        if pool_best_result is None or _strict_ofv_better(trial_result, pool_best_result):
            pool_best_result = trial_result
            pool_best_specs = trial_specs

    if pool_best_result is not None:
        pool_best_result, pool_best_specs = _greedy_extend(
            problem,
            order,
            pool_best_result,
            pool_best_specs,
            mip_candidates[:candidate_limit],
            max_insertions=mip["repair_insertions"],
        )

        if _strict_ofv_better(pool_best_result, best_result):
            GUROBI_STATS["mip_schedule_wins"] += 1
            best_result = pool_best_result
            best_specs = pool_best_specs

    return best_result, best_specs


# ============================================================
# Route search with an optional Gurobi TSP seed
# ============================================================

def gurobi_route_search(problem: Dict[str, Any], group: int) -> Tuple[List[Tuple[str, List[int]]], str]:
    """
    Return labelled candidate truck orders. The route search ranks orders with
    the approximate (greedy) fitness, which can miss orders that the sortie MIP
    schedules better, so the simple construction seeds are kept as candidates
    and every candidate is scheduled with gurobi_parallel_scheduler().
    """
    if group == 8:
        order = small_group_search(problem, group)
        strategy = "Gurobi_TSPSeed_SortieMIP_LocalSearch_8"
    elif group == 10:
        order = micro_ga_search_10(problem)
        strategy = "Gurobi_TSPSeed_SortieMIP_MicroGA_10"
    elif group == 25:
        order = small_group_search(problem, group)
        strategy = "Gurobi_TSPSeed_SortieMIP_LocalSearch_25"
    else:
        order = memetic_ga_search(problem, group)
        strategy = "Gurobi_SortieMIP_MemeticGA_%d" % group

    orders: List[Tuple[str, List[int]]] = [
        ("route_search", order),
        ("clarke_wright", clarke_wright_order(problem)),
        ("insertion", insertion_order(problem)),
        ("nearest_neighbor", nearest_neighbor_order(problem)),
    ]

    if len(_customers(problem)) > TSP_MAX_CUSTOMERS:
        return orders, strategy

    tsp_order = gurobi_truck_tsp_order(problem)
    if tsp_order is None:
        return orders, strategy

    settings = CANDIDATE_SETTINGS[group]
    ls = LOCAL_SEARCH_SETTINGS.get(group, {"rounds": 6, "trials": 85})

    orders.append(("gurobi_tsp", tsp_order))
    orders.append((
        "gurobi_tsp_local_search",
        local_search_order(
            problem,
            tsp_order,
            max_window=settings["fitness_window"],
            top_per_customer=settings["top_per_customer"],
            rounds=ls["rounds"],
            trials_per_round=ls["trials"],
        ),
    ))

    return orders, strategy


# ============================================================
# Route polish using the Gurobi scheduler
# ============================================================

def final_route_schedule_polish(
    problem: Dict[str, Any],
    order: List[int],
    group: int,
    initial_result: SimulationResult,
    initial_specs: List[CandidateSpec],
) -> Tuple[List[int], SimulationResult, List[CandidateSpec]]:
    candidate_settings = CANDIDATE_SETTINGS[group]
    final_settings = FINAL_SCHEDULE_SETTINGS[group]

    best_order = order[:]
    best_result = initial_result
    best_specs = initial_specs[:]

    if group <= 10:
        route_trials = 14
    elif group <= 25:
        route_trials = 10
    elif group <= 50:
        route_trials = 6
    else:
        route_trials = 4

    for _ in range(route_trials):
        candidate_order = mutate_mixed(best_order)
        trial_result, trial_specs = gurobi_parallel_scheduler(
            problem,
            candidate_order,
            max_window=candidate_settings["final_window"],
            top_per_customer=candidate_settings["top_per_customer"],
            candidate_limit=final_settings["candidate_limit"],
            max_insertions=final_settings["max_insertions"],
        )

        if trial_result.valid and trial_result.makespan + 1e-9 < best_result.makespan:
            best_order = candidate_order
            best_result = trial_result
            best_specs = trial_specs

    return best_order, best_result, best_specs


# ============================================================
# Main solver entry point
# ============================================================

def proposed_heuristic_with_gurobi(problem: Dict[str, Any]) -> Dict[str, Any]:
    started_at = time.time()
    _reset_stats()

    n = len(_customers(problem))
    group = _group_key(n)

    candidate_orders, strategy = gurobi_route_search(problem, group)

    candidate_settings = CANDIDATE_SETTINGS[group]
    final_settings = FINAL_SCHEDULE_SETTINGS[group]

    # Schedule every candidate order exactly and keep the best one.
    result: Optional[SimulationResult] = None
    selected_specs: List[CandidateSpec] = []
    order: List[int] = []
    order_source = ""

    for label, candidate_order in candidate_orders:
        trial_result, trial_specs = gurobi_parallel_scheduler(
            problem,
            candidate_order,
            max_window=candidate_settings["final_window"],
            top_per_customer=candidate_settings["top_per_customer"],
            candidate_limit=final_settings["candidate_limit"],
            max_insertions=final_settings["max_insertions"],
        )
        if result is None or _strict_ofv_better(trial_result, result):
            result, selected_specs = trial_result, trial_specs
            order, order_source = candidate_order, label

    if order_source.startswith("gurobi_tsp"):
        GUROBI_STATS["tsp_seed_used"] += 1

    result, selected_specs = final_schedule_improvement_trials(
        problem,
        order,
        result,
        selected_specs,
        max_window=candidate_settings["final_window"],
        top_per_customer=candidate_settings["top_per_customer"],
        candidate_limit=final_settings["candidate_limit"],
        trials=final_settings["improvement_trials"],
    )

    result, selected_specs, uav_count_expansion_moves_1 = uav_count_expansion_phase(
        problem,
        order,
        result,
        selected_specs,
        max_window=candidate_settings["final_window"],
        top_per_customer=candidate_settings["top_per_customer"],
        candidate_limit=final_settings["candidate_limit"],
        rounds=final_settings["count_expansion_rounds"],
    )

    order, result, selected_specs = final_route_schedule_polish(
        problem,
        order,
        group,
        result,
        selected_specs,
    )

    result, selected_specs = final_schedule_improvement_trials(
        problem,
        order,
        result,
        selected_specs,
        max_window=candidate_settings["final_window"],
        top_per_customer=candidate_settings["top_per_customer"],
        candidate_limit=final_settings["candidate_limit"],
        trials=max(10, final_settings["improvement_trials"] // 2),
    )

    result, selected_specs, uav_count_expansion_moves_2 = uav_count_expansion_phase(
        problem,
        order,
        result,
        selected_specs,
        max_window=candidate_settings["final_window"],
        top_per_customer=candidate_settings["top_per_customer"],
        candidate_limit=final_settings["candidate_limit"],
        rounds=final_settings["count_expansion_rounds"],
    )

    if not result.valid:
        # Safe fallback: truck-only schedule, never return an infeasible solution.
        result = simulate_schedule(problem, order, [])
        selected_specs = []

    depot = _depot(problem)
    truck_customers = [node for node in result.truck_route if node != depot]
    uav_customers = [sortie.customer for sortie in result.scheduled_sorties]

    solution = {
        "problem_id": problem.get("problem_id", ""),
        "makespan": result.makespan,
        "truck_waiting_time": result.truck_waiting_time,
        "uav_waiting_time": result.uav_waiting_time,
        "num_truck_customers": len(truck_customers),
        "num_uav_customers": len(uav_customers),
        "truck_customers": truck_customers,
        "uav_customers": uav_customers,
        "truck_route": result.truck_route,
        "uav_sorties": [sortie.as_dict() for sortie in result.scheduled_sorties],
        "activity_log": result.activity_log,
        "validation": result.validation,
        "runtime": time.time() - started_at,
        "strategy": strategy,
        "max_parallel_uavs_used": result.max_parallel_uavs_used,
        "num_physical_uavs": len(_uavs(problem)),
        "optimization_version": "Gurobi_TSPSeed_SortieSelectionMIP_on_V4",
        "uav_count_expansion_moves": int(uav_count_expansion_moves_1 + uav_count_expansion_moves_2),
        "metadata": {
            "uses_gurobi": GUROBI_STATS["mip_solves"] + GUROBI_STATS["tsp_solves"] > 0,
            "gurobi_version": "%d.%d.%d" % gp.gurobi.version(),
            "gurobi": dict(GUROBI_STATS),
            "initial_order_source": order_source,
            "random_seed": RANDOM_SEED,
            "customer_group": group,
            "num_customers": n,
            "fitness_window": candidate_settings["fitness_window"],
            "final_window": candidate_settings["final_window"],
            "uav_count_tolerance_ratio": UAV_COUNT_SETTINGS[group]["final_count_makespan_tolerance_ratio"],
            "uav_count_tolerance_seconds": UAV_COUNT_SETTINGS[group]["final_count_makespan_tolerance_seconds"],
            "route_bonus_seconds_per_uav": UAV_COUNT_SETTINGS[group]["route_bonus_seconds_per_uav"],
        },
    }

    return solution


# ============================================================
# CSV persistence expected by main.py
# ============================================================

def save_solution(solution: Dict[str, Any], output_csv_path: str) -> None:
    output_path = Path(output_csv_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "problem_id",
        "optimization_version",
        "strategy",
        "makespan",
        "truck_waiting_time",
        "uav_waiting_time",
        "num_truck_customers",
        "num_uav_customers",
        "num_physical_uavs",
        "max_parallel_uavs_used",
        "uav_count_expansion_moves",
        "runtime",
        "valid",
        "truck_route",
        "uav_sorties",
    ]

    file_exists = output_path.exists()

    with output_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        validation = solution.get("validation", {})

        writer.writerow({
            "problem_id": solution.get("problem_id", ""),
            "optimization_version": solution.get("optimization_version", ""),
            "strategy": solution.get("strategy", ""),
            "makespan": solution.get("makespan", ""),
            "truck_waiting_time": solution.get("truck_waiting_time", ""),
            "uav_waiting_time": solution.get("uav_waiting_time", ""),
            "num_truck_customers": solution.get("num_truck_customers", ""),
            "num_uav_customers": solution.get("num_uav_customers", ""),
            "num_physical_uavs": solution.get("num_physical_uavs", ""),
            "max_parallel_uavs_used": solution.get("max_parallel_uavs_used", ""),
            "uav_count_expansion_moves": solution.get("uav_count_expansion_moves", ""),
            "runtime": solution.get("runtime", ""),
            "valid": validation.get("valid", ""),
            "truck_route": repr(solution.get("truck_route", [])),
            "uav_sorties": repr(solution.get("uav_sorties", [])),
        })
