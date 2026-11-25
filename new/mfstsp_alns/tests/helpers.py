"""Tiny hand-built instances with times that are easy to check by hand."""

from mfstsp_alns.data.models import Customer, ProblemInstance, Truck, UAV


def tiny_instance(n_customers=3, n_uavs=1, truck_leg=100.0, uav_leg=50.0, endurance_type=4,
                  battery=562990.0, launch=60.0, recovery=30.0, truck_service=30.0, uav_service=60.0,
                  parcel=1.0, require_driver=True):
    """Depot 0 and customers 1..n. Every truck leg takes truck_leg s, every UAV leg uav_leg s.

    endurance_type 4 = unlimited, 3 = fixed (battery 562990 J -> 1400 s).
    """
    n = n_customers + 1
    nodes = {0: Customer(0, 0.0, 0.0, 0.0, -1.0, truck_service, uav_service)}
    for i in range(1, n):
        nodes[i] = Customer(i, 0.0, 0.0, 0.0, parcel, truck_service, uav_service)
    truck_time = [[0.0 if i == j else truck_leg for j in range(n)] for i in range(n)]
    uavs, uav_time, uav_legs = {}, {}, {}
    for k in range(n_uavs):
        vid = 2 + k
        uavs[vid] = UAV(vid, 15.6464, 31.2928, 7.8232, 360.0, 50.0, 5.0, launch, recovery, uav_service,
                        battery, "high")
        uav_time[vid] = [[0.0 if i == j else uav_leg for j in range(n)] for i in range(n)]
        uav_legs[vid] = [[(0.0, 0.0, 0.0) if i == j else (0.0, uav_leg, 0.0) for j in range(n)] for i in range(n)]
    return ProblemInstance("tiny", 0, 0, nodes, list(range(1, n)), Truck(1, truck_service), uavs,
                           truck_time, uav_time, uav_legs, endurance_type=endurance_type,
                           require_driver=require_driver)
