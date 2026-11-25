"""ALNS settings (guide section 12). Every value can be overridden from a JSON file."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Dict, Optional


@dataclass
class ALNSConfig:
    random_seed: int = 1
    # Stopping: whichever comes first. time_limit_seconds=None -> use time_limit_by_size.
    max_iterations: int = 100000
    time_limit_seconds: Optional[float] = None
    time_limit_by_size: Dict[str, float] = field(default_factory=lambda: {
        "8": 5.0, "10": 5.0, "25": 10.0, "50": 20.0, "100": 45.0})

    # Destroy size: q random in [min_removal, max(min_removal, max_removal_fraction * n)], capped.
    min_removal: int = 1
    max_removal_fraction: float = 0.3
    max_removal_cap: int = 15

    # Adaptive operator weights (Ropke & Pisinger style).
    reaction_factor: float = 0.1
    segment_length: int = 50
    reward_best: float = 33.0
    reward_improve: float = 15.0
    reward_accept: float = 5.0
    reward_reject: float = 0.0

    # Simulated annealing: a move this much worse (fraction of the start makespan)
    # is accepted with probability start_accept_probability at the beginning.
    start_worsening_fraction: float = 0.03
    start_accept_probability: float = 0.5
    end_temperature_ratio: float = 0.002

    # Insertion: how many cheaply ranked options get the full schedule evaluation, by customer count.
    insertion_full_evaluations_by_size: Dict[str, int] = field(default_factory=lambda: {
        "8": 20, "10": 20, "25": 10, "50": 6, "100": 6})
    insertion_full_evaluations: Optional[int] = None  # set to override the table above
    max_sortie_span: int = 8          # recovery at most this many truck stops after launch
    # Up to this many customers, keep sortie options that would hover too long (the evaluator
    # can hold the launch back); for larger problems drop them to save time.
    hold_launch_options_up_to: int = 25
    regret_k: int = 2

    # Local search after repair: run on every new best, and every N iterations.
    local_search_frequency: int = 25
    local_search_max_passes: int = 2

    # Schedule policies tried while searching: "all" (36) up to this many customers, else "fast" (5).
    # The final reported schedule always uses all 36.
    all_policies_up_to: int = 10
    search_policies: str = "fast"   # "fast", "all", or "auto" (all up to all_policies_up_to customers)
    # Endurance repairs (launch last / recover first / hold launch) tried per policy while
    # searching, by customer count. The final schedule always gets the full 4 per sortie.
    search_endurance_repairs_by_size: Dict[str, int] = field(default_factory=lambda: {
        "8": 40, "10": 40, "25": 20, "50": 3, "100": 3})

    # Paper model options.
    endurance_model: int = 1          # Etype (1 = non-linear energy model, as in every paper run)
    require_driver: bool = True
    require_truck_at_depot: bool = True

    def time_limit(self, n_customers: int) -> float:
        if self.time_limit_seconds is not None:
            return float(self.time_limit_seconds)
        sizes = sorted(int(k) for k in self.time_limit_by_size)
        key = next((s for s in sizes if n_customers <= s), sizes[-1])
        return float(self.time_limit_by_size[str(key)])

    def full_evaluations(self, n_customers: int) -> int:
        if self.insertion_full_evaluations is not None:
            return int(self.insertion_full_evaluations)
        sizes = sorted(int(k) for k in self.insertion_full_evaluations_by_size)
        key = next((s for s in sizes if n_customers <= s), sizes[-1])
        return int(self.insertion_full_evaluations_by_size[str(key)])

    def endurance_repairs(self, n_customers: int) -> int:
        sizes = sorted(int(k) for k in self.search_endurance_repairs_by_size)
        key = next((s for s in sizes if n_customers <= s), sizes[-1])
        return int(self.search_endurance_repairs_by_size[str(key)])

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_json(cls, path) -> "ALNSConfig":
        with open(path) as f:
            data = json.load(f)
        cfg = cls()
        for k, v in data.items():
            if not hasattr(cfg, k):
                raise KeyError("Unknown ALNS setting: %s" % k)
            setattr(cfg, k, v)
        return cfg
