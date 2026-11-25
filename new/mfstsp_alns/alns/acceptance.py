"""Simulated-annealing acceptance (guide 9.2). Infeasible candidates are never accepted."""

from __future__ import annotations

import math
import random


class SimulatedAnnealing:
    def __init__(self, start_objective: float, worsening_fraction: float, accept_probability: float,
                 end_ratio: float):
        # exp(-delta / T0) = p  for  delta = worsening_fraction * f0  ->  scale-free start temperature
        delta = max(1e-9, worsening_fraction * start_objective)
        self.t0 = -delta / math.log(accept_probability)
        self.t_end = self.t0 * end_ratio
        self.temperature = self.t0

    def update(self, progress: float) -> None:
        """Geometric cooling over the run: progress goes from 0 (start) to 1 (time/iteration limit)."""
        progress = min(1.0, max(0.0, progress))
        self.temperature = self.t0 * (self.t_end / self.t0) ** progress

    def accept(self, f_new: float, f_current: float, rng: random.Random) -> bool:
        if f_new <= f_current:
            return True
        if self.temperature <= 0:
            return False
        return rng.random() < math.exp(-(f_new - f_current) / self.temperature)
