"""The ALNS main loop (guide section 4)."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..data.models import ProblemInstance
from ..construction.initial_solution import construct_initial_solution
from ..operators.destroy import DESTROY_OPERATORS
from ..operators.insertion import Evaluator, remove_customers
from ..operators.local_search import improve
from ..operators.repair import REPAIR_OPERATORS
from ..scheduling.evaluator import ALL_POLICIES, FAST_POLICIES, evaluate
from ..solution.models import Solution
from .acceptance import SimulatedAnnealing
from .adaptive_weights import AdaptiveWeights
from .config import ALNSConfig

EPS = 1e-6


@dataclass
class ALNSResult:
    best: Solution
    initial_objective: float
    iterations: int
    runtime: float
    evaluations: int
    history: List[Dict] = field(default_factory=list)          # every new best: time, iteration, makespan
    destroy_stats: Dict[str, Dict] = field(default_factory=dict)
    repair_stats: Dict[str, Dict] = field(default_factory=dict)


def _detailed(ev: Evaluator, sol: Solution) -> Solution:
    """Attach the full timing of the solution (needed by wait-based destroy operators)."""
    sol.schedule = evaluate(ev.instance, sol.route, sol.sorties, (sol.schedule.policy,), detailed=True,
                            max_repairs=ev.max_repairs)
    if not sol.schedule.feasible:  # should not happen; fall back to the search policies
        sol.schedule = evaluate(ev.instance, sol.route, sol.sorties, ev.policies, detailed=True,
                                max_repairs=ev.max_repairs)
    return sol


def solve_alns(instance: ProblemInstance, config: Optional[ALNSConfig] = None, seed: Optional[int] = None,
               on_improvement=None) -> ALNSResult:
    cfg = config or ALNSConfig()
    rng = random.Random(cfg.random_seed if seed is None else seed)
    start = time.time()
    time_limit = cfg.time_limit(instance.n_customers)
    deadline = start + time_limit

    mode = cfg.search_policies
    if mode == "auto":
        mode = "all" if instance.n_customers <= cfg.all_policies_up_to else "fast"
    policies = ALL_POLICIES if mode == "all" else FAST_POLICIES
    ev = Evaluator(instance, policies, cfg.endurance_repairs(instance.n_customers))

    current = construct_initial_solution(instance, ev, cfg, rng)
    initial_objective = current.objective
    current = _detailed(ev, current)
    best = current.copy()
    history = [{"time": round(time.time() - start, 3), "iteration": 0, "makespan": best.objective}]
    if on_improvement:
        on_improvement(history[-1])

    destroy_w = AdaptiveWeights(list(DESTROY_OPERATORS), cfg.reaction_factor)
    repair_w = AdaptiveWeights(list(REPAIR_OPERATORS), cfg.reaction_factor)
    sa = SimulatedAnnealing(current.objective, cfg.start_worsening_fraction, cfg.start_accept_probability,
                            cfg.end_temperature_ratio)

    n = instance.n_customers
    q_max = max(cfg.min_removal, min(cfg.max_removal_cap, int(round(cfg.max_removal_fraction * n))))
    it = 0
    while it < cfg.max_iterations and time.time() < deadline:
        it += 1
        d_name = destroy_w.choose(rng)
        r_name = repair_w.choose(rng)
        q = rng.randint(cfg.min_removal, q_max)

        chosen, hints = DESTROY_OPERATORS[d_name](instance, current, q, rng)
        route, sorties, removed = remove_customers(current.route, current.sorties, chosen)
        partial = Solution(route, sorties)
        cand = REPAIR_OPERATORS[r_name](ev, partial, removed, hints, cfg, rng)

        outcome = "reject"
        if cand is not None:
            cand = ev.full(cand)
            if cand.feasible and cfg.local_search_frequency and it % cfg.local_search_frequency == 0:
                cand = improve(ev, cand, cfg, rng, deadline)
        if cand is not None and cand.feasible:
            if cand.objective < best.objective - EPS:
                if cfg.local_search_frequency:
                    cand = improve(ev, cand, cfg, rng, deadline)
                current = _detailed(ev, cand)
                best = current.copy()
                outcome = "best"
                history.append({"time": round(time.time() - start, 3), "iteration": it,
                                "makespan": best.objective})
                if on_improvement:
                    on_improvement(history[-1])
            elif cand.objective < current.objective - EPS:
                current = _detailed(ev, cand)
                outcome = "improve"
            elif sa.accept(cand.objective, current.objective, rng):
                current = _detailed(ev, cand)
                outcome = "accept"
        reward = {"best": cfg.reward_best, "improve": cfg.reward_improve,
                  "accept": cfg.reward_accept, "reject": cfg.reward_reject}[outcome]
        destroy_w.reward(d_name, reward)
        repair_w.reward(r_name, reward)

        if it % cfg.segment_length == 0:
            destroy_w.end_segment()
            repair_w.end_segment()
        sa.update(max((time.time() - start) / time_limit, it / cfg.max_iterations))

    best = ev.final(best)  # best schedule over every policy, with full timing
    runtime = time.time() - start
    return ALNSResult(
        best=best, initial_objective=initial_objective, iterations=it, runtime=runtime,
        evaluations=ev.calls, history=history,
        destroy_stats={k: {"weight": round(destroy_w.weight[k], 3), "uses": destroy_w.total_uses[k]}
                       for k in destroy_w.names},
        repair_stats={k: {"weight": round(repair_w.weight[k], 3), "uses": repair_w.total_uses[k]}
                      for k in repair_w.names},
    )
