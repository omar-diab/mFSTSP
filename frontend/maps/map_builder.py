from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

# =============================================================================
# Paths
# =============================================================================

MAPS_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = MAPS_DIR.parent
PROJECT_DIR = FRONTEND_DIR.parent

GENERATED_DIR = MAPS_DIR / "generated"
GENERATED_DIR.mkdir(exist_ok=True)

PERFORMANCE_FILE = PROJECT_DIR / "performance_summary.csv"

OUR_COLUMNS = [
    "problemName",
    "vehicleFileID",
    "cutoffTime",
    "problemType",
    "problemTypeString",
    "numUAVs",
    "numTrucks",
    "requireTruckAtDepot",
    "requireDriver",
    "Etype",
    "ITER",
    "runString",
    "numCustomers",
    "timestamp",
    "ofv",
    "bestBound",
    "totalTime",
    "isOptimal",
    "numUAVcust",
    "numTruckCust",
    "waitingTruck",
    "waitingUAV",
]


# =============================================================================
# Data container
# =============================================================================

@dataclass
class BestProblemMapData:
    scenario: int
    problem_name: str
    vehicle_file_id: int
    num_uavs: int
    ofv: float | None
    total_time: float | None
    num_uav_customers: int | None
    num_truck_customers: int | None
    summary_file: Path | None
    truck_route: list[Any]
    uav_sorties: list[dict[str, Any]]
    coordinates: dict[Any, tuple[float, float]]
    coordinate_source: Path | None
    route_status: str


# =============================================================================
# Generic helpers
# =============================================================================

def normalize_node_id(value: Any):
    try:
        number = float(str(value).strip())
        if number.is_integer():
            return int(number)
        return number
    except Exception:
        return str(value).strip()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return default


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def parse_literal(text: str, default):
    try:
        return ast.literal_eval(text.strip())
    except Exception:
        return default


def problem_dir(problem_name: str) -> Path:
    return PROJECT_DIR / "Problems" / str(problem_name)


# =============================================================================
# Choose the best problem for a scenario
# =============================================================================

def load_performance_for_scenario(scenario: int) -> pd.DataFrame:
    if not PERFORMANCE_FILE.exists():
        raise FileNotFoundError(f"Missing performance summary: {PERFORMANCE_FILE}")

    df = pd.read_csv(PERFORMANCE_FILE, header=None, names=OUR_COLUMNS)

    numeric_cols = [
        "vehicleFileID",
        "problemType",
        "numUAVs",
        "numCustomers",
        "ofv",
        "totalTime",
        "numUAVcust",
        "numTruckCust",
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df[
        (df["problemType"] == 2)
        & (df["numCustomers"] == scenario)
    ].copy()

    if df.empty:
        raise ValueError(f"No heuristic rows found for scenario {scenario}.")

    # Repeated runs can exist; keep best OFV for each problem.
    df = df.sort_values(["problemName", "ofv"], ascending=[True, True], na_position="last")
    df = df.drop_duplicates(subset=["problemName"], keep="first")

    return df


def choose_best_problem_row(scenario_df: pd.DataFrame) -> pd.Series:
    if scenario_df.empty:
        raise ValueError("Scenario dataframe is empty.")
    return scenario_df.loc[scenario_df["ofv"].idxmin()]


# =============================================================================
# Read the NO-GUROBI simple solution summary file
# =============================================================================

def find_simple_solution_summary_file(best_row: pd.Series) -> Path | None:
    problem_name = str(best_row["problemName"])
    pdir = problem_dir(problem_name)

    vehicle_file_id = safe_int(best_row.get("vehicleFileID"), 101)
    num_uavs = safe_int(best_row.get("numUAVs"), 3)

    exact = pdir / f"tbl_solutions_{vehicle_file_id}_{num_uavs}_NoGurobiHeuristic.csv"
    if exact.exists():
        return exact

    candidates = sorted(pdir.glob("tbl_solutions_*_*_NoGurobiHeuristic.csv"))
    if candidates:
        return candidates[-1]

    return None


def extract_single_line_after_label(text: str, label: str) -> str | None:
    pattern = rf"{re.escape(label)}:\s*\n([^\n]+)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def extract_block_after_label(text: str, label: str, stop_labels: list[str]) -> str | None:
    stop_pattern = "|".join(re.escape(stop) for stop in stop_labels)
    pattern = rf"{re.escape(label)}:\s*\n([\s\S]*?)(?=\n(?:{stop_pattern}):|\Z)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def parse_truck_route(text: str) -> list[Any]:
    route_line = extract_single_line_after_label(text, "Truck Route")
    if not route_line:
        return []

    parsed = parse_literal(route_line, [])
    if not isinstance(parsed, (list, tuple)):
        return []

    return [normalize_node_id(node) for node in parsed]


def parse_uav_sorties(text: str) -> list[dict[str, Any]]:
    block = extract_block_after_label(
        text,
        "UAV Sorties",
        stop_labels=["Activity Log"],
    )

    if not block:
        return []

    sorties: list[dict[str, Any]] = []

    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue

        parsed = parse_literal(line, None)
        if isinstance(parsed, dict):
            sorties.append(parsed)

    return sorties


def load_route_details_from_summary(summary_file: Path | None) -> tuple[list[Any], list[dict[str, Any]], str]:
    if summary_file is None or not summary_file.exists():
        return [], [], "summary_file_not_found"

    text = summary_file.read_text(encoding="utf-8", errors="ignore")

    truck_route = parse_truck_route(text)
    uav_sorties = parse_uav_sorties(text)

    if truck_route and uav_sorties:
        return truck_route, uav_sorties, "truck_route_and_uav_sorties_found"
    if truck_route:
        return truck_route, uav_sorties, "truck_route_found_uav_sorties_empty"
    if uav_sorties:
        return truck_route, uav_sorties, "uav_sorties_found_truck_route_empty"

    return truck_route, uav_sorties, "summary_file_found_but_route_sections_not_parsed"


# =============================================================================
# Coordinates from tbl_locations.csv
# =============================================================================

def load_coordinates(problem_name: str) -> tuple[dict[Any, tuple[float, float]], Path | None]:
    locations_file = problem_dir(problem_name) / "tbl_locations.csv"

    if not locations_file.exists():
        return {}, None

    df = pd.read_csv(locations_file)
    df.columns = df.columns.astype(str).str.strip()

    # Your project uses these headers:
    #   % nodeID, nodeType, latDeg, lonDeg, altMeters, parcelWtLbs
    node_col = None
    lat_col = None
    lon_col = None

    for col in df.columns:
        normalized = col.strip().lower().replace("%", "").strip()
        if normalized == "nodeid":
            node_col = col
        elif normalized == "latdeg":
            lat_col = col
        elif normalized == "londeg":
            lon_col = col

    if node_col is None or lat_col is None or lon_col is None:
        return {}, locations_file

    coords: dict[Any, tuple[float, float]] = {}

    for _, row in df.iterrows():
        try:
            node_id = normalize_node_id(row[node_col])
            lon = float(row[lon_col])
            lat = float(row[lat_col])
            coords[node_id] = (lon, lat)
        except Exception:
            continue

    return coords, locations_file


# =============================================================================
# Build data for one scenario
# =============================================================================

def build_best_problem_map_data(scenario: int) -> BestProblemMapData:
    scenario_df = load_performance_for_scenario(scenario)
    best_row = choose_best_problem_row(scenario_df)

    problem_name = str(best_row["problemName"])
    vehicle_file_id = safe_int(best_row.get("vehicleFileID"), 101)
    num_uavs = safe_int(best_row.get("numUAVs"), 3)

    summary_file = find_simple_solution_summary_file(best_row)
    truck_route, uav_sorties, route_status = load_route_details_from_summary(summary_file)

    coordinates, coordinate_source = load_coordinates(problem_name)

    return BestProblemMapData(
        scenario=scenario,
        problem_name=problem_name,
        vehicle_file_id=vehicle_file_id,
        num_uavs=num_uavs,
        ofv=safe_float(best_row.get("ofv")),
        total_time=safe_float(best_row.get("totalTime")),
        num_uav_customers=safe_int(best_row.get("numUAVcust"), 0),
        num_truck_customers=safe_int(best_row.get("numTruckCust"), 0),
        summary_file=summary_file,
        truck_route=truck_route,
        uav_sorties=uav_sorties,
        coordinates=coordinates,
        coordinate_source=coordinate_source,
        route_status=route_status,
    )


# =============================================================================
# Map drawing
# =============================================================================

def get_sortie_node(sortie: dict[str, Any], *keys: str):
    for key in keys:
        if key in sortie:
            return normalize_node_id(sortie[key])
    return None


def draw_best_problem_map(data: BestProblemMapData) -> tuple[Path, Path]:
    output_png = GENERATED_DIR / f"scenario_{data.scenario}_best_map.png"
    output_json = GENERATED_DIR / f"scenario_{data.scenario}_best_map.json"

    coords = data.coordinates

    fig, ax = plt.subplots(figsize=(13, 9))

    # Draw all points first.
    for node_id, (x, y) in coords.items():
        ax.scatter([x], [y], s=48, color="#6b7280", zorder=2)
        ax.text(x, y, f" {node_id}", fontsize=8, ha="left", va="bottom")

    # Depot
    depot = 0 if 0 in coords else None
    if depot is not None:
        x, y = coords[depot]
        ax.scatter([x], [y], marker="*", s=380, color="#ef4444", edgecolor="black", linewidth=0.7, zorder=6, label="Depot")

    # Truck route
    truck_line_drawn = False
    truck_route_nodes = [node for node in data.truck_route if node in coords]

    if len(truck_route_nodes) >= 2:
        xs = [coords[node][0] for node in truck_route_nodes]
        ys = [coords[node][1] for node in truck_route_nodes]
        ax.plot(
            xs,
            ys,
            linewidth=2.8,
            color="#2563eb",
            marker="o",
            markersize=4.5,
            zorder=4,
            label="Truck route",
        )
        truck_line_drawn = True

    # Highlight truck-served route nodes
    truck_nodes = set(truck_route_nodes)
    for node in truck_nodes:
        if node == depot:
            continue
        x, y = coords[node]
        ax.scatter([x], [y], s=82, color="#10b981", edgecolor="black", linewidth=0.4, zorder=5)

    # UAV sorties
    uav_line_count = 0
    uav_customers = set()

    for sortie in data.uav_sorties:
        launch = get_sortie_node(sortie, "launch", "launch_node")
        customer = get_sortie_node(sortie, "customer", "customer_node")
        recovery = get_sortie_node(sortie, "recovery", "recovery_node")

        if launch not in coords or customer not in coords or recovery not in coords:
            continue

        uav_customers.add(customer)

        x1, y1 = coords[launch]
        x2, y2 = coords[customer]
        x3, y3 = coords[recovery]

        ax.plot([x1, x2], [y1, y2], linestyle="--", linewidth=1.8, color="#f59e0b", zorder=5)
        ax.plot([x2, x3], [y2, y3], linestyle="--", linewidth=1.8, color="#f59e0b", zorder=5)

        uav_line_count += 1

    if uav_line_count > 0:
        ax.plot([], [], linestyle="--", linewidth=1.8, color="#f59e0b", label="UAV sortie")

    # Highlight UAV-served customers
    for node in uav_customers:
        x, y = coords[node]
        ax.scatter([x], [y], s=100, color="#f59e0b", edgecolor="black", linewidth=0.4, zorder=6)

    title_lines = [
        f"Best Scenario {data.scenario} Problem: {data.problem_name}",
        f"OFV = {data.ofv:.2f}" if data.ofv is not None else "OFV = N/A",
        f"Truck Customers = {data.num_truck_customers} | UAV Customers = {data.num_uav_customers}",
    ]
    ax.set_title("\n".join(title_lines), fontsize=14, pad=14)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(True, alpha=0.25)
    ax.axis("equal")
    ax.legend(loc="best")

    fig.tight_layout()
    fig.savefig(output_png, dpi=220, bbox_inches="tight")
    plt.close(fig)

    metadata = {
        "scenario": data.scenario,
        "problemName": data.problem_name,
        "vehicleFileID": data.vehicle_file_id,
        "numUAVs": data.num_uavs,
        "ofv": data.ofv,
        "totalTime": data.total_time,
        "numUAVcust": data.num_uav_customers,
        "numTruckCust": data.num_truck_customers,
        "summary_file": None if data.summary_file is None else str(data.summary_file),
        "coordinate_source": None if data.coordinate_source is None else str(data.coordinate_source),
        "route_status": data.route_status,
        "truck_route_length": len(data.truck_route),
        "uav_sortie_count": len(data.uav_sorties),
        "truck_line_drawn": truck_line_drawn,
        "uav_line_count_drawn": uav_line_count,
        "output_image": str(output_png),
    }
    output_json.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return output_png, output_json


# =============================================================================
# Public entry point
# =============================================================================

def generate_best_map(scenario: int) -> None:
    data = build_best_problem_map_data(scenario)
    png, meta = draw_best_problem_map(data)

    print(f"\nScenario {scenario}")
    print(f"Best problem: {data.problem_name}")
    print(f"Summary file: {data.summary_file}")
    print(f"Route status: {data.route_status}")
    print(f"Truck route length: {len(data.truck_route)}")
    print(f"UAV sorties parsed: {len(data.uav_sorties)}")
    print(f"Coordinate source: {data.coordinate_source}")
    print(f"Map image: {png}")
    print(f"Metadata: {meta}")
