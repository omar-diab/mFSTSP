// Builds the read-only JSON the dashboard fetches from public/data.
// Sources are the recorded experiments in new/; nothing here runs a solver
// or writes outside public/data.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = path.resolve(WEB, "..");
const OLD = path.resolve(ROOT, "..", "old");
const OUT = path.join(WEB, "public", "data");

const COLUMNS =
  "problemName vehicleFileID cutoffTime problemType problemTypeString numUAVs numTrucks requireTruckAtDepot requireDriver Etype ITER runString numCustomers timestamp ofv bestBound totalTime isOptimal numUAVcust numTruckCust waitingTruck waitingUAV".split(
    " ",
  );

const issues = [];

// ------------------------------------------------------------
// CSV helpers
// ------------------------------------------------------------

function parseCSV(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (ch === '"') quoted = false;
      else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") {
      row.push(field.trim());
      field = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(field.trim());
      rows.push(row);
      row = [];
      field = "";
    } else field += ch;
  }
  if (field || row.length) {
    row.push(field.trim());
    rows.push(row);
  }
  return rows.filter((r) => r.some((x) => x !== ""));
}

function readTable(file, names) {
  const rel = path.relative(ROOT, file);
  if (!fs.existsSync(file)) {
    issues.push(`Missing: ${rel}`);
    return [];
  }
  const rows = parseCSV(fs.readFileSync(file, "utf8").replace(/^﻿/, ""));
  const header = names ?? rows.shift() ?? [];
  const out = [];
  rows.forEach((row, i) => {
    if (row.join() === header.join()) return;
    if (row.length !== header.length) {
      issues.push(`${rel}:${i + 1}: skipped ${row.length} fields; expected ${header.length}`);
      return;
    }
    out.push(Object.fromEntries(header.map((h, k) => [h, row[k]])));
  });
  return out;
}

const num = (v) => {
  if (v === undefined || v === null || v === "") return null;
  const s = String(v).trim().toLowerCase();
  if (s === "true") return 1;
  if (s === "false") return 0;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
};
const round = (v, d = 3) => (v === null ? null : Math.round(v * 10 ** d) / 10 ** d);

// ------------------------------------------------------------
// Recorded results
// ------------------------------------------------------------

function cohortOf(algorithm, source) {
  if (source === "performance_summary_archive.csv") return "archive";
  if (/gurobi heuristic/i.test(algorithm)) return "proposed";
  return "rerun";
}

function normalize(r, source, extra = {}) {
  const algorithm = (r.problemTypeString || "").trim() || "Unspecified algorithm";
  const ofv = num(r.ofv);
  let solved = ofv !== null && ofv > 0;
  let outcome = solved ? "Recorded solution" : "No valid objective";
  if (r.status !== undefined) {
    solved = solved && r.status === "solved";
    if (!solved) outcome = r.status || "Unknown";
  }
  return {
    source,
    cohort: cohortOf(algorithm, source),
    algorithm,
    problemName: String(r.problemName).trim(),
    numCustomers: num(r.numCustomers),
    vehicleFileID: num(r.vehicleFileID),
    numUAVs: num(r.numUAVs),
    numTrucks: num(r.numTrucks),
    requireTruckAtDepot: num(r.requireTruckAtDepot),
    requireDriver: num(r.requireDriver),
    Etype: num(r.Etype),
    cutoffTime: num(r.cutoffTime),
    ITER: num(r.ITER),
    timestamp: r.timestamp ?? "",
    ofv: round(ofv),
    bestBound: round(num(r.bestBound)),
    totalTime: round(num(r.totalTime)),
    isOptimal: num(r.isOptimal),
    numUAVcust: num(r.numUAVcust),
    numTruckCust: num(r.numTruckCust),
    waitingTruck: round(num(r.waitingTruck)),
    waitingUAV: round(num(r.waitingUAV)),
    solved,
    outcome,
    ...extra,
  };
}

function loadResults() {
  const rows = [];
  for (const r of readTable(path.join(ROOT, "performance_summary.csv"), COLUMNS))
    rows.push(normalize(r, "performance_summary.csv"));
  for (const r of readTable(path.join(ROOT, "performance_summary_archive.csv")))
    rows.push(normalize(r, "performance_summary_archive.csv"));

  // Strategy labels live in the runner's detailed file, keyed by problem.
  const strategy = {};
  for (const r of readTable(path.join(ROOT, "results", "gurobi_heuristic_results.csv")))
    strategy[r.problem_id] = r.strategy;

  // Aggregate runner files only; per-size copies would double count.
  for (const file of ["all_solved.csv", "all_not_solved.csv"]) {
    for (const r of readTable(path.join(ROOT, "results", file))) {
      rows.push(
        normalize(
          {
            ...r,
            numCustomers: r.customerCount,
            ofv: r.objective,
            waitingTruck: r.truckWaitingTime,
            waitingUAV: r.uavWaitingTime,
            numTruckCust: r.numTruckCustomers,
            numUAVcust: r.numUAVCustomers,
            problemTypeString: "mFSTSP Gurobi Heuristic",
          },
          "results/" + file,
          { strategy: strategy[r.problemName] ?? "" },
        ),
      );
    }
  }
  return rows;
}

// ------------------------------------------------------------
// Benchmarks and saved solutions
// ------------------------------------------------------------

function coordinates(dir) {
  const text = fs.readFileSync(path.join(dir, "tbl_locations.csv"), "utf8");
  const rows = parseCSV(text);
  const header = rows.shift().map((h) => h.replace(/^%\s*/, "").trim());
  const idx = (k) => header.indexOf(k);
  return rows.map((r) => [
    Number(r[idx("nodeID")]),
    Number(r[idx("lonDeg")]),
    Number(r[idx("latDeg")]),
    Number(r[idx("parcelWtLbs")]),
  ]);
}

const labeled = (text, label) => {
  const m = text.match(new RegExp("^" + label + ":\\s*(.*)$", "m"));
  return m ? m[1].trim() : "";
};

// Python literal (dict/list of numbers, strings, booleans) to JSON.
function pyLiteral(text) {
  try {
    return JSON.parse(
      text
        .replace(/'/g, '"')
        .replace(/\bTrue\b/g, "true")
        .replace(/\bFalse\b/g, "false")
        .replace(/\bNone\b/g, "null")
        .replace(/\binf\b/g, "1e999"),
    );
  } catch {
    return null;
  }
}

function section(text, label) {
  const m = text.match(new RegExp(label + ":\\s*\\n([\\s\\S]*?)(?=\\n[A-Za-z][A-Za-z ]*:\\s*\\n|$)"));
  return m ? m[1].trim().split("\n").filter(Boolean) : [];
}

// main.py writes a "<NAME> SOLUTION" banner; the original solvers write CSV blocks.
const SIMPLE = /^[A-Z -]+SOLUTION\s*\n=+/;

function snapshots(text) {
  if (SIMPLE.test(text.slice(0, 120))) return [text];
  const starts = [...text.matchAll(/^problemName,/gm)].map((m) => m.index);
  if (!starts.length) return [text];
  return starts.map((a, i) => text.slice(a, starts[i + 1] ?? text.length));
}

function parseSnapshot(text) {
  const proposed = SIMPLE.test(text.slice(0, 120));
  const data = {
    ofv: num(labeled(text, "Objective Function Value")),
    runtime: num(labeled(text, "Runtime")),
    config: {},
    validation: null,
    route: [],
    sorties: [],
    segments: [],
    deliveries: [],
    events: [],
    warnings: [],
  };

  if (proposed) {
    for (const k of "problemTypeString vehicleFileID numUAVs Etype cutoffTime requireTruckAtDepot requireDriver ITER".split(" "))
      data.config[k] = labeled(text, k);
    data.validation = pyLiteral(section(text, "Validation")[0] ?? "");
    data.route = pyLiteral(section(text, "Truck Route")[0] ?? "") ?? [];
    data.sorties = section(text, "UAV Sorties").map(pyLiteral).filter(Boolean);
    const log = section(text, "Activity Log").map(pyLiteral).filter(Boolean);

    for (const e of log) {
      if (e.type === "truck_travel") {
        const end = e.arrival_time;
        data.segments.push(["Truck 1", end - e.duration, end, e.from, e.to, "Traveling"]);
      } else if (e.type === "truck_service") {
        data.segments.push(["Truck 1", e.time_after_service - e.duration, e.time_after_service, e.node, e.node, "Making Delivery"]);
        data.deliveries.push([e.node, e.time_after_service]);
      } else if (e.type === "uav_launch") {
        data.events.push({ vehicle: `UAV ${e.uav}`, type: "UAV Launch", node: e.launch_node, time: e.launch_time });
      } else if (e.type === "recovery_node") {
        data.events.push({ vehicle: "Truck 1", type: "UAV Recovery", node: e.node, time: e.time_after_recovery_sync });
      }
    }
    for (const s of data.sorties) {
      // No customer arrival time is saved, so the midpoint is illustrative.
      const mid = (s.launch_time + s.arrival_to_recovery_time) / 2;
      const v = `UAV ${s.uav}`;
      data.segments.push([v, s.launch_time, mid, s.launch, s.customer, "Illustrative outbound"]);
      data.segments.push([v, mid, s.arrival_to_recovery_time, s.customer, s.recovery, "Illustrative return"]);
      data.deliveries.push([s.customer, mid]);
    }
    if (data.sorties.length)
      data.warnings.push(
        "UAV customer arrival times are not recorded. UAV flight legs and their delivery highlights use an illustrative midpoint; launch, recovery and truck times come from the saved schedule.",
      );
    const ready = {};
    for (const s of [...data.sorties].sort((a, b) => a.launch_time - b.launch_time)) {
      if (s.launch_time < (ready[s.uav] ?? -1) - 1e-5)
        data.warnings.push(`UAV ${s.uav} is recorded launching before its previous rendezvous. Playback shows the record as saved; it is not a verified feasible simulation.`);
      ready[s.uav] = Math.max(s.arrival_to_recovery_time, s.recovery_truck_arrival_time ?? 0);
    }
  } else {
    const lines = text.split(/\r?\n/);
    if (lines.length > 1) {
      const h = parseCSV(lines[0])[0] ?? [];
      const v = parseCSV(lines[1])[0] ?? [];
      h.forEach((k, i) => (data.config[k] = v[i]));
    }
    const at = lines.findIndex((l) => l.startsWith("vehicleID,"));
    if (at >= 0) {
      for (const row of parseCSV(lines.slice(at + 1).join("\n"))) {
        if (row.length < 9) continue;
        const start = Number(row[3]);
        const end = Number(row[5]);
        const a = Number(row[4]);
        const b = Number(row[6]);
        // A terminal row uses -1 as an end sentinel.
        if (![start, end, a, b].every(Number.isFinite) || end < start) continue;
        const vehicle = `${row[1]} ${Number(row[0])}`;
        const status = row[row.length - 1];
        data.segments.push([vehicle, Math.max(0, start), end, a, b, status]);
        if (status === "Making Delivery") data.deliveries.push([b, end]);
        if (status === "UAV Launch" || status === "UAV Recovery") data.events.push({ vehicle, type: status, node: b, time: end });
      }
    }
  }

  data.segments = data.segments.map(([v, s, e, a, b, st]) => [v, round(s, 2), round(e, 2), a, b, st]);
  data.deliveries = data.deliveries.map(([n, t]) => [n, round(t, 2)]);
  data.events = data.events.map((e) => ({ ...e, time: round(e.time, 2) }));
  data.duration = round(Math.max(data.ofv ?? 0, ...data.segments.map((s) => s[2])), 2);
  data.warnings = [...new Set(data.warnings)];
  return data;
}

function solutionKind(name) {
  if (name.includes("_GurobiHeuristic")) return { kind: "proposed", algorithm: "mFSTSP Gurobi Heuristic" };
  if (name.includes("_NoGurobiHeuristic")) return { kind: "proposed", algorithm: "mFSTSP No-Gurobi Heuristic (legacy)" };
  if (name.includes("_IP")) return { kind: "original", algorithm: "mFSTSP IP" };
  return { kind: "original", algorithm: "mFSTSP Heuristic" };
}

function loadBenchmarks() {
  const problems = path.join(ROOT, "Problems");
  fs.rmSync(path.join(OUT, "solutions"), { recursive: true, force: true });
  fs.mkdirSync(path.join(OUT, "solutions"), { recursive: true });
  const inventory = [];
  let savedFiles = 0;

  for (const name of fs.readdirSync(problems).sort()) {
    const dir = path.join(problems, name);
    if (!fs.statSync(dir).isDirectory()) continue;
    let coords = [];
    let issue = "";
    try {
      coords = coordinates(dir);
      if (!coords.some((c) => c[0] === 0)) issue = "Benchmark has no depot node 0";
    } catch (e) {
      issue = String(e.message ?? e);
    }
    const files = fs
      .readdirSync(dir)
      .filter((f) => f.startsWith("tbl_solutions_") && f.endsWith(".csv"))
      .sort();
    savedFiles += files.length;

    const solutions = files.map((file) => {
      const m = file.match(/tbl_solutions_(\d+)_(\d+)_/);
      let snaps = [];
      try {
        snaps = snapshots(fs.readFileSync(path.join(dir, file), "utf8")).map(parseSnapshot);
      } catch (e) {
        issues.push(`Problems/${name}/${file}: ${e.message ?? e}`);
      }
      return { file, vehicleFileID: m ? Number(m[1]) : null, numUAVs: m ? Number(m[2]) : null, ...solutionKind(file), snapshots: snaps };
    });

    fs.writeFileSync(path.join(OUT, "solutions", `${name}.json`), JSON.stringify({ problemName: name, coords, solutions }));
    const truckTravel = fs.existsSync(path.join(dir, "tbl_truck_travel_data_PG.csv"));
    if (issue || !truckTravel) issues.push(`Benchmark ${name}: ${issue || "Missing truck travel CSV"}`);
    inventory.push({ problemName: name, numCustomers: coords.length ? coords.length - 1 : null, locations: coords.length > 0, truckTravel, savedSolutions: files.length, issue });
  }
  return { inventory, savedFiles };
}

// ------------------------------------------------------------
// Source excerpts for the algorithms page
// ------------------------------------------------------------

const SOURCES = [
  [path.join(ROOT, "proposed_heuristic_with_gurobi.py"), "new/proposed_heuristic_with_gurobi.py"],
  [path.join(OLD, "solve_mfstsp_heuristic.py"), "old/solve_mfstsp_heuristic.py"],
  [path.join(OLD, "solve_mfstsp_IP.py"), "old/solve_mfstsp_IP.py"],
];

function loadSources() {
  const out = {};
  for (const [file, label] of SOURCES) {
    if (!fs.existsSync(file)) {
      issues.push(`Missing source: ${label}`);
      continue;
    }
    const lines = fs.readFileSync(file, "utf8").split("\n");
    lines.forEach((line, i) => {
      const m = line.match(/^def (\w+)\(/);
      if (!m) return;
      let end = i + 1;
      while (end < lines.length && (lines[end] === "" || /^\s/.test(lines[end]) || /^\)/.test(lines[end]))) end++;
      while (end > i && lines[end - 1].trim() === "") end--;
      out[`${label}#${m[1]}`] = { file: label, line: i + 1, code: lines.slice(i, end).join("\n") };
    });
  }
  return out;
}

// ------------------------------------------------------------

fs.mkdirSync(OUT, { recursive: true });
const results = loadResults();
const { inventory, savedFiles } = loadBenchmarks();
fs.writeFileSync(
  path.join(OUT, "results.json"),
  JSON.stringify({ generatedAt: new Date().toISOString(), results, inventory, savedFiles, issues }),
);
fs.writeFileSync(path.join(OUT, "source.json"), JSON.stringify(loadSources()));
console.log(`dashboard data: ${results.length} result rows, ${inventory.length} benchmarks, ${savedFiles} saved solutions, ${issues.length} issues`);
