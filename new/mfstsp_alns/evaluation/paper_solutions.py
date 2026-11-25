"""Read the truck route and sorties from the paper's tbl_solutions_*.csv files.

Used to check our evaluator: re-timing the paper's own plans must give
feasible schedules with (close to) the paper's makespan.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from ..solution.models import Sortie

_TRAVEL = re.compile(r"Travel from node (\d+) to node (\d+)")


def read_paper_solution(path, n_customers: int) -> Optional[Dict]:
    """Return {'ofv', 'route', 'sorties'} for the first solution in the file."""
    path = Path(path)
    if not path.exists():
        return None
    lines = path.read_text().splitlines()
    depot_copy = n_customers + 1
    ofv = None
    rows = []
    started = False
    for line in lines:
        if line.startswith("Objective Function Value"):
            if ofv is not None:
                break  # only the first solution of an appended file
            ofv = float(line.split(":")[1])
            continue
        if line.startswith("vehicleID"):
            started = True
            continue
        if started and line.strip():
            if line.startswith("problemName"):
                break
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 9 and parts[0].isdigit():
                rows.append(parts)
    if ofv is None:
        return None

    def norm(n: int) -> int:
        return 0 if n == depot_copy else n

    route = [0]
    for r in rows:
        if r[1] == "Truck":
            m = _TRAVEL.search(r[7])
            if m:
                route.append(norm(int(m.group(2))))
    if route[-1] != 0:
        route.append(0)

    sorties: List[Sortie] = []
    current: Dict[int, Dict] = {}
    for r in rows:
        if r[1] != "UAV":
            continue
        v = int(r[0])
        desc = r[7]
        if desc.startswith("Prepare to launch"):
            current[v] = {"launch": norm(int(r[4]))}
        elif desc.startswith("Fly to UAV customer"):
            current.setdefault(v, {})["customer"] = int(r[6])
        elif desc.startswith("Recovered by truck") or desc.startswith("Recovered at depot"):
            c = current.pop(v, {})
            sorties.append(Sortie(v, c.get("launch", 0), c["customer"], norm(int(r[4]))))
    return {"ofv": ofv, "route": route, "sorties": sorties}
