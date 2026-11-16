"use client";

import { ReactNode, useState } from "react";
import { useWorkspace } from "./Shell";
import { DataTable, type Column } from "./DataTable";
import { Field, Hero, Kpi, KpiRow, Loading, Note, Page, Panel, Select, cx } from "./ui";
import { METHOD_LABEL, METHODS, SIZES, STATUS_LABEL, UAV_COUNTS, VEHICLE_LABEL, runKey, type Method, type OurRun, type PaperRun, type Status } from "@/lib/types";

// ------------------------------------------------------------
// Shared helpers
// ------------------------------------------------------------

const fmt = (v: number | null | undefined, digits = 2) => (v === null || v === undefined || !Number.isFinite(v) ? "—" : v.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits }));
const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

type Filters = { method: Method | "All"; vehicle: number | "All"; uavs: number | "All" };
const ALL: Filters = { method: "All", vehicle: "All", uavs: "All" };

function useFilters() {
  const [f, setF] = useState<Filters>(ALL);
  const { sizes } = useWorkspace();
  const keep = (r: { method: Method; vehicleFileID: number | null; numUAVs: number | null; numCustomers: number | null }) =>
    (f.method === "All" || r.method === f.method) &&
    (f.vehicle === "All" || r.vehicleFileID === f.vehicle) &&
    (f.uavs === "All" || r.numUAVs === f.uavs) &&
    sizes.includes(r.numCustomers ?? -1);
  return { f, setF, keep };
}

function FilterBar({ f, setF }: { f: Filters; setF: (f: Filters) => void }) {
  return (
    <div className="reveal grid grid-cols-1 gap-3 sm:grid-cols-3">
      <Field label="Method">
        <Select value={f.method} options={["All", ...METHODS] as const} onChange={(method) => setF({ ...f, method })} format={(m) => (m === "All" ? "All methods" : METHOD_LABEL[m])} />
      </Field>
      <Field label="Vehicle file (drone type)">
        <Select value={f.vehicle} options={["All", 101, 102, 103, 104] as const} onChange={(vehicle) => setF({ ...f, vehicle })} format={(v) => (v === "All" ? "All vehicle files" : `${v} · ${VEHICLE_LABEL[v]}`)} />
      </Field>
      <Field label="Number of UAVs">
        <Select value={f.uavs} options={["All", ...UAV_COUNTS] as const} onChange={(uavs) => setF({ ...f, uavs })} format={(u) => (u === "All" ? "All UAV counts" : `${u} UAV${u === 1 ? "" : "s"}`)} />
      </Field>
    </div>
  );
}

const STATUS_STYLE: Record<Status, string> = {
  solved: "bg-mint/10 text-mint border-mint/30",
  time_capped: "bg-amber/10 text-amber border-amber/30",
  license_needed: "bg-orange/10 text-orange border-orange/30",
  error: "bg-rose/10 text-rose border-rose/30",
  not_run: "bg-panel-2 text-muted border-line",
};

function Badge({ className, children }: { className: string; children: ReactNode }) {
  return <span className={cx("rounded-full border px-2 py-0.5 text-xs font-semibold whitespace-nowrap", className)}>{children}</span>;
}

export const StatusBadge = ({ status }: { status: Status }) => <Badge className={STATUS_STYLE[status]}>{STATUS_LABEL[status]}</Badge>;

const baseColumns = <T extends PaperRun>(): Column<T>[] => [
  { key: "problem", label: "Problem", value: (r) => r.problemName },
  { key: "cust", label: "Customers", value: (r) => r.numCustomers, numeric: true },
  { key: "method", label: "Method", value: (r) => METHOD_LABEL[r.method] },
  { key: "veh", label: "Vehicle file", value: (r) => r.vehicleFileID },
  { key: "uavs", label: "UAVs", value: (r) => r.numUAVs, numeric: true },
];

// Table grouped by method and customer count.
function GroupTable({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className="w-full min-w-max text-left text-sm">
        <thead className="bg-panel-2 text-xs tracking-wide text-muted uppercase">
          <tr>
            {head.map((h, i) => (
              <th key={h} className={cx("px-3 py-2.5 font-semibold whitespace-nowrap", i > 1 && "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line odd:bg-panel even:bg-panel-2/40">
              {r.map((c, j) => (
                <td key={j} className={cx("px-3 py-2 whitespace-nowrap", j > 1 && "text-right tabular-nums")}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function groups<T extends { method: Method; numCustomers: number | null }>(rows: T[]) {
  const out: { method: Method; size: number; rows: T[] }[] = [];
  for (const method of METHODS)
    for (const size of SIZES) {
      const g = rows.filter((r) => r.method === method && r.numCustomers === size);
      if (g.length) out.push({ method, size, rows: g });
    }
  return out;
}

function Frame({ title, subtitle, tags, children }: { title: string; subtitle: string; tags: string[]; children: (ctx: ReturnType<typeof useWorkspace> & { data: NonNullable<ReturnType<typeof useWorkspace>["data"]> }) => ReactNode }) {
  const ws = useWorkspace();
  return (
    <Page>
      <Hero title={title} subtitle={subtitle} tags={tags} />
      {ws.data ? children({ ...ws, data: ws.data }) : !ws.error && <Loading />}
    </Page>
  );
}

// ------------------------------------------------------------
// Paper results
// ------------------------------------------------------------

export function PaperResults() {
  const { f, setF, keep } = useFilters();
  return (
    <Frame title="Paper results" subtitle="The results Murray & Raj (2019) published with their code, read from old/performance_summary_archive.csv. Every run solves one problem with one vehicle file (drone type) and one number of UAVs." tags={["Murray & Raj 2019", "1,920 runs"]}>
      {({ data }) => {
        const rows = data.paper.filter(keep);
        const ip = rows.filter((r) => r.method === "IP");
        return (
          <>
            <FilterBar f={f} setF={setF} />
            <KpiRow>
              <Kpi label="Runs shown" value={rows.length} detail="Paper runs matching the filters and the customer-count filter in the sidebar." />
              <Kpi label="Problems" value={new Set(rows.map((r) => r.problemName)).size} tone="violet" detail="Distinct benchmark problems among the runs shown." />
              <Kpi label="IP runs proven optimal" value={ip.filter((r) => r.isOptimal).length} tone="mint" detail={`Of ${ip.length} exact-model runs shown. The rest hit the paper's 1-hour time limit, so their makespan is the best found, not proven optimal.`} />
              <Kpi label="Average makespan (s)" value={mean(rows.map((r) => r.ofv ?? NaN).filter(Number.isFinite))} digits={1} tone="orange" detail="Makespan = time until every package is delivered and every vehicle is back at the depot. Lower is better." />
            </KpiRow>
            <Panel title="Summary by method and size" subtitle="The exact model (IP) was only run on the 8-customer problems; the heuristic on all sizes.">
              <GroupTable
                head={["Method", "Customers", "Runs", "Proven optimal", "Avg makespan (s)", "Avg runtime (s)"]}
                rows={groups(rows).map((g) => [
                  METHOD_LABEL[g.method],
                  g.size,
                  g.rows.length,
                  g.method === "IP" ? g.rows.filter((r) => r.isOptimal).length : "—",
                  fmt(mean(g.rows.map((r) => r.ofv ?? NaN).filter(Number.isFinite)), 1),
                  fmt(mean(g.rows.map((r) => r.totalTime ?? NaN).filter(Number.isFinite)), 2),
                ])}
              />
            </Panel>
            <Panel title="All paper runs">
              <DataTable
                name="paper_results"
                rows={rows}
                columns={[
                  ...baseColumns<PaperRun>(),
                  { key: "ofv", label: "Makespan (s)", value: (r) => r.ofv, numeric: true },
                  { key: "opt", label: "Proven optimal", value: (r) => (r.method === "IP" ? r.isOptimal : null) },
                  { key: "time", label: "Runtime (s)", value: (r) => r.totalTime, numeric: true },
                  { key: "uavc", label: "UAV customers", value: (r) => r.numUAVcust, numeric: true },
                  { key: "trc", label: "Truck customers", value: (r) => r.numTruckCust, numeric: true },
                ]}
              />
            </Panel>
          </>
        );
      }}
    </Frame>
  );
}

// ------------------------------------------------------------
// Our results
// ------------------------------------------------------------

const STATUSES: Status[] = ["solved", "time_capped", "license_needed", "error", "not_run"];
const BAR: Record<Status, string> = { solved: "bg-mint", time_capped: "bg-amber", license_needed: "bg-orange", error: "bg-rose", not_run: "bg-line-strong" };

function StatusBar({ rows }: { rows: OurRun[] }) {
  return (
    <div className="flex h-2.5 w-40 overflow-hidden rounded-full bg-panel-2" aria-hidden="true">
      {STATUSES.map((s) => {
        const n = rows.filter((r) => r.status === s).length;
        return n ? <span key={s} className={BAR[s]} style={{ width: `${(100 * n) / rows.length}%` }} /> : null;
      })}
    </div>
  );
}

export function OurResults() {
  const { f, setF, keep } = useFilters();
  return (
    <Frame title="Our results" subtitle="The paper's original code (old/) re-run by us on the same 1,920 settings, using the free size-limited Gurobi license. Runs whose model is too large for that license are marked License needed." tags={["Re-run of the original code", "Free Gurobi license"]}>
      {({ data }) => {
        const rows = data.ours.filter(keep);
        const count = (s: Status) => rows.filter((r) => r.status === s).length;
        return (
          <>
            <Note tone="warn">
              <b>Free license limit:</b> Gurobi&apos;s free license only accepts models up to 2,000 variables and 2,000 constraints. When a run hits that limit we stop that group (method, customer count, UAV count) and mark the rest <b>License needed</b>. Exact-model (IP) runs are capped at 60 s instead of the paper&apos;s 3,600 s; runs that stop at the cap without proving optimality are marked <b>Time-capped</b>.
            </Note>
            <FilterBar f={f} setF={setF} />
            <KpiRow>
              <Kpi label="Solved" value={count("solved")} tone="mint" detail="Runs that finished with the free license." />
              <Kpi label="License needed" value={count("license_needed")} tone="orange" detail="Gurobi refused these: the model is larger than the free license allows. A full (academic) license is needed." />
              <Kpi label="Time-capped" value={count("time_capped")} tone="violet" detail="Exact-model runs stopped at our 60 s cap before proving optimality. The paper allowed 1 hour." />
              <Kpi label="Not run yet / errors" value={count("not_run") + count("error")} detail="Runs the batch has not reached yet, plus any that crashed." />
            </KpiRow>
            <Panel title="Status by method and size">
              <GroupTable
                head={["Method", "Customers", "Runs", "Solved", "Time-capped", "License needed", "Not run / error", ""]}
                rows={groups(rows).map((g) => {
                  const c = (s: Status) => g.rows.filter((r) => r.status === s).length;
                  return [METHOD_LABEL[g.method], g.size, g.rows.length, c("solved"), c("time_capped"), c("license_needed"), c("not_run") + c("error"), <StatusBar key="b" rows={g.rows} />];
                })}
              />
            </Panel>
            <Panel title="All our runs">
              <DataTable
                name="our_results"
                rows={rows}
                columns={[
                  ...baseColumns<OurRun>(),
                  { key: "status", label: "Status", value: (r) => STATUS_LABEL[r.status], render: (r) => <StatusBadge status={r.status} /> },
                  { key: "ofv", label: "Makespan (s)", value: (r) => r.ofv, numeric: true },
                  { key: "opt", label: "Proven optimal", value: (r) => (r.method === "IP" && r.ofv !== null ? r.isOptimal : null) },
                  { key: "time", label: "Runtime (s)", value: (r) => r.totalTime, numeric: true },
                  { key: "msg", label: "Note", value: (r) => r.message },
                ]}
              />
            </Panel>
          </>
        );
      }}
    </Frame>
  );
}

// ------------------------------------------------------------
// Compare
// ------------------------------------------------------------

type Verdict = "Match" | "Within 1%" | "Different" | "Not comparable";
type Pair = { paper: PaperRun; ours: OurRun; diff: number | null; pct: number | null; verdict: Verdict; reason: string };

// Same makespan up to 0.01 s (files print 6 decimals; tiny rounding differences are expected).
const MATCH_TOLERANCE = 0.01;

function pairUp(paper: PaperRun[], ours: OurRun[]): Pair[] {
  const byKey = new Map(ours.map((o) => [runKey(o), o]));
  return paper.map((p) => {
    const o = byKey.get(runKey(p))!;
    if (p.ofv === null || o.ofv === null) return { paper: p, ours: o, diff: null, pct: null, verdict: "Not comparable", reason: STATUS_LABEL[o.status] };
    const diff = o.ofv - p.ofv;
    const pct = (100 * diff) / p.ofv;
    const verdict: Verdict = Math.abs(diff) <= MATCH_TOLERANCE ? "Match" : Math.abs(pct) <= 1 ? "Within 1%" : "Different";
    return { paper: p, ours: o, diff, pct, verdict, reason: o.status === "time_capped" ? "Ours time-capped" : "" };
  });
}

const VERDICT_STYLE: Record<Verdict, string> = {
  Match: "bg-mint/10 text-mint border-mint/30",
  "Within 1%": "bg-cyan/10 text-cyan border-cyan/30",
  Different: "bg-rose/10 text-rose border-rose/30",
  "Not comparable": "bg-panel-2 text-muted border-line",
};

export function Compare() {
  const { f, setF, keep } = useFilters();
  return (
    <Frame title="Compare" subtitle="Each of our runs next to the paper's run with the same problem, method, vehicle file and number of UAVs. A run matches when both makespans agree to within 0.01 s." tags={["Paper vs ours", "Makespan"]}>
      {({ data }) => {
        const pairs = pairUp(data.paper, data.ours).filter((p) => keep(p.paper));
        const compared = pairs.filter((p) => p.pct !== null);
        const n = (v: Verdict) => pairs.filter((p) => p.verdict === v).length;
        const optimalBoth = compared.filter((p) => p.paper.method === "IP" && p.paper.isOptimal && p.ours.isOptimal);
        return (
          <>
            <FilterBar f={f} setF={setF} />
            <KpiRow>
              <Kpi label="Compared runs" value={compared.length} detail={`Runs where both the paper and we have a makespan, out of ${pairs.length} shown. The rest are license needed, time-capped without a result, or not run yet.`} />
              <Kpi label="Exact matches" value={n("Match")} tone="mint" detail="Our makespan equals the paper's to within 0.01 s." />
              <Kpi label="Within 1%" value={n("Within 1%")} tone="violet" detail="Not an exact match, but less than 1% apart." />
              <Kpi label="Avg |difference| (%)" value={mean(compared.map((p) => Math.abs(p.pct!)))} digits={3} suffix="%" tone="orange" detail="Average absolute percentage difference in makespan over the compared runs." />
            </KpiRow>
            {optimalBoth.length > 0 && (
              <Note tone={optimalBoth.every((p) => p.verdict === "Match") ? "ok" : "warn"}>
                <b>Proven-optimal check:</b> {optimalBoth.filter((p) => p.verdict === "Match").length} of {optimalBoth.length} exact-model runs that both the paper and we proved optimal have the same makespan. An optimal value does not depend on the computer or Gurobi version, so these must match.
              </Note>
            )}
            <Panel title="Summary by method and size">
              <GroupTable
                head={["Method", "Customers", "Runs", "Compared", "Exact match", "Within 1%", "Different", "Avg |diff| %", "Max |diff| %", "Not comparable"]}
                rows={groups(pairs.map((p) => ({ ...p, method: p.paper.method, numCustomers: p.paper.numCustomers }))).map((g) => {
                  const c = g.rows.filter((p) => p.pct !== null);
                  const abs = c.map((p) => Math.abs(p.pct!));
                  const k = (v: Verdict) => g.rows.filter((p) => p.verdict === v).length;
                  return [METHOD_LABEL[g.method], g.size, g.rows.length, c.length, k("Match"), k("Within 1%"), k("Different"), fmt(mean(abs), 3), abs.length ? fmt(Math.max(...abs), 3) : "—", k("Not comparable")];
                })}
              />
            </Panel>
            <Panel title="Run by run">
              <DataTable
                name="paper_vs_ours"
                rows={pairs}
                columns={[
                  { key: "problem", label: "Problem", value: (p) => p.paper.problemName },
                  { key: "cust", label: "Customers", value: (p) => p.paper.numCustomers, numeric: true },
                  { key: "method", label: "Method", value: (p) => METHOD_LABEL[p.paper.method] },
                  { key: "veh", label: "Vehicle file", value: (p) => p.paper.vehicleFileID },
                  { key: "uavs", label: "UAVs", value: (p) => p.paper.numUAVs, numeric: true },
                  { key: "pofv", label: "Paper makespan (s)", value: (p) => p.paper.ofv, numeric: true },
                  { key: "oofv", label: "Our makespan (s)", value: (p) => p.ours.ofv, numeric: true },
                  { key: "diff", label: "Difference (s)", value: (p) => p.diff, numeric: true },
                  { key: "pct", label: "Difference (%)", value: (p) => (p.pct === null ? null : Number(p.pct.toFixed(4))), numeric: true },
                  { key: "verdict", label: "Result", value: (p) => p.verdict, render: (p) => <Badge className={VERDICT_STYLE[p.verdict]}>{p.verdict}</Badge> },
                  { key: "why", label: "Note", value: (p) => p.reason },
                ]}
              />
            </Panel>
          </>
        );
      }}
    </Frame>
  );
}
