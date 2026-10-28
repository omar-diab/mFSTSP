// Educational descriptions grounded in the checked-in source files.
export type Algorithm = {
  id: string;
  name: string;
  family: "Proposed" | "Original";
  source: string;
  fn: string;
  role: string;
  inputs: string;
  outputs: string;
  steps: string[];
  flow: string[];
  pseudocode: string;
  strengths: string;
  limitations: string;
};

const P = "new/proposed_heuristic_with_gurobi.py";

export const ALGORITHMS: Algorithm[] = [
  {
    id: "pipeline",
    name: "Full Gurobi-assisted pipeline",
    family: "Proposed",
    source: P,
    fn: "proposed_heuristic_with_gurobi",
    role: "Entry point called by main.py for problemType 3",
    inputs: "Problem dictionary built by main.py: customers, truck and UAV travel times, service, launch and recovery times, endurance and the physical UAV fleet.",
    outputs: "Makespan, truck route, timed UAV sorties, activity log, validation dictionary, strategy label and Gurobi usage statistics.",
    steps: [
      "Pick the customer group (8, 10, 25, 50 or 100) and its tuned settings.",
      "Build labelled candidate truck orders: the size-specific route search plus Clarke–Wright, insertion and nearest-neighbour seeds (and the Gurobi TSP tour for n ≤ 25).",
      "Schedule every candidate order exactly with the Gurobi parallel scheduler and keep the strictly best makespan.",
      "Run schedule-improvement trials, then the UAV-count expansion phase (more UAV customers within a small makespan tolerance).",
      "Polish the route with mutations rescheduled by Gurobi, then repeat improvement and expansion.",
      "If the final result is invalid, fall back to a truck-only schedule so an infeasible solution is never returned.",
    ],
    flow: ["Problem", "Candidate orders", "Exact scheduling", "Improve + expand", "Route polish", "Validate / fallback", "Save solution"],
    pseudocode: `orders, strategy = gurobi_route_search(problem, group)
result = best(gurobi_parallel_scheduler(problem, o) for o in orders)
result = final_schedule_improvement_trials(result)
result = uav_count_expansion_phase(result)
order, result = final_route_schedule_polish(order, result)
result = final_schedule_improvement_trials(result)
result = uav_count_expansion_phase(result)
if not result.valid:
    result = simulate_schedule(problem, order, [])   # truck only
return solution(result, strategy, GUROBI_STATS)`,
    strengths: "Every candidate is judged by the same exact event simulation, so Gurobi can only improve on the greedy schedule. Falls back safely when Gurobi fails.",
    limitations: "Still a heuristic: there is no global optimality proof. The free Gurobi licence caps every model at roughly 1,900 variables and constraints.",
  },
  {
    id: "tsp",
    name: "Exact truck TSP seed",
    family: "Proposed",
    source: P,
    fn: "gurobi_truck_tsp_order",
    role: "Optimal truck-only tour used as an extra route seed for n ≤ 25",
    inputs: "Depot, customers and asymmetric truck travel times.",
    outputs: "Customer order of the optimal truck-only tour, or None if the model does not fit or fails.",
    steps: [
      "Create one binary arc variable per ordered node pair (n·(n+1) arcs).",
      "Require exactly one outgoing and one incoming arc per node.",
      "Minimise total truck travel time (service time is order-independent, so it is left out).",
      "Add subtour-elimination constraints lazily whenever an integer solution contains a cycle that skips the depot.",
      "Return the tour; it competes raw and after the UAV-aware local search.",
    ],
    flow: ["Arc variables", "Degree constraints", "Minimise travel", "Lazy subtour cuts", "Optimal tour"],
    pseudocode: `x[i, j] in {0, 1} for every arc
minimise  sum(truck_time[i][j] * x[i, j])
s.t.      sum_j x[i, j] = 1,  sum_j x[j, i] = 1
callback: for each subtour S without depot:
              add sum(x[i, j] for i, j in S) <= |S| - 1
return order_from(x)`,
    strengths: "Provably optimal for the truck alone and cheap for small instances; gives the drone search a strong starting route.",
    limitations: "Only the truck is optimised, not the truck–drone schedule. Skipped above 25 customers because the arc count exceeds the licence limit.",
  },
  {
    id: "mip",
    name: "Sortie-selection MIP",
    family: "Proposed",
    source: P,
    fn: "select_sorties_mip",
    role: "Chooses which (launch, customer, recovery) sorties to fly for a fixed truck order",
    inputs: "Truck order and candidate sortie templates with an estimated makespan improvement each.",
    outputs: "A pool of good sortie selections (best estimated benefit first).",
    steps: [
      "Keep the strongest candidates if the licence limit would be exceeded; drop depot launches.",
      "One binary variable per candidate sortie; maximise estimated improvement plus a small per-UAV bonus.",
      "Each customer is served by at most one sortie.",
      "A node used for launch or recovery must stay on the truck route (big-M = 2 × fleet size).",
      "At most |UAVs| sorties may be airborne over any route segment.",
      "Return up to the configured number of pool solutions for exact evaluation.",
    ],
    flow: ["Candidate sorties", "Binary selection", "Customer / node / fleet constraints", "Solution pool", "Exact evaluation"],
    pseudocode: `maximise  sum((gain[k] + bonus) * x[k])
s.t.      sum(x[k] for k serving c) <= 1           # each customer
          sum(x[k] using node v) + M * sum(x[k] serving v) <= M
          sum(x[k] covering segment p) <= num_uavs   # fleet
model.Params.PoolSearchMode = 2
return [selection(sol) for sol in pool]`,
    strengths: "Searches the candidate set exactly instead of greedily and returns several diverse selections.",
    limitations: "The objective uses estimated gains, not the exact makespan, which is why every pool solution is re-simulated and repaired.",
  },
  {
    id: "scheduler",
    name: "Parallel UAV scheduler + exact repair",
    family: "Proposed",
    source: P,
    fn: "gurobi_parallel_scheduler",
    role: "Turns a truck order into the best timed truck–UAV schedule",
    inputs: "Truck order, candidate window settings, candidate limit and insertion limit.",
    outputs: "Best simulation result (makespan, waits, sorties, activity log) and the chosen sortie templates.",
    steps: [
      "Run the no-Gurobi exact greedy parallel scheduler as the baseline.",
      "Generate candidate sorties and solve the sortie-selection MIP for a pool of selections.",
      "Simulate every pool selection with the event-based schedule simulator.",
      "Drop-descent: remove sorties that hurt the exact makespan.",
      "Greedily extend the best pool solution with sorties that help.",
      "Keep the MIP schedule only if it strictly beats the greedy baseline.",
    ],
    flow: ["Greedy baseline", "Sortie MIP pool", "Exact simulation", "Drop descent", "Greedy extension", "Best schedule"],
    pseudocode: `best = exact_greedy_parallel_scheduler(problem, order)
for selection in select_sorties_mip(problem, order, candidates):
    result = simulate_schedule(problem, order, selection)
    if result.valid:
        result = drop_descent(result)
        pool_best = better(pool_best, result)
pool_best = greedy_extend(pool_best)
return better(best, pool_best)`,
    strengths: "Combines an exact model for selection with an exact simulator for timing; cannot be worse than the greedy scheduler.",
    limitations: "Candidate windows bound which launch/recovery pairs are considered, so useful long sorties can be excluded on large instances.",
  },
  {
    id: "search",
    name: "Size-specific route search",
    family: "Proposed",
    source: P,
    fn: "gurobi_route_search",
    role: "Builds the labelled list of candidate truck orders",
    inputs: "Problem dictionary and customer group.",
    outputs: "Labelled orders (route_search, clarke_wright, insertion, nearest_neighbor, gurobi_tsp, gurobi_tsp_local_search) and a strategy name.",
    steps: [
      "8 and 25 customers: multi-start local search from Clarke–Wright, insertion and nearest-neighbour seeds (small_group_search).",
      "10 customers: micro genetic algorithm seeded by an exact truck TSP dynamic program (micro_ga_search_10).",
      "50 and 100 customers: memetic GA with tournament selection, order crossover, mixed mutation and elite polish (memetic_ga_search).",
      "Keep the simple construction seeds as extra candidates, since approximate fitness can mis-rank them.",
      "For n ≤ 25, add the Gurobi TSP tour and its local-search improvement.",
    ],
    flow: ["Group 8/10/25/50/100", "Local search / micro GA / memetic GA", "Construction seeds", "Gurobi TSP seeds (n ≤ 25)", "Candidate orders"],
    pseudocode: `if group in (8, 25):  order = small_group_search(problem, group)
elif group == 10:     order = micro_ga_search_10(problem)
else:                 order = memetic_ga_search(problem, group)
orders = [route_search, clarke_wright, insertion, nearest_neighbor]
if n <= 25 and (tsp := gurobi_truck_tsp_order(problem)):
    orders += [tsp, local_search_order(tsp)]
return orders, strategy`,
    strengths: "Search effort is matched to instance size; several independent seeds reduce dependence on one starting tour.",
    limitations: "Stochastic (fixed seed 42); approximate fitness ranking can differ from the final exact simulation.",
  },
  {
    id: "original-heuristic",
    name: "Original three-phase heuristic",
    family: "Original",
    source: "old/solve_mfstsp_heuristic.py",
    fn: "solve_mfstsp_heuristic",
    role: "Reference heuristic from the original paper code (archived results)",
    inputs: "Nodes, vehicles, travel data, cutoff time, driver/depot flags and endurance model.",
    outputs: "Objective, assignments, packages and waiting metrics.",
    steps: [
      "Phase 1 partitions customers and builds a truck TSP (mfstsp_heuristic_1_partition.py).",
      "Phase 2 assigns feasible UAV sorties (mfstsp_heuristic_2_asgn_uavs.py).",
      "Phase 3 solves timing and synchronisation with Gurobi (mfstsp_heuristic_3_timing.py).",
      "Try local shifts (local_search.py) and re-time.",
      "Keep improved feasible solutions until the time limit.",
    ],
    flow: ["Partition + truck TSP", "UAV assignment", "Gurobi timing", "Local shifts", "Best solution"],
    pseudocode: `while time_left:
    partition = phase1_partition_and_tsp(problem)
    assignments = phase2_assign_uavs(partition)
    schedule = phase3_gurobi_timing(assignments)
    if schedule.feasible:
        schedule = local_search_and_retime(schedule)
    keep_best(schedule)`,
    strengths: "Explicit mathematical timing constraints and clearly separated decisions.",
    limitations: "Decomposition can restrict the search. Archived runs use Etype 1 and a 5-second limit, unlike the proposed runs (Etype 3, 3,600 s).",
  },
  {
    id: "original-ip",
    name: "Original mixed-integer program",
    family: "Original",
    source: "old/solve_mfstsp_IP.py",
    fn: "solve_mfstsp_IP",
    role: "Reference mathematical model (archived results for 8-customer instances)",
    inputs: "Full node, vehicle and travel data plus model constraints.",
    outputs: "Incumbent objective, bound, assignments and solver status.",
    steps: [
      "Create truck routing and UAV assignment variables.",
      "Add service, routing, endurance and synchronisation constraints.",
      "Optimise with Gurobi under the time limit.",
      "Report the incumbent, its bound and whether optimality was proven.",
    ],
    flow: ["Full problem", "Variables + constraints", "Gurobi optimise", "Incumbent / bound"],
    pseudocode: `model = construct_mfstsp_model(problem)
add_routing_assignment_timing_constraints(model)
model.optimize(time_limit)
return objective, bound, assignments, status`,
    strengths: "Can certify optimality and provide bounds.",
    limitations: "Scales poorly, so it is only recorded for small instances. Not called by the current main.py.",
  },
];
