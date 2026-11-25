"""Roulette-wheel operator selection with segment-based weight updates (guide 9.1)."""

from __future__ import annotations

import random
from typing import Dict, List


class AdaptiveWeights:
    def __init__(self, names: List[str], reaction: float, initial: float = 1.0, floor: float = 0.05):
        self.names = list(names)
        self.weight: Dict[str, float] = {n: initial for n in names}
        self.score: Dict[str, float] = {n: 0.0 for n in names}
        self.uses: Dict[str, int] = {n: 0 for n in names}
        self.total_uses: Dict[str, int] = {n: 0 for n in names}
        self.reaction = reaction
        self.floor = floor

    def choose(self, rng: random.Random) -> str:
        total = sum(self.weight.values())
        x = rng.random() * total
        for n in self.names:
            x -= self.weight[n]
            if x <= 0:
                return n
        return self.names[-1]

    def reward(self, name: str, value: float) -> None:
        self.score[name] += value
        self.uses[name] += 1
        self.total_uses[name] += 1

    def end_segment(self) -> None:
        for n in self.names:
            if self.uses[n] > 0:
                avg = self.score[n] / self.uses[n]
                self.weight[n] = max(self.floor, (1 - self.reaction) * self.weight[n] + self.reaction * avg)
            self.score[n] = 0.0
            self.uses[n] = 0
