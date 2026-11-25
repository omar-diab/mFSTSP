"""Problem data for the mFSTSP, in the units and conventions of Murray & Raj (2019).

Node 0 is the depot. The truck route starts at the depot and ends at the
depot again; the paper calls that final copy node c+1. In this package the
final copy keeps id 0 and is identified by its position (the last one).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Customer:
    node_id: int
    lat: float
    lon: float
    alt: float
    parcel_lbs: float
    truck_service: float  # sigma_j  [s]
    uav_service: float    # sigma'_j [s]


@dataclass(frozen=True)
class UAV:
    uav_id: int
    takeoff_speed: float
    cruise_speed: float
    landing_speed: float
    yaw_rate_deg: float
    cruise_alt: float
    capacity_lbs: float
    launch_time: float     # s_L [s]
    recovery_time: float   # s_R [s]
    service_time: float
    battery_joules: float
    flight_range: str


@dataclass(frozen=True)
class Truck:
    vehicle_id: int
    service_time: float


@dataclass
class ProblemInstance:
    name: str
    vehicle_file_id: int
    depot_id: int
    nodes: Dict[int, Customer]            # includes the depot (id 0)
    customers: List[int]
    truck: Truck
    uavs: Dict[int, UAV]
    truck_time: List[List[float]]         # tau[i][j], indexed by node id
    uav_time: Dict[int, List[List[float]]]  # tau'[v][i][j] (takeoff + fly + land)
    uav_legs: Dict[int, List[List[Tuple[float, float, float]]]]  # (takeoff, fly, land) per leg
    endurance_type: int = 1               # Etype of the paper (1 = non-linear energy model)
    require_truck_at_depot: bool = True
    require_driver: bool = True
    _endurance_cache: Dict[Tuple[int, int, int, int], float] = field(default_factory=dict, repr=False)

    @property
    def n_customers(self) -> int:
        return len(self.customers)

    def uav_ids(self) -> List[int]:
        return sorted(self.uavs)

    def can_carry(self, uav_id: int, customer: int) -> bool:
        return self.nodes[customer].parcel_lbs <= self.uavs[uav_id].capacity_lbs

    def endurance(self, uav_id: int, i: int, j: int, k: int) -> float:
        """Maximum time [s] between launch completion at i and recovery start at k.

        Matches eee[v][i][j][k] of the paper (k = depot copy uses node 0).
        Returns -1 when the battery cannot even cover the minimum flight.
        """
        key = (uav_id, i, j, k)
        value = self._endurance_cache.get(key)
        if value is None:
            from .endurance import give_endurance
            value = give_endurance(self, uav_id, i, j, k, self.endurance_type)
            self._endurance_cache[key] = value
        return value

    def sortie_flight_time(self, uav_id: int, i: int, j: int, k: int) -> float:
        """tau'_{ij} + sigma'_j + tau'_{jk}: the minimum airborne time of a sortie."""
        t = self.uav_time[uav_id]
        return t[i][j] + self.nodes[j].uav_service + t[j][k]

    def sortie_possible(self, uav_id: int, i: int, j: int, k: int) -> bool:
        """The paper's set P: payload fits and the minimum flight fits the endurance."""
        if j == i or j == k or i == k and i != self.depot_id:
            return False
        if not self.can_carry(uav_id, j):
            return False
        return self.sortie_flight_time(uav_id, i, j, k) <= self.endurance(uav_id, i, j, k)
