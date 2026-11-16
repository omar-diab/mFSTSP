// Builds public/data/reproduction.json from:
//   old/performance_summary_archive.csv   (the paper's results, Murray & Raj 2019)
//   old/reproduction/our_results.csv      (our re-run of the same code, made by old/reproduce.py)
// Runs before `npm run dev` and `npm run build`.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OLD = path.resolve(ROOT, "..", "..", "old");
const ARCHIVE = path.join(OLD, "performance_summary_archive.csv");
const OURS = path.join(OLD, "reproduction", "our_results.csv");
const OUT = path.join(ROOT, "public", "data", "reproduction.json");

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

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify({ generatedAt: new Date().toISOString(), paper, ours }));
console.log(`reproduction.json: ${paper.length} paper runs, ${oursByKey.size} of ours`);
