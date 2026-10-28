import type { Metric, Row } from "./types";

// Strict: every recorded configuration flag must match.
export const STRICT_KEYS = [
  "problemName",
  "numCustomers",
  "vehicleFileID",
  "numUAVs",
  "numTrucks",
  "requireTruckAtDepot",
  "requireDriver",
  "Etype",
  "cutoffTime",
  "ITER",
] as const;

// Relaxed: same benchmark and fleet, ignoring endurance model, time limit and flags.
export const RELAXED_KEYS = ["problemName", "numCustomers", "vehicleFileID", "numUAVs"] as const;

export type MatchRule = "strict" | "relaxed";

export type Winner = "Proposed" | "Archive" | "Tie" | "Not comparable";

export type Pair = {
  key: string;
  problemName: string;
  numCustomers: number | null;
  vehicleFileID: number | null;
  numUAVs: number | null;
  ours: Row | null;
  archive: Row | null;
  oursRuns: number;
  archiveRuns: number;
  status: string;
  comparable: boolean;
  improvement: number | null;
  winner: Winner;
};

const rank = (r: Row) => (r.solved && r.ofv !== null ? r.ofv : Infinity);

// Repeated runs: keep the best positive makespan per exact configuration.
function best(rows: Row[], keys: readonly (keyof Row)[]) {
  const out = new Map<string, { row: Row; runs: number }>();
  rows.forEach((r, i) => {
    const unknown = keys.some((k) => r[k] === null || r[k] === undefined);
    // Unknown configurations stay in the audit but never match each other.
    const key = unknown ? `unknown-${r.source}-${i}` : keys.map((k) => r[k]).join("|");
    const seen = out.get(key);
    if (!seen) out.set(key, { row: r, runs: 1 });
    else {
      seen.runs++;
      if (rank(r) < rank(seen.row)) seen.row = r;
    }
  });
  return out;
}

export function pairResults(ours: Row[], archive: Row[], metric: Metric, rule: MatchRule): Pair[] {
  const keys = rule === "strict" ? STRICT_KEYS : RELAXED_KEYS;
  const left = best(ours, keys);
  const right = best(archive, keys);
  const higherIsBetter = metric === "numUAVcust";
  const pairs: Pair[] = [];

  for (const key of new Set([...left.keys(), ...right.keys()])) {
    const a = left.get(key);
    const b = right.get(key);
    const ref = (a ?? b)!.row;
    let status = a && b ? "Paired configuration" : a ? "No compatible archive run" : "No compatible proposed run";
    const comparable = Boolean(a && b && a.row.solved && b.row.solved);
    if (a && b && !comparable) status = "Matching config; missing solution";

    let improvement: number | null = null;
    let winner: Winner = "Not comparable";
    const x = a?.row[metric] as number | null | undefined;
    const y = b?.row[metric] as number | null | undefined;
    if (comparable && typeof x === "number" && typeof y === "number" && x >= 0 && y >= 0) {
      const delta = higherIsBetter ? x - y : y - x;
      // A zero reference value has no defined percentage.
      improvement = y !== 0 ? (100 * delta) / y : null;
      winner = delta > 1e-6 ? "Proposed" : delta < -1e-6 ? "Archive" : "Tie";
    }

    pairs.push({
      key,
      problemName: ref.problemName,
      numCustomers: ref.numCustomers,
      vehicleFileID: ref.vehicleFileID,
      numUAVs: ref.numUAVs,
      ours: a?.row ?? null,
      archive: b?.row ?? null,
      oursRuns: a?.runs ?? 0,
      archiveRuns: b?.runs ?? 0,
      status,
      comparable,
      improvement,
      winner,
    });
  }
  return pairs.sort((p, q) => (p.numCustomers ?? 0) - (q.numCustomers ?? 0) || p.problemName.localeCompare(q.problemName));
}
