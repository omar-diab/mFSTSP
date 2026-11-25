"""UAV endurance, ported line for line from the paper's endurance_calculator.py.

give_endurance() returns the time [s] a UAV may spend between finishing its
launch at node i and starting its recovery at node k while serving customer j.
It includes hovering, which is how the paper limits waiting in the air.
"""

from __future__ import annotations

import math


def _pi(T, v_vert):
    return 0.8554 * T * (v_vert / 2.0 + math.sqrt((v_vert / 2.0) ** 2 + T / (0.3051) ** 2))


def _pp(T):
    return 0.3177 * (T ** 1.5)


def _ppar(v_air):
    return 0.0296 * (v_air ** 3)


def _thrust(m, v_air):  # Matternet M2, 1.5 kg empty weight in the paper's formula
    return math.sqrt(((1.5 + m) * 9.8 - 0.0279 * (v_air * math.cos(10 * math.pi / 180.0)) ** 2) ** 2
                     + (0.0296 * v_air ** 2) ** 2)


def give_endurance(problem, v: int, i: int, j: int, k: int, etype: int) -> float:
    uav = problem.uavs[v]
    legs = problem.uav_legs[v]
    p, q, r = uav.takeoff_speed, uav.cruise_speed, uav.landing_speed
    tt_ij, ft_ij, lt_ij = legs[i][j]
    tt_jk, ft_jk, lt_jk = legs[j][k]
    sj = problem.nodes[j].uav_service
    mj = problem.nodes[j].parcel_lbs * 0.453592  # kg
    E = uav.battery_joules

    minimum_time_required = tt_ij + ft_ij + lt_ij + sj + tt_jk + ft_jk + lt_jk

    if etype == 1:  # non-linear energy model
        T = _thrust(mj, 0)
        ea = tt_ij * (_pi(T, p) + _pp(T))
        T = _thrust(mj, q)
        eb = ft_ij * (_pi(T, 0) + _pp(T) + _ppar(q))
        T = _thrust(mj, 0)
        ec = lt_ij * (_pi(T, r) + _pp(T))
        T = _thrust(0, 0)
        ed = tt_jk * (_pi(T, p) + _pp(T))
        T = _thrust(0, q)
        ee = ft_jk * (_pi(T, 0) + _pp(T) + _ppar(q))
        T = _thrust(0, 0)
        ef = lt_jk * (_pi(T, r) + _pp(T))
        energy_left = E - (ea + eb + ec + ed + ee + ef)
        if energy_left < 0:
            return -1.0
        T = _thrust(0, 0)
        p_hover = _pi(T, 0) + _pp(T)
        return minimum_time_required + energy_left / p_hover

    if etype == 2:  # linear energy model
        if q == 31.2928:
            A, B = 24.2368, 1391.9916
        elif q == 15.6464:
            A, B = 210.8011, 181.2141
        else:
            raise ValueError("Linear endurance model needs cruise speed 31.2928 or 15.6464 m/s")
        e_ij = (tt_ij + ft_ij + lt_ij) * (A * mj + B)
        e_jk = (tt_jk + ft_jk + lt_jk) * B
        energy_left = E - (e_ij + e_jk)
        if energy_left < 0:
            return -1.0
        return minimum_time_required + energy_left / B

    if etype == 3:  # fixed flight time
        return {291094: 700.0, 562990: 1400.0, 457503: 350.0, 904033: 700.0}[int(E)]

    if etype == 4:  # unlimited
        return 24 * 3600.0

    raise ValueError("Unsupported endurance type %r (5 = distance limit is not implemented)" % etype)
