"""
proposed_heuristic_no_gurobi.py

Pure no-Gurobi heuristic for mFSTSP.

This file replaces:
1. Gurobi TSP with Nearest Neighbor + 2-opt
2. Gurobi Phase II feasibility with greedy sortie assignment
3. Gurobi Phase III timing model with greedy simulation

Expected problem dictionary format:

problem = {
    "problem_id": "20170608T121355407419",
    "depot": 0,
    "customers": [1, 2, 3, ...],
    "droneable_customers": [1, 3, 5, ...],
    "uavs": [1, 2, 3, 4],

    "truck_time": {
        0: {1: 10, 2: 20, ...},
        1: {0: 10, 2: 5, ...},
        ...
    },

    "uav_time": {
        1: {
            0: {1: 5, 2: 8, ...},
            1: {0: 5, 2: 3, ...},
            ...
        },
        2: {...}
    },

    "truck_service_time": {
        1: 30,
        2: 30,
        ...
    },

    "uav_service_time": {
        1: {1: 60, 2: 60, ...},
        2: {1: 60, 2: 60, ...}
    },

    "uav_endurance": {
        1: 1200,
        2: 1200,
        ...
    },

    "launch_time": {
        1: {"default": 60},
        2: {"default": 60}
    },

    "recovery_time": {
        1: {"default": 30},
        2: {"default": 30}
    }
}
"""

import csv
import os
import time


# =========================================================
# Helper functions
# =========================================================

def get_matrix_value(matrix, i, j):
    """
    Safely get travel time from a nested dictionary or list matrix.

    Supports:
    matrix[i][j]
    """
    try:
        return matrix[i][j]
    except Exception as exc:
        raise KeyError(f"Missing travel time from {i} to {j}") from exc


def get_service_time(service_time, node, default=0):
    """
    Safely get service time.
    Supports dictionary with node keys.
    """
    if service_time is None:
        return default

    if isinstance(service_time, dict):
        return service_time.get(node, default)

    return default


def get_nested_time(time_dict, outer_key, inner_key=None, default=0):
    """
    Used for launch/recovery times.

    Supports:
    launch_time[v]["default"]
    launch_time[v][node]
    launch_time["default"]
    """
    if time_dict is None:
        return default

    if isinstance(time_dict, (int, float)):
        return time_dict

    if outer_key in time_dict:
        value = time_dict[outer_key]

        if isinstance(value, dict):
            if inner_key is not None:
                return value.get(inner_key, value.get("default", default))
            return value.get("default", default)

        if isinstance(value, (int, float)):
            return value

    return time_dict.get("default", default) if isinstance(time_dict, dict) else default


def validate_solution(problem, solution):
    """
    Make sure every customer is served exactly once.
    """
    all_customers = set(problem["customers"])
    truck_customers = set(solution.get("truck_customers", []))
    uav_customers = set(solution.get("uav_customers", []))

    duplicated = truck_customers.intersection(uav_customers)
    served = truck_customers.union(uav_customers)
    missing = all_customers - served
    extra = served - all_customers

    solution["validation"] = {
        "valid": len(duplicated) == 0 and len(missing) == 0 and len(extra) == 0,
        "missing_customers": list(missing),
        "duplicated_customers": list(duplicated),
        "extra_customers": list(extra),
    }

    return solution


# =========================================================
# Phase I: assign truck and UAV customers
# =========================================================

def phase1_assign_customers(problem, LTL):
    """
    Phase I:
    Split customers into:
    - truck_customers
    - uav_customers

    Customers that are not droneable must stay with the truck.
    LTL = lower truck limit.
    """
    customers = list(problem["customers"])
    droneable = set(problem.get("droneable_customers", []))

    # Customers that cannot be served by UAV must stay with truck.
    truck_customers = set(customers) - droneable

    # Customers that can be served by UAV.
    uav_customers = set(customers) - truck_customers

    # Make sure truck has at least LTL customers.
    # Choose customers closest to depot to move to truck first.
    depot = problem["depot"]
    truck_time = problem["truck_time"]

    while len(truck_customers) < LTL and uav_customers:
        j = min(
            uav_customers,
            key=lambda c: get_matrix_value(truck_time, depot, c)
        )
        uav_customers.remove(j)
        truck_customers.add(j)

    return list(truck_customers), list(uav_customers)


# =========================================================
# Truck route: Nearest Neighbor + 2-opt
# =========================================================

def nearest_neighbor_route(customers, depot, travel_time):
    """
    Build a simple truck route:
    depot -> nearest customer -> nearest customer -> ... -> depot
    """
    customers = list(customers)

    if not customers:
        return [depot, depot]

    unvisited = set(customers)
    route = [depot]
    current = depot

    while unvisited:
        next_customer = min(
            unvisited,
            key=lambda j: get_matrix_value(travel_time, current, j)
        )
        route.append(next_customer)
        unvisited.remove(next_customer)
        current = next_customer

    route.append(depot)
    return route


def route_cost(route, travel_time, service_time=None):
    """
    Calculate route cost including travel time and optional truck service time.
    """
    total = 0

    for i in range(len(route) - 1):
        total += get_matrix_value(travel_time, route[i], route[i + 1])

    if service_time:
        for node in route[1:-1]:
            total += get_service_time(service_time, node, 0)

    return total


def two_opt(route, travel_time, service_time=None, max_iterations=1000):
    """
    Improve a route by reversing route segments.
    This is a no-Gurobi TSP improvement heuristic.
    """
    best = route[:]
    improved = True
    iteration = 0

    while improved and iteration < max_iterations:
        iteration += 1
        improved = False
        best_cost = route_cost(best, travel_time, service_time)

        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best) - 1):
                new_route = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                new_cost = route_cost(new_route, travel_time, service_time)

                if new_cost < best_cost:
                    best = new_route
                    improved = True
                    break

            if improved:
                break

    return best


def build_truck_route_no_gurobi(problem, truck_customers):
    """
    Build truck route without Gurobi.
    """
    depot = problem["depot"]
    travel_time = problem["truck_time"]
    service_time = problem.get("truck_service_time", {})

    route = nearest_neighbor_route(truck_customers, depot, travel_time)
    route = two_opt(route, travel_time, service_time)

    return route


# =========================================================
# Phase II: create UAV sorties
# =========================================================

def is_feasible_sortie(problem, v, i, j, k):
    """
    Check if UAV v can launch from i, serve customer j, and recover at k.

    sortie = (v, i, j, k)
    """
    uav_time = problem["uav_time"][v]
    uav_service_time = problem.get("uav_service_time", {})
    endurance_data = problem.get("uav_endurance", {})

    service_j = 0
    if isinstance(uav_service_time, dict):
        if v in uav_service_time and isinstance(uav_service_time[v], dict):
            service_j = uav_service_time[v].get(j, 0)
        else:
            service_j = uav_service_time.get(j, 0)

    endurance = endurance_data.get(v, float("inf"))

    total_flight_time = (
        get_matrix_value(uav_time, i, j)
        + service_j
        + get_matrix_value(uav_time, j, k)
    )

    return total_flight_time <= endurance


def phase2_create_sorties(problem, truck_route, uav_customers):
    """
    Phase II:
    Create UAV sorties greedily.

    For each UAV customer j, try to assign:
    (v, i, j, k)

    where:
    v = UAV
    i = launch node on truck route
    j = UAV customer
    k = recovery node on truck route

    This version first tries adjacent truck nodes only:
    i -> k are consecutive in the truck route.
    """
    uavs = list(problem["uavs"])
    truck_time = problem["truck_time"]
    uav_time = problem["uav_time"]
    uav_service_time = problem.get("uav_service_time", {})

    sorties = []
    unassigned = set(uav_customers)

    # Adjacent truck edges only: truck_route[idx] -> truck_route[idx + 1]
    truck_edges = []
    for idx in range(len(truck_route) - 1):
        i = truck_route[idx]
        k = truck_route[idx + 1]

        if i != k:
            truck_edges.append((i, k))

    # Track UAV usage at each launch node to avoid launching same UAV twice from same node.
    used_uav_at_launch = set()

    while unassigned:
        best_sortie = None
        best_score = float("inf")

        for j in list(unassigned):
            for v in uavs:
                for i, k in truck_edges:
                    if (v, i) in used_uav_at_launch:
                        continue

                    if i == j or k == j or i == k:
                        continue

                    if not is_feasible_sortie(problem, v, i, j, k):
                        continue

                    service_j = 0
                    if isinstance(uav_service_time, dict):
                        if v in uav_service_time and isinstance(uav_service_time[v], dict):
                            service_j = uav_service_time[v].get(j, 0)
                        else:
                            service_j = uav_service_time.get(j, 0)

                    drone_duration = (
                        get_matrix_value(uav_time[v], i, j)
                        + service_j
                        + get_matrix_value(uav_time[v], j, k)
                    )

                    truck_duration = get_matrix_value(truck_time, i, k)

                    # Score tries to reduce waiting between truck and UAV.
                    score = abs(drone_duration - truck_duration)

                    if score < best_score:
                        best_score = score
                        best_sortie = (v, i, j, k)

        if best_sortie is None:
            break

        sorties.append(best_sortie)
        used_uav_at_launch.add((best_sortie[0], best_sortie[1]))
        unassigned.remove(best_sortie[2])

    return sorties, list(unassigned)


# =========================================================
# Phase III: greedy timing scheduler
# =========================================================

def phase3_greedy_schedule(problem, truck_route, uav_sorties):
    """
    Phase III:
    Greedy schedule simulation.

    No Gurobi.
    No MILP.

    Order at each truck node:
    1. Recover UAVs
    2. Truck serves customer
    3. Launch UAVs
    4. Truck travels to next node
    """
    truck_time = problem["truck_time"]
    truck_service = problem.get("truck_service_time", {})

    uav_time = problem["uav_time"]
    uav_service = problem.get("uav_service_time", {})

    launch_time = problem.get("launch_time", {})
    recovery_time = problem.get("recovery_time", {})

    depot = problem["depot"]
    uavs = list(problem["uavs"])

    truck_clock = 0
    truck_waiting_time = 0
    uav_waiting_time = 0

    uav_available_time = {v: 0 for v in uavs}

    launches_at = {}
    recoveries_at = {}

    for sortie in uav_sorties:
        v, i, j, k = sortie
        launches_at.setdefault(i, []).append(sortie)
        recoveries_at.setdefault(k, []).append(sortie)

    # Store when each UAV arrives at its recovery node.
    uav_recovery_arrival = {}

    activity_log = []

    for idx, node in enumerate(truck_route):
        activity_log.append({
            "time": truck_clock,
            "activity": "truck_arrive",
            "node": node,
        })

        # 1. Recover UAVs at this node.
        for sortie in recoveries_at.get(node, []):
            v, i, j, k = sortie

            arrival_time = uav_recovery_arrival.get(sortie, truck_clock)

            # If UAV arrives before truck, UAV waits.
            if arrival_time < truck_clock:
                uav_waiting_time += truck_clock - arrival_time

            # If truck arrives before UAV, truck waits.
            if truck_clock < arrival_time:
                truck_waiting_time += arrival_time - truck_clock
                truck_clock = arrival_time

            rec_time = get_nested_time(recovery_time, v, node, default=30)
            truck_clock += rec_time
            uav_available_time[v] = truck_clock

            activity_log.append({
                "time": truck_clock,
                "activity": "uav_recovered",
                "uav": v,
                "launch_node": i,
                "uav_customer": j,
                "recovery_node": k,
            })

        # 2. Truck service at customer node.
        if node != depot:
            service = get_service_time(truck_service, node, 0)
            truck_clock += service

            activity_log.append({
                "time": truck_clock,
                "activity": "truck_service_done",
                "node": node,
            })

        # 3. Launch UAVs from this node.
        for sortie in launches_at.get(node, []):
            v, i, j, k = sortie

            # If UAV is not available yet, truck waits.
            if truck_clock < uav_available_time[v]:
                truck_waiting_time += uav_available_time[v] - truck_clock
                truck_clock = uav_available_time[v]

            lau_time = get_nested_time(launch_time, v, node, default=60)
            truck_clock += lau_time

            # UAV flight calculation.
            service_j = 0
            if isinstance(uav_service, dict):
                if v in uav_service and isinstance(uav_service[v], dict):
                    service_j = uav_service[v].get(j, 0)
                else:
                    service_j = uav_service.get(j, 0)

            drone_arrive_customer = truck_clock + get_matrix_value(uav_time[v], i, j)
            drone_leave_customer = drone_arrive_customer + service_j
            drone_arrive_recovery = drone_leave_customer + get_matrix_value(uav_time[v], j, k)

            uav_recovery_arrival[sortie] = drone_arrive_recovery

            activity_log.append({
                "time": truck_clock,
                "activity": "uav_launched",
                "uav": v,
                "launch_node": i,
                "uav_customer": j,
                "recovery_node": k,
                "uav_expected_recovery_time": drone_arrive_recovery,
            })

        # 4. Truck travels to next node.
        if idx < len(truck_route) - 1:
            next_node = truck_route[idx + 1]
            truck_clock += get_matrix_value(truck_time, node, next_node)

            activity_log.append({
                "time": truck_clock,
                "activity": "truck_travel_done",
                "from": node,
                "to": next_node,
            })

    makespan = truck_clock

    return {
        "makespan": makespan,
        "truck_route": truck_route,
        "uav_sorties": uav_sorties,
        "truck_waiting_time": truck_waiting_time,
        "uav_waiting_time": uav_waiting_time,
        "activity_log": activity_log,
    }


# =========================================================
# Main no-Gurobi proposed heuristic
# =========================================================

def proposed_heuristic_no_gurobi(problem):
    """
    Main solver.

    This loops over LTL values and keeps the best solution found.
    """
    start_time = time.time()

    n = len(problem["customers"])
    num_uavs = len(problem["uavs"])

    if n == 0:
        return {
            "makespan": 0,
            "truck_route": [problem["depot"], problem["depot"]],
            "uav_sorties": [],
            "truck_customers": [],
            "uav_customers": [],
            "runtime": 0,
            "status": "solved_no_customers",
        }

    initial_ltl = max(1, n // (num_uavs + 1))

    best_solution = None

    for LTL in range(initial_ltl, n + 1):
        truck_customers, uav_customers = phase1_assign_customers(problem, LTL)

        truck_route = build_truck_route_no_gurobi(problem, truck_customers)

        uav_sorties, unassigned = phase2_create_sorties(
            problem,
            truck_route,
            uav_customers
        )

        # If some UAV customers cannot be assigned, move them to truck.
        if unassigned:
            truck_customers = list(set(truck_customers).union(set(unassigned)))
            uav_customers = [c for c in uav_customers if c not in set(unassigned)]

            truck_route = build_truck_route_no_gurobi(problem, truck_customers)

            uav_sorties, unassigned_again = phase2_create_sorties(
                problem,
                truck_route,
                uav_customers
            )

            # If still unassigned, force them to truck too.
            if unassigned_again:
                truck_customers = list(set(truck_customers).union(set(unassigned_again)))
                uav_customers = [c for c in uav_customers if c not in set(unassigned_again)]

                truck_route = build_truck_route_no_gurobi(problem, truck_customers)

                uav_sorties, _ = phase2_create_sorties(
                    problem,
                    truck_route,
                    uav_customers
                )

        solution = phase3_greedy_schedule(
            problem,
            truck_route,
            uav_sorties
        )

        served_by_uav = [sortie[2] for sortie in uav_sorties]
        served_by_truck = [c for c in problem["customers"] if c not in set(served_by_uav)]

        solution["LTL"] = LTL
        solution["truck_customers"] = served_by_truck
        solution["uav_customers"] = served_by_uav
        solution["num_truck_customers"] = len(served_by_truck)
        solution["num_uav_customers"] = len(served_by_uav)
        solution["status"] = "solved_no_gurobi"

        solution = validate_solution(problem, solution)

        if not solution["validation"]["valid"]:
            solution["status"] = "invalid_solution"

        if best_solution is None or solution["makespan"] < best_solution["makespan"]:
            best_solution = solution

    best_solution["runtime"] = time.time() - start_time
    best_solution["problem_id"] = problem.get("problem_id", "unknown")
    best_solution["num_customers"] = len(problem["customers"])
    best_solution["num_uavs"] = len(problem["uavs"])

    return best_solution


# =========================================================
# Save solution
# =========================================================

def save_solution(solution, output_path):
    """
    Save one solution summary row to CSV.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    row = {
        "problem_id": solution.get("problem_id", "unknown"),
        "num_customers": solution.get("num_customers", ""),
        "num_uavs": solution.get("num_uavs", ""),
        "status": solution.get("status", ""),
        "makespan": solution.get("makespan", ""),
        "runtime": solution.get("runtime", ""),
        "LTL": solution.get("LTL", ""),
        "num_truck_customers": solution.get("num_truck_customers", ""),
        "num_uav_customers": solution.get("num_uav_customers", ""),
        "truck_waiting_time": solution.get("truck_waiting_time", ""),
        "uav_waiting_time": solution.get("uav_waiting_time", ""),
        "truck_route": solution.get("truck_route", ""),
        "uav_sorties": solution.get("uav_sorties", ""),
        "validation_valid": solution.get("validation", {}).get("valid", ""),
        "missing_customers": solution.get("validation", {}).get("missing_customers", ""),
        "duplicated_customers": solution.get("validation", {}).get("duplicated_customers", ""),
    }

    file_exists = os.path.exists(output_path)

    with open(output_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)


# =========================================================
# Optional test with fake small data
# =========================================================

if __name__ == "__main__":
    # This is only a small fake test.
    # You can remove this part when connecting to your real project.

    nodes = [0, 1, 2, 3, 4, 5]
    customers = [1, 2, 3, 4, 5]

    truck_time = {
        i: {
            j: 0 if i == j else abs(i - j) * 10 + 5
            for j in nodes
        }
        for i in nodes
    }

    uav_time_one = {
        i: {
            j: 0 if i == j else abs(i - j) * 5 + 2
            for j in nodes
        }
        for i in nodes
    }

    problem = {
        "problem_id": "fake_test",
        "depot": 0,
        "customers": customers,
        "droneable_customers": [2, 3, 4, 5],
        "uavs": [1, 2],
        "truck_time": truck_time,
        "uav_time": {
            1: uav_time_one,
            2: uav_time_one,
        },
        "truck_service_time": {
            1: 30,
            2: 30,
            3: 30,
            4: 30,
            5: 30,
        },
        "uav_service_time": {
            1: {1: 60, 2: 60, 3: 60, 4: 60, 5: 60},
            2: {1: 60, 2: 60, 3: 60, 4: 60, 5: 60},
        },
        "uav_endurance": {
            1: 300,
            2: 300,
        },
        "launch_time": {
            1: {"default": 60},
            2: {"default": 60},
        },
        "recovery_time": {
            1: {"default": 30},
            2: {"default": 30},
        },
    }

    solution = proposed_heuristic_no_gurobi(problem)

    print("Status:", solution["status"])
    print("Makespan:", solution["makespan"])
    print("Truck route:", solution["truck_route"])
    print("UAV sorties:", solution["uav_sorties"])
    print("Truck customers:", solution["truck_customers"])
    print("UAV customers:", solution["uav_customers"])
    print("Validation:", solution["validation"])

    save_solution(solution, "results/no_gurobi_heuristic_results.csv")