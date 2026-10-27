#!/usr/bin/env python3
"""
----------------

GUROBI-assisted version of the proposed mFSTSP heuristic.

It keeps the whole framework of proposed_heuristic_no_gurobi.py
(route search, candidate sortie templates, event-based schedule simulation,
UAV-count expansion) and adds Gurobi in two places:

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

import time
from typing import Dict, List, Tuple, Any, Optional

import gurobipy as gp
from gurobipy import GRB

from proposed_heuristic_no_gurobi import (
    CANDIDATE_SETTINGS,
    FINAL_SCHEDULE_SETTINGS,
    LOCAL_SEARCH_SETTINGS,
    UAV_COUNT_SETTINGS,
    RANDOM_SEED,
    CandidateSpec,
    SimulationResult,
    _candidate_min_estimated_improvement,
    _customers,
    _depot,
    _group_key,
    _strict_ofv_better,
    _truck_time,
    _uav_count_settings_for_order,
    _uavs,
    clarke_wright_order,
    exact_greedy_parallel_scheduler,
    final_schedule_improvement_trials,
    generate_candidate_specs,
    insertion_order,
    local_search_order,
    memetic_ga_search,
    micro_ga_search_10,
    mutate_mixed,
    nearest_neighbor_order,
    simulate_schedule,
    small_group_search,
    uav_count_expansion_phase,
    save_solution,
)


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
