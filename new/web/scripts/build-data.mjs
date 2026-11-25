// Builds public/data/reproduction.json from:
//   old/performance_summary_archive.csv          (the paper's results, Murray & Raj 2019)
//   old/reproduction/our_results.csv             (our re-run of the same code, made by old/reproduce.py)
//   new/results/alns/alns_results.csv            (our ALNS, made by new/run_alns_benchmark.py)
//   new/results/alns/evaluator_validation.csv    (our evaluator on the paper's solutions)
// and copies new/results/alns/solutions/*.json to public/data/alns/ with node coordinates added.
// Runs before `npm run dev` and `npm run build`.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OLD = path.resolve(ROOT, "..", "..", "old");
const ARCHIVE = path.join(OLD, "performance_summary_archive.csv");
const OURS = path.join(OLD, "reproduction", "our_results.csv");
const NEW = path.resolve(ROOT, "..");
const ALNS = path.join(NEW, "results", "alns", "alns_results.csv");
const VALIDATION = path.join(NEW, "results", "alns", "evaluator_validation.csv");
const SOLUTIONS = path.join(NEW, "results", "alns", "solutions");
const PROBLEMS = path.join(OLD, "Problems");
const OUT = path.join(ROOT, "public", "data", "reproduction.json");
const OUT_SOLUTIONS = path.join(ROOT, "public", "data", "alns");

// Small CSV reader that handles quoted fields.
function readCSV(file) {
  const text = fs.readFileSync(file, "utf8").replace(/^\uFEFF/, "");
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") {
      row.push(cell);
      cell = "";
    }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cell);
      if (row.some((c) => c.trim() !== "")) rows.push(row);
      row = [];
      cell = "";
    } else cell += ch;
  }
  row.push(cell);
  if (row.some((c) => c.trim() !== "")) rows.push(row);
  const header = rows.shift().map((h) => h.trim());
  return rows.map((r) => Object.fromEntries(header.map((h, i) => [h, (r[i] ?? "").trim()])));
}

const num = (v) => {
  if (v === undefined || v === null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};
const bool = (v) => (v === "True" ? true : v === "False" ? false : null);
const key = (r) => `${r.problemName}|${r.vehicleFileID}|${r.method}|${r.numUAVs}`;

const paper = readCSV(ARCHIVE).map((r) => ({
  problemName: r.problemName,
  numCustomers: num(r.numCustomers),
  vehicleFileID: num(r.vehicleFileID),
  method: Number(r.problemType) === 1 ? "IP" : "Heuristic",
  numUAVs: num(r.numUAVs),
  cutoffTime: num(r.cutoffTime),
  ofv: num(r.ofv),
  bestBound: num(r.bestBound),
  totalTime: num(r.totalTime),
  isOptimal: bool(r.isOptimal),
  numUAVcust: num(r.numUAVcust),
  numTruckCust: num(r.numTruckCust),
  waitingTruck: num(r.waitingTruck),
  waitingUAV: num(r.waitingUAV),
}));

const oursByKey = new Map();
if (fs.existsSync(OURS)) {
  for (const r of readCSV(OURS)) {
    const row = {
      problemName: r.problemName,
      numCustomers: num(r.numCustomers),
      vehicleFileID: num(r.vehicleFileID),
      method: r.method,
      numUAVs: num(r.numUAVs),
      cutoffTime: num(r.cutoffTime),
      status: r.status,
      message: r.message,
      ofv: num(r.ofv),
      bestBound: num(r.bestBound),
      totalTime: num(r.totalTime),
      isOptimal: bool(r.isOptimal),
      numUAVcust: num(r.numUAVcust),
      numTruckCust: num(r.numTruckCust),
      waitingTruck: num(r.waitingTruck),
      waitingUAV: num(r.waitingUAV),
      timestamp: r.timestamp,
    };
    if (row.status !== "solved" && row.status !== "time_capped") row.ofv = null;
    oursByKey.set(key(row), row);
  }
}

// One "ours" row for every paper run, so runs we have not reached show as not run yet.
const ours = paper.map(
  (p) =>
    oursByKey.get(key(p)) ?? {
      ...Object.fromEntries(Object.keys(p).map((k) => [k, null])),
      problemName: p.problemName,
      numCustomers: p.numCustomers,
      vehicleFileID: p.vehicleFileID,
      method: p.method,
      numUAVs: p.numUAVs,
      status: "not_run",
      message: "",
      timestamp: "",
    },
);

// ------------------------------------------------------------
// ALNS (our algorithm)
// ------------------------------------------------------------

const alns = [];
if (fs.existsSync(ALNS)) {
  const latest = new Map(); // keep the last row per run (a rerun replaces an older one)
  for (const r of readCSV(ALNS)) latest.set(`${r.problemName}|${r.vehicleFileID}|${r.numUAVs}|${r.seed}`, r);
  for (const r of latest.values()) {
    alns.push({
      problemName: r.problemName,
      numCustomers: num(r.numCustomers),
      vehicleFileID: num(r.vehicleFileID),
      numUAVs: num(r.numUAVs),
      etype: num(r.Etype),
      seed: num(r.seed),
      timeLimit: num(r.timeLimit),
      status: r.status,
      ofv: r.status === "solved" ? num(r.ofv) : null,
      initialOfv: num(r.initialOfv),
      runtime: num(r.runtime),
      iterations: num(r.iterations),
      evaluations: num(r.evaluations),
      numUAVcust: num(r.numUAVcust),
      numTruckCust: num(r.numTruckCust),
      waitingTruck: num(r.waitingTruck),
      waitingUAV: num(r.waitingUAV),
      verified: bool(r.verified),
      message: r.message,
      timestamp: r.timestamp,
    });
  }
}

// Evaluator check: summarised by method and size (the full CSV stays in the repo).
const validation = [];
if (fs.existsSync(VALIDATION)) {
  const groups = new Map();
  for (const r of readCSV(VALIDATION)) {
    const k = `${r.method}|${r.numCustomers}`;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(r);
  }
  for (const [k, rows] of groups) {
    const [method, size] = k.split("|");
    const feas = rows.filter((r) => r.feasible === "True");
    const diffs = feas.map((r) => Number(r.diffPct));
    const opt = rows.filter((r) => r.paperOptimal === "True");
    const optFeas = opt.filter((r) => r.feasible === "True");
    validation.push({
      method,
      numCustomers: Number(size),
      plans: rows.length,
      feasible: feas.length,
      verified: rows.filter((r) => r.verified === "True").length,
      exact: diffs.filter((d) => Math.abs(d) < 0.01).length,
      meanDiffPct: diffs.length ? diffs.reduce((a, b) => a + b, 0) / diffs.length : null,
      minDiffPct: diffs.length ? Math.min(...diffs) : null,
      maxDiffPct: diffs.length ? Math.max(...diffs) : null,
      provenOptimal: opt.length,
      provenOptimalExact: optFeas.filter((r) => Math.abs(Number(r.diffPct)) < 0.01).length,
      provenOptimalMinDiffPct: optFeas.length ? Math.min(...optFeas.map((r) => Number(r.diffPct))) : null,
    });
  }
  validation.sort((a, b) => a.method.localeCompare(b.method) || a.numCustomers - b.numCustomers);
}

// Solutions for the route viewer, with coordinates, plus operator usage totals.
const locations = new Map();
function nodesOf(problem) {
  if (!locations.has(problem)) {
    const file = path.join(PROBLEMS, problem, "tbl_locations.csv");
    const text = fs.readFileSync(file, "utf8").split(/\r?\n/).filter((l) => l.trim() && !l.startsWith("%"));
    locations.set(problem, text.map((l) => {
      const c = l.split(",").map((x) => x.trim());
      return { id: Number(c[0]), lat: Number(c[2]), lon: Number(c[3]), parcelLbs: Number(c[5]) };
    }));
  }
  return locations.get(problem);
}
const operatorTotals = { destroy: {}, repair: {} };
let copied = 0;
fs.rmSync(OUT_SOLUTIONS, { recursive: true, force: true });
if (fs.existsSync(SOLUTIONS)) {
  fs.mkdirSync(OUT_SOLUTIONS, { recursive: true });
  for (const f of fs.readdirSync(SOLUTIONS)) {
    if (!f.endsWith(".json")) continue;
    const sol = JSON.parse(fs.readFileSync(path.join(SOLUTIONS, f), "utf8"));
    for (const [kind, key] of [["destroy", "destroy_operators"], ["repair", "repair_operators"]])
      for (const [name, st] of Object.entries(sol[key] ?? {})) operatorTotals[kind][name] = (operatorTotals[kind][name] ?? 0) + (st.uses ?? 0);
    delete sol.config;
    sol.nodes = nodesOf(sol.problemName);
    fs.writeFileSync(path.join(OUT_SOLUTIONS, f), JSON.stringify(sol));
    copied++;
  }
}

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify({ generatedAt: new Date().toISOString(), paper, ours, alns, validation, operatorTotals }));
console.log(`reproduction.json: ${paper.length} paper runs, ${oursByKey.size} of ours, ${alns.length} ALNS runs, ${copied} ALNS solutions`);
