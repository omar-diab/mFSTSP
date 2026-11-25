"""Read a benchmark instance exactly like the paper's main.py (readData)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Tuple

from . import paper_distance
from .models import Customer, ProblemInstance, Truck, UAV

TYPE_TRUCK = 1
TYPE_UAV = 2


def _rows(path: Path, comment: str = "%") -> List[List[str]]:
    rows = []
    with open(path) as f:
        for line in f:
            if line.startswith(comment) or not line.strip():
                continue
            rows.append([c.strip() for c in line.rstrip().split(",") if c.strip() != ""])
    return rows


def load_instance(problems_dir, problem_name: str, vehicle_file_id: int, num_uavs: int,
                  endurance_type: int = 1, require_truck_at_depot: bool = True,
                  require_driver: bool = True) -> ProblemInstance:
    problems_dir = Path(problems_dir)

    # Vehicles: the truck plus the first `num_uavs` UAVs of the file (as in the paper).
    truck = None
    uavs: Dict[int, UAV] = {}
    first_uav_service = 0.0
    for r in _rows(problems_dir / ("tbl_vehicles_%d.csv" % vehicle_file_id)):
        vid, vtype = int(r[0]), int(r[1])
        if vtype == TYPE_TRUCK:
            truck = Truck(vid, float(r[10]))
        elif vtype == TYPE_UAV and len(uavs) < num_uavs:
            uavs[vid] = UAV(vid, float(r[2]), float(r[3]), float(r[4]), float(r[5]), float(r[6]),
                            float(r[7]), float(r[8]), float(r[9]), float(r[10]), float(r[11]), r[12])
            if len(uavs) == 1:
                first_uav_service = float(r[10])
    if truck is None:
        raise ValueError("No truck in vehicle file %d" % vehicle_file_id)
    if len(uavs) < num_uavs:
        raise ValueError("Vehicle file %d has only %d UAVs" % (vehicle_file_id, len(uavs)))

    nodes: Dict[int, Customer] = {}
    customers: List[int] = []
    for r in _rows(problems_dir / problem_name / "tbl_locations.csv"):
        nid, ntype = int(r[0]), int(r[1])
        nodes[nid] = Customer(nid, float(r[2]), float(r[3]), float(r[4]), float(r[5]),
                              truck.service_time, first_uav_service if num_uavs > 0 else 0.0)
        if ntype == 1:
            customers.append(nid)
    if sorted(nodes) != list(range(len(nodes))):
        raise ValueError("Node ids must be 0..n")
    n = len(nodes)

    truck_time = [[0.0] * n for _ in range(n)]
    seen = 0
    for r in _rows(problems_dir / problem_name / "tbl_truck_travel_data_PG.csv"):
        i, j = int(r[0]), int(r[1])
        if i < n and j < n:
            truck_time[i][j] = float(r[2])
            seen += 1
    if seen < n * (n - 1):
        raise ValueError("Truck travel matrix is incomplete (%d of %d arcs)" % (seen, n * (n - 1)))

    uav_time: Dict[int, List[List[float]]] = {}
    uav_legs: Dict[int, List[List[Tuple[float, float, float]]]] = {}
    cache: Dict[tuple, Tuple[List[List[float]], list]] = {}
    for vid, u in uavs.items():
        sig = (u.takeoff_speed, u.cruise_speed, u.landing_speed, u.yaw_rate_deg, u.cruise_alt)
        if sig not in cache:
            tt = [[0.0] * n for _ in range(n)]
            legs = [[(0.0, 0.0, 0.0)] * n for _ in range(n)]
            for i in range(n):
                a = nodes[i]
                for j in range(n):
                    if i == j:
                        continue
                    b = nodes[j]
                    res = paper_distance.calcMultirotorTravelTime(
                        u.takeoff_speed, u.cruise_speed, u.landing_speed, u.yaw_rate_deg,
                        a.alt, u.cruise_alt, b.alt, a.lat, a.lon, b.lat, b.lon, -361, -361)
                    legs[i][j] = (res[0], res[1], res[2])
                    tt[i][j] = res[3]
            cache[sig] = (tt, legs)
        uav_time[vid], uav_legs[vid] = cache[sig]

    return ProblemInstance(
        name=problem_name, vehicle_file_id=vehicle_file_id, depot_id=0, nodes=nodes,
        customers=customers, truck=truck, uavs=uavs, truck_time=truck_time,
        uav_time=uav_time, uav_legs=uav_legs, endurance_type=endurance_type,
        require_truck_at_depot=require_truck_at_depot, require_driver=require_driver)
