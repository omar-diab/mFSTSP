"""Normalize recorded results without silently pooling experiments or configurations."""
from __future__ import annotations

import ast
import csv
import io
import math
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
COLUMNS = "problemName vehicleFileID cutoffTime problemType problemTypeString numUAVs numTrucks requireTruckAtDepot requireDriver Etype ITER runString numCustomers timestamp ofv bestBound totalTime isOptimal numUAVcust numTruckCust waitingTruck waitingUAV".split()
KEYS = "problemName numCustomers vehicleFileID numUAVs numTrucks requireTruckAtDepot requireDriver Etype cutoffTime ITER".split()
METRICS = {"ofv": "Makespan (s)", "totalTime": "Runtime (s)", "waitingTruck": "Truck waiting (s)", "waitingUAV": "UAV waiting (s)", "numUAVcust": "UAV customers", "numTruckCust": "Truck customers"}


def signature():
    """Invalidate the UI cache when data is added, removed, or updated."""
    files = [ROOT / "performance_summary.csv", ROOT / "performance_summary_archive.csv"]
    files += list((ROOT / "results").rglob("*.csv"))
    files += list((ROOT / "Problems").glob("*/*.csv"))
    return tuple((str(p.relative_to(ROOT)), p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(set(files)) if p.exists())


def read_csv(path: Path, names=None):
    """Read headerless/headered summaries, retaining diagnostics for malformed records."""
    issues, rows = [], []
    display_path = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path.name
    if not path.exists():
        return pd.DataFrame(), [f"Missing: {display_path}"]
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, skipinitialspace=True)
        header = names
        for line, row in enumerate(reader, 1):
            if not row or not any(x.strip() for x in row):
                continue
            row = [x.strip() for x in row]
            if header is None:
                header = row
                continue
            if row == header:
                continue
            if len(row) != len(header):
                issues.append(f"{display_path}:{line}: skipped {len(row)} fields; expected {len(header)}")
                continue
            rows.append(row)
    return pd.DataFrame(rows, columns=header), issues


def normalize(frame, source):
    df = frame.copy()
    for col in COLUMNS:
        if col not in df:
            df[col] = pd.NA
    df["problemName"] = df.problemName.astype(str).str.strip()
    df["problemTypeString"] = df.problemTypeString.fillna("").astype(str).str.strip()
    for col in ["requireTruckAtDepot", "requireDriver", "isOptimal"]:
        df[col] = df[col].astype(str).str.lower().replace({"true": "1", "false": "0"})
    for col in set(COLUMNS) - {"problemName", "problemTypeString", "runString", "timestamp"}:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["source"] = source
    df["algorithm"] = df.problemTypeString.replace("", "Unspecified algorithm")
    # Positive finite objective means a recorded solution, not independent feasibility proof.
    df["solved"] = df.ofv.gt(0) & df.ofv.map(lambda x: pd.notna(x) and math.isfinite(x))
    if "status" in frame:
        df["solved"] &= df.status.eq("solved")
    df["outcome"] = df.solved.map({True: "Recorded solution", False: "No valid objective"})
    if "status" in frame:
        df.loc[~df.solved, "outcome"] = df.loc[~df.solved, "status"].fillna("Unknown")
    df["configuration"] = df.apply(lambda r: f"vehicle={r.vehicleFileID:g} | UAVs={r.numUAVs:g} | E={r.Etype:g} | limit={r.cutoffTime:g}s | depot={r.requireTruckAtDepot:g} | driver={r.requireDriver:g} | iter={r.ITER:g}", axis=1) if len(df) else pd.Series(dtype=str)
    return df


def load_results():
    frames, issues = [], []
    for filename, names in [("performance_summary.csv", COLUMNS), ("performance_summary_archive.csv", None)]:
        frame, notes = read_csv(ROOT / filename, names)
        issues += notes
        frames.append(normalize(frame, filename))
    # Aggregate runner files are a distinct experiment; do not also load their per-size duplicates.
    for filename in ["all_solved.csv", "all_not_solved.csv"]:
        path = ROOT / "results" / filename
        frame, notes = read_csv(path)
        issues += notes
        if frame.empty:
            continue
        frame = frame.rename(columns={"customerCount": "numCustomers", "objective": "ofv", "truckWaitingTime": "waitingTruck", "uavWaitingTime": "waitingUAV", "numTruckCustomers": "numTruckCust", "numUAVCustomers": "numUAVcust"})
        frame["problemTypeString"] = "mFSTSP No-Gurobi Heuristic"
        frames.append(normalize(frame, "results/" + filename))
    return pd.concat(frames, ignore_index=True), issues


def pair_results(ours, archive, metric="ofv"):
    """Best finite objective per exact config, outer join; no cross-config comparisons."""
    def select(df, side):
        df = df.copy()
        # Retain unknown configurations in the audit but never match two unknowns.
        missing = df[KEYS].isna().any(axis=1)
        df["_unknown_config"] = [f"{side}-{i}" if value else "" for i, value in enumerate(missing)]
        join_keys = KEYS + ["_unknown_config"]
        df["_rank"] = df.ofv.where(df.solved, float("inf"))
        counts = df.groupby(join_keys, dropna=False).size().rename("recorded_runs").reset_index()
        return df.sort_values("_rank", kind="stable").drop_duplicates(join_keys).drop(columns="_rank").merge(counts, on=join_keys)
    left, right = select(ours, "our"), select(archive, "archive")
    result = left.merge(right, on=KEYS+["_unknown_config"], how="outer", suffixes=("_our", "_archive"), indicator=True).drop(columns="_unknown_config")
    result["comparison_status"] = result["_merge"].astype(str).map({"left_only": "No compatible archive run", "right_only": "No compatible proposed run", "both": "Paired configuration"})
    both = result["_merge"].eq("both")
    result["comparable"] = both & result.solved_our.eq(True) & result.solved_archive.eq(True)
    result.loc[both & ~result.comparable, "comparison_status"] = "Matching config; missing solution"
    a, b = result[f"{metric}_our"], result[f"{metric}_archive"]
    valid = result.comparable & a.notna() & b.notna() & a.ge(0) & b.ge(0)
    direction = 1 if metric == "numUAVcust" else -1
    delta = direction * (a - b)
    result["improvement_percent"] = (100 * delta / b.where(b.ne(0))).where(valid)
    result["winner"] = "Not comparable"
    result.loc[valid & delta.gt(1e-6), "winner"] = "Proposed"
    result.loc[valid & delta.lt(-1e-6), "winner"] = "Archive"
    result.loc[valid & delta.abs().le(1e-6), "winner"] = "Tie"
    return result


def literal(text, default):
    try:
        return ast.literal_eval(text.strip())
    except (ValueError, SyntaxError):
        return default


def labeled(text, label):
    match = re.search(r"^" + re.escape(label) + r":\s*(.*)$", text, re.M)
    return match.group(1).strip() if match else ""


def solution_files(instance):
    return sorted((ROOT / "Problems" / instance).glob("tbl_solutions_*.csv"))


def solution_snapshots(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    if "NO-GUROBI HEURISTIC SOLUTION" in text:
        return [text]
    starts = [m.start() for m in re.finditer(r"^problemName,", text, re.M)]
    return [text[a:b] for a, b in zip(starts, starts[1:]+[len(text)])] if starts else [text]


def load_solution(path: Path, snapshot=-1):
    """Parse both saved solution formats; never synthesize solver output."""
    snapshots = solution_snapshots(path)
    text = snapshots[snapshot]
    proposed = "NO-GUROBI HEURISTIC SOLUTION" in text
    data = {"path": str(path.relative_to(ROOT)), "proposed": proposed, "segments": [], "deliveries": [], "events": [], "warnings": [], "validation": {}, "route": [], "sorties": []}
    objective = labeled(text, "Objective Function Value")
    data["ofv"] = float(objective) if objective else None
    data["runtime"] = float(labeled(text, "Runtime")) if labeled(text, "Runtime") else None
    if proposed:
        data["config"] = {k: labeled(text, k) for k in KEYS if k != "numCustomers"}
        for label, key in [("Truck Route", "route"), ("Validation", "validation")]:
            match = re.search(re.escape(label) + r":\s*\n([^\n]+)", text)
            data[key] = literal(match.group(1), [] if key == "route" else {}) if match else data[key]
        for section, key in [("UAV Sorties", "sorties"), ("Activity Log", "events")]:
            match = re.search(re.escape(section) + r":\s*\n(.*?)(?=\n[A-Za-z][A-Za-z ]*:|\Z)", text, re.S)
            data[key] = [value for line in match.group(1).splitlines() if isinstance(value := literal(line, None), dict)] if match else []
        for e in data["events"]:
            if e.get("type") == "truck_travel":
                end = float(e["arrival_time"])
                data["segments"].append(dict(vehicle="Truck 1", start=end-float(e["duration"]), end=end, a=int(e["from"]), b=int(e["to"]), status="Traveling"))
            elif e.get("type") == "truck_service":
                data["deliveries"].append((int(e["node"]), float(e["time_after_service"])))
        for s in data["sorties"]:
            start, end = float(s["launch_time"]), float(s["arrival_to_recovery_time"])
            # No customer arrival timestamp is saved: midpoint is explicitly illustrative.
            mid = (start + end) / 2
            vehicle = f"UAV {s['uav']}"
            data["segments"] += [dict(vehicle=vehicle, start=start, end=mid, a=int(s["launch"]), b=int(s["customer"]), status="Illustrative outbound timing"), dict(vehicle=vehicle, start=mid, end=end, a=int(s["customer"]), b=int(s["recovery"]), status="Illustrative return timing")]
            data["deliveries"].append((int(s["customer"]), mid))
        data["warnings"].append("UAV customer arrival times are not recorded. Flight-leg timing and UAV delivery highlights use an illustrative midpoint; launch/recovery-arrival and truck travel times come from the saved schedule.")
        # Detect recorded overlapping physical assignments (including wait for truck).
        fleet = {}
        for s in sorted(data["sorties"], key=lambda x: x["launch_time"]):
            uav = s["uav"]
            if s["launch_time"] < fleet.get(uav, -1) - 1e-5:
                data["warnings"].append(f"Recorded UAV {uav} launches before its previous rendezvous. Playback is a record visualization, not a verified feasible simulation.")
            fleet[uav] = max(s["arrival_to_recovery_time"], s.get("recovery_truck_arrival_time", 0))
    else:
        lines = text.splitlines()
        header_idx = next((i for i, x in enumerate(lines) if x.startswith("vehicleID,")), None)
        data["config"] = {}
        if len(lines) > 1:
            headers = next(csv.reader([lines[0]], skipinitialspace=True))
            values = next(csv.reader([lines[1]], skipinitialspace=True))
            data["config"] = dict(zip([x.strip() for x in headers], [x.strip() for x in values]))
        if header_idx is not None:
            for row in csv.reader(io.StringIO("\n".join(lines[header_idx+1:])), skipinitialspace=True):
                if len(row) < 9:
                    continue
                try:
                    start, end = float(row[3]), float(row[5])
                    a, b = int(row[4]), int(row[6])
                    if end < start:
                        continue  # terminal -1 sentinel
                    vehicle = f"{row[1].strip()} {int(row[0])}"
                    status = row[-1].strip()
                    data["segments"].append(dict(vehicle=vehicle, start=max(0, start), end=end, a=a, b=b, status=status))
                    if status == "Making Delivery":
                        data["deliveries"].append((b, end))
                    if status in ("UAV Launch", "UAV Recovery"):
                        data["events"].append(dict(vehicle=vehicle, type=status, node=b, time=end))
                except ValueError:
                    data["warnings"].append("An assignment row could not be parsed.")
    data["duration"] = max([s["end"] for s in data["segments"]] + [data["ofv"] or 0])
    data["snapshot_count"] = len(snapshots)
    data["snapshot_index"] = snapshot % len(snapshots)
    data["warnings"] = list(dict.fromkeys(data["warnings"]))
    return data


def coordinates(instance):
    frame = pd.read_csv(ROOT / "Problems" / instance / "tbl_locations.csv", skipinitialspace=True)
    frame.columns = [x.strip().lstrip("% ") for x in frame.columns]
    coords = {int(r.nodeID): (float(r.lonDeg), float(r.latDeg)) for r in frame.itertuples()}
    if 0 not in coords:
        raise ValueError("Benchmark has no depot node 0")
    if any(not math.isfinite(lon) or not math.isfinite(lat) or abs(lon)>180 or abs(lat)>90 for lon, lat in coords.values()):
        raise ValueError("Benchmark contains invalid latitude/longitude")
    return coords


def benchmark_inventory():
    rows = []
    for directory in sorted((ROOT / "Problems").glob("*")):
        if directory.is_dir():
            location = directory / "tbl_locations.csv"
            issue = ""
            try:
                count = len(coordinates(directory.name)) - 1 if location.exists() else None
            except (ValueError, KeyError, pd.errors.ParserError, pd.errors.EmptyDataError) as error:
                count, issue = None, str(error)
            rows.append(dict(problemName=directory.name, numCustomers=count, locations=location.exists(), truck_travel=(directory / "tbl_truck_travel_data_PG.csv").exists(), saved_solutions=len(solution_files(directory.name)), issue=issue))
    return pd.DataFrame(rows, columns=["problemName", "numCustomers", "locations", "truck_travel", "saved_solutions", "issue"])
