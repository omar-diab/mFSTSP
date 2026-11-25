"""Solution representation: an ordered truck route plus a list of UAV sorties."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Sortie:
    """One UAV delivery: launch at a truck node, serve one customer, land at a later truck node.

    The depot is node 0. A launch at node 0 means the start of the route; a
    recovery at node 0 means the end of the route (the paper's node c+1).
    """
    uav_id: int
    launch_node: int
    customer_id: int
    recovery_node: int


@dataclass
class SortieTiming:
    sortie: Sortie
    launch_start: float
    launch_done: float      # UAV leaves the truck (hat t'_{v,i})
    ready_at_recovery: float  # UAV arrives above the recovery node
    recovery_start: float
    recovery_done: float    # check t'_{v,k}
    hover: float            # time spent waiting in the air for the truck/driver
    airborne: float         # recovery_start - launch_done (limited by the endurance)
    endurance: float


@dataclass
class ScheduleResult:
    feasible: bool
    makespan: float
    policy: Tuple[str, ...] = ()
    truck_arrival: List[float] = field(default_factory=list)    # by route position
    truck_departure: List[float] = field(default_factory=list)
    operations: List[Tuple[int, str, int, float, float]] = field(default_factory=list)
    # (position, kind 'L'/'R'/'S', uav id or customer, start, end)
    sorties: List[SortieTiming] = field(default_factory=list)
    truck_waiting: float = 0.0   # truck idle at stops waiting for UAVs
    uav_waiting: float = 0.0     # UAV hover time
    violations: List[str] = field(default_factory=list)
    failed_sortie: Optional[int] = None   # index of the sortie that broke the endurance (internal)
    excess: float = 0.0                   # how far that sortie was over its endurance (internal)
    flags: tuple = (frozenset(), frozenset(), {})  # (late launches, urgent recoveries, launch delays)


@dataclass
class Solution:
    route: List[int]                    # [0, ..., 0]
    sorties: List[Sortie]
    schedule: Optional[ScheduleResult] = None

    @property
    def objective(self) -> float:
        return self.schedule.makespan if self.schedule and self.schedule.feasible else float("inf")

    @property
    def feasible(self) -> bool:
        return bool(self.schedule and self.schedule.feasible)

    def copy(self) -> "Solution":
        return Solution(list(self.route), list(self.sorties), self.schedule)

    def uav_customers(self) -> List[int]:
        return [s.customer_id for s in self.sorties]

    def truck_customers(self) -> List[int]:
        return self.route[1:-1]

    def to_dict(self) -> Dict:
        return {
            "truck_route": list(self.route),
            "sorties": [[s.uav_id, s.launch_node, s.customer_id, s.recovery_node] for s in self.sorties],
        }
