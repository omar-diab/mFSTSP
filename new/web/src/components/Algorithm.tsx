"use client";

import { ReactNode, useEffect, useMemo, useState } from "react";
import { useWorkspace } from "./Shell";
import { DataTable } from "./DataTable";
import { Caption, Details, Field, Hero, Kpi, KpiRow, Loading, Note, Page, Panel, Select, cx } from "./ui";
import { SIZES, UAV_COUNTS, VEHICLE_LABEL, alnsKey, type AlnsRun, type AlnsSolution, type PaperRun, type ReproductionData } from "@/lib/types";

// ------------------------------------------------------------
// Helpers
// ------------------------------------------------------------

const fmt = (v: number | null | undefined, digits = 2) => (v === null || v === undefined || !Number.isFinite(v) ? "—" : v.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits }));
const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
const median = (xs: number[]) => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const finite = (xs: (number | null | undefined)[]) => xs.filter((x): x is number => x !== null && x !== undefined && Number.isFinite(x));

// Same makespan up to 0.01 s counts as a tie.
const TIE = 0.01;

type Filters = { vehicle: number | "All"; uavs: number | "All" };

function useFilters() {
  const [f, setF] = useState<Filters>({ vehicle: "All", uavs: "All" });
  const { sizes } = useWorkspace();
  const keep = (r: { vehicleFileID: number | null; numUAVs: number | null; numCustomers: number | null }) =>
    (f.vehicle === "All" || r.vehicleFileID === f.vehicle) && (f.uavs === "All" || r.numUAVs === f.uavs) && sizes.includes(r.numCustomers ?? -1);
  return { f, setF, keep };
}

function FilterBar({ f, setF }: { f: Filters; setF: (f: Filters) => void }) {
  return (
    <div className="reveal grid grid-cols-1 gap-3 sm:grid-cols-2">
      <Field label="Vehicle file (drone type)">
        <Select value={f.vehicle} options={["All", 101, 102, 103, 104] as const} onChange={(vehicle) => setF({ ...f, vehicle })} format={(v) => (v === "All" ? "All vehicle files" : `${v} · ${VEHICLE_LABEL[v]}`)} />
      </Field>
      <Field label="Number of UAVs">
        <Select value={f.uavs} options={["All", ...UAV_COUNTS] as const} onChange={(uavs) => setF({ ...f, uavs })} format={(u) => (u === "All" ? "All UAV counts" : `${u} UAV${u === 1 ? "" : "s"}`)} />
      </Field>
    </div>
  );
}

function Badge({ className, children }: { className: string; children: ReactNode }) {
  return <span className={cx("rounded-full border px-2 py-0.5 text-xs font-semibold whitespace-nowrap", className)}>{children}</span>;
}

// wrap: let long text columns wrap instead of widening the table.
function SimpleTable({ head, rows, firstCols = 1, wrap = false }: { head: ReactNode[]; rows: ReactNode[][]; firstCols?: number; wrap?: boolean }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className={cx("w-full text-left text-sm", wrap ? "min-w-[640px]" : "min-w-max")}>
        <thead className="bg-panel-2 text-xs tracking-wide text-muted uppercase">
          <tr>
            {head.map((h, i) => (
              <th key={i} className={cx("px-3 py-2.5 font-semibold whitespace-nowrap", i >= firstCols && "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line odd:bg-panel even:bg-panel-2/40">
              {r.map((c, j) => (
                <td key={j} className={cx("px-3 py-2 align-top", j >= firstCols ? "text-right tabular-nums whitespace-nowrap" : "whitespace-normal")}>
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

function Frame({ title, subtitle, tags, children }: { title: string; subtitle: string; tags: string[]; children: (data: ReproductionData) => ReactNode }) {
  const ws = useWorkspace();
  return (
    <Page>
      <Hero title={title} subtitle={subtitle} tags={tags} />
      {ws.data ? children(ws.data) : !ws.error && <Loading />}
    </Page>
  );
}

const Code = ({ children }: { children: ReactNode }) => <code className="code">{children}</code>;

// ------------------------------------------------------------
// Page 1: Our algorithm (what it is and how it works)
// ------------------------------------------------------------

const FLOW: { title: string; text: string }[] = [
  { title: "1 · Start", text: "Truck-only tour (nearest neighbour + or-opt + 2-opt on road times), then customers move to UAVs one at a time, hardest first, while the makespan drops." },
  { title: "2 · Destroy", text: "Pick a destroy operator by its adaptive weight and unassign q customers (q random, 1 to 30% of customers, at most 15)." },
  { title: "3 · Repair", text: "Pick a repair operator by its weight and put every removed customer back: on the truck, or on a UAV sortie with a launch and recovery stop." },
  { title: "4 · Schedule", text: "The schedule evaluator times the whole plan with the paper's rules (queues, driver, endurance with hovering) and returns the makespan, or rejects it." },
  { title: "5 · Accept", text: "New best → keep it (local search first). Better than current → move. Worse → simulated annealing may still move. Infeasible → never kept." },
  { title: "6 · Learn", text: "Operators earn points (best 33, better 15, accepted 5, rejected 0). Every 50 iterations their weights move 10% toward their average score." },
];

const DESTROY: [string, string, string][] = [
  ["random", "Random removal", "q customers chosen at random, truck or UAV. Keeps the search moving."],
  ["worst", "Worst-contribution removal", "Customers that cost the most: long truck detours, and sorties with launch, recovery and hovering time."],
  ["related", "Related-customer removal", "A random customer and the customers closest to it by truck travel time, so a whole area is rebuilt."],
  ["high_wait", "High-wait removal", "Sorties where the UAV hovers or the truck waits, and the truck stops where that happens."],
  ["expensive_sortie", "Expensive-sortie removal", "Sorties that use the largest share of their battery, to try other UAVs and stops."],
  ["mode_change", "Mode-change removal", "Random customers that the repair must try to serve the other way: truck ↔ UAV."],
  ["segment", "Segment removal", "A run of consecutive truck stops, with the sorties that start or end there."],
];

const REPAIR: [string, string, string][] = [
  ["greedy", "Greedy best insertion", "Removed customers in random order, each at its best option."],
  ["constrained_first", "Constrained-first insertion", "Customers with the fewest UAV options first, so they are not left with no good place."],
  ["regret", "Regret-2 insertion", "First the customer whose best and second-best options differ most: the one that loses most by waiting."],
];

const RULES: [string, string][] = [
  ["Every customer once", "Served by the truck or by exactly one UAV sortie, never both, never neither."],
  ["Sorties", "A UAV leaves the truck at one stop, serves one customer and lands on the truck at a later stop (any later stop, also the depot at the end)."],
  ["Payload", "Parcels over the UAV's capacity (5 lbs) go by truck."],
  ["Endurance (Etype 1)", "The paper's non-linear energy model (endurance_calculator.py, ported line by line). Time from launch to recovery, including hovering while it waits for the truck, must fit the battery."],
  ["One operation at a time", "At a stop the driver does the delivery, each launch (60 s) and each recovery (30 s) one after another. The truck leaves when all are done."],
  ["UAV reuse", "A UAV can start a new sortie only after it has been recovered."],
  ["Makespan", "Time when the truck is back at the depot with every UAV recovered. Lower is better."],
];

function OperatorTable({ rows, totals }: { rows: [string, string, string][]; totals: Record<string, number> }) {
  const all = Object.values(totals).reduce((a, b) => a + b, 0);
  return (
    <SimpleTable
      head={["Operator", "What it does", "Times used", "Share"]}
      firstCols={2}
      wrap
      rows={rows.map(([key, name, text]) => [
        <span key="n" className="font-semibold">
          {name}
        </span>,
        <span key="t" className="text-muted">
          {text}
        </span>,
        totals[key] ? totals[key].toLocaleString() : "—",
        all && totals[key] ? `${((100 * totals[key]) / all).toFixed(1)}%` : "—",
      ])}
    />
  );
}

export function AlgorithmOverview() {
  return (
    <Frame title="Our algorithm: ALNS" subtitle="An Adaptive Large Neighborhood Search for the multiple flying sidekicks TSP (one truck, up to four UAVs). It needs no Gurobi license and follows the same rules as the paper's model, so its makespans can be compared with the paper's." tags={["Adaptive Large Neighborhood Search", "No Gurobi needed", "Same rules as the paper"]}>
      {(data) => {
        const v = data.validation;
        const ip = v.filter((r) => r.method === "IP");
        const all = v.reduce((a, r) => ({ plans: a.plans + r.plans, feasible: a.feasible + r.feasible, verified: a.verified + r.verified }), { plans: 0, feasible: 0, verified: 0 });
        const opt = ip.reduce((a, r) => ({ n: a.n + r.provenOptimal, exact: a.exact + r.provenOptimalExact }), { n: 0, exact: 0 });
        const minOpt = finite(ip.map((r) => r.provenOptimalMinDiffPct));
        return (
          <>
            <Note>
              This is our own proposed method, not the paper&apos;s three-phase heuristic. Code: <Code>new/mfstsp_alns/</Code> · run one problem with <Code>python run_alns.py &lt;problem&gt; &lt;vehicle&gt; &lt;UAVs&gt;</Code> · run all with <Code>python run_alns_benchmark.py</Code>.
            </Note>

            <Panel title="How one ALNS run works" subtitle="The loop repeats steps 2–6 until the time limit. The best feasible solution is stored apart from the current one and never gets worse.">
              <ol className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {FLOW.map((s) => (
                  <li key={s.title} className="rounded-xl border border-line bg-panel-2/50 p-4">
                    <div className="text-sm font-bold text-cyan">{s.title}</div>
                    <p className="mt-1.5 text-sm leading-relaxed text-muted">{s.text}</p>
                  </li>
                ))}
              </ol>
            </Panel>

            <Panel title="Rules every solution must follow" subtitle="Taken from the paper's model (solve_mfstsp_IP.py) with the settings of every paper run: Etype 1, driver required, truck ends at the depot.">
              <SimpleTable head={["Rule", "Meaning"]} firstCols={2} wrap rows={RULES.map(([a, b]) => [<b key="a">{a}</b>, <span key="b" className="text-muted">{b}</span>])} />
            </Panel>

            <Panel title="Destroy operators" subtitle="Times used: total over every recorded ALNS run.">
              <OperatorTable rows={DESTROY} totals={data.operatorTotals.destroy} />
            </Panel>

            <Panel title="Repair operators" subtitle="Every option is first ranked by a quick estimate; only the best few are timed by the full schedule evaluator, and only that evaluator can call an option feasible.">
              <OperatorTable rows={REPAIR} totals={data.operatorTotals.repair} />
            </Panel>

            <Panel title="Schedule evaluator: the most important part" subtitle="ALNS is only as good as the timing it trusts. The evaluator turns a truck route plus sorties into exact start and end times.">
              <div className="grid grid-cols-1 gap-4 text-sm leading-relaxed text-muted lg:grid-cols-2">
                <div className="flex flex-col gap-2">
                  <p>It walks along the truck route. At each stop it puts the delivery, the recoveries and the launches in a queue for the driver, one at a time. A recovery waits until its UAV is there; a UAV recovered at a stop is relaunched only after its recovery.</p>
                  <p>Which operation goes first is a choice, so it tries 36 priority policies (class order × launch order × &quot;relaunch right after recovery&quot;) and keeps the best. When a UAV would run out of battery, it launches that UAV last, recovers it first, or holds the launch back, as the paper&apos;s exact model does.</p>
                </div>
                <div className="flex flex-col gap-2">
                  <p>It is a heuristic for the timing, not an exact solver. To be sure it is right, a second, independent checker (<Code>solution/verify.py</Code>) re-reads every time and checks each rule. Every ALNS result is passed through it.</p>
                  <p>During the search a faster set of 5 policies is used; the reported makespan is always re-timed with all 36.</p>
                </div>
              </div>
            </Panel>

            <Panel title="Check: our evaluator on the paper's own solutions" subtitle="We took every solution the paper saved, kept its truck route and sorties, and let our evaluator do the timing. If our rules were too loose we would beat the proven optima; if too strict, their plans would come out infeasible.">
              <KpiRow>
                <Kpi label="Paper plans re-timed" value={all.plans} detail="Every saved paper solution: 320 exact-model (IP) and 1,600 heuristic runs." />
                <Kpi label="Feasible and verified" value={all.verified} tone="mint" detail={`Plans our evaluator could time without breaking any rule, confirmed by the independent checker. ${all.plans - all.feasible} paper heuristic plans could not be timed by our list scheduler (it is conservative; the paper uses an exact model for timing).`} />
                <Kpi label="Proven optima matched" value={opt.exact} tone="violet" detail={`Of ${opt.n} runs the paper proved optimal, our evaluator gives the same makespan (within 0.01%) on these. On the others it is slightly slower.`} />
                <Kpi label="Lowest gap to a proven optimum" value={minOpt.length ? Math.min(...minOpt) : null} digits={4} suffix="%" tone="orange" detail="Never below 0: our evaluator never claims a faster schedule than the proven optimum, so it does not break any of the paper's rules." />
              </KpiRow>
              <div className="mt-4">
                <SimpleTable
                  head={["Paper method", "Customers", "Plans", "Feasible", "Verified", "Same makespan (±0.01%)", "Avg diff %", "Max diff %"]}
                  firstCols={1}
                  rows={v.map((r) => [r.method === "IP" ? "Exact model (IP)" : "Paper's heuristic", r.numCustomers, r.plans, r.feasible, r.verified, r.exact, fmt(r.meanDiffPct, 3), fmt(r.maxDiffPct, 2)])}
                />
              </div>
              <Caption>Diff = (our makespan − paper makespan) / paper makespan. A few heuristic plans come out slightly faster with our timing (min {fmt(Math.min(...finite(v.filter((r) => r.method === "Heuristic").map((r) => r.minDiffPct))), 2)}%) because the paper&apos;s heuristic stopped its timing model after 5 s. Source: new/results/alns/evaluator_validation.csv.</Caption>
            </Panel>

            <Panel title="Settings used for the recorded runs" subtitle="All in new/mfstsp_alns/alns/config.py; every run saves its settings with its solution.">
              <SimpleTable
                head={["Setting", "Value"]}
                firstCols={1}
                rows={[
                  ["Time limit per run (8 / 10 / 25 / 50 / 100 customers)", "5 / 5 / 10 / 20 / 45 s"],
                  ["Customers removed per iteration", "1 to 30% (max 15)"],
                  ["Options fully timed per insertion (by size)", "20 / 20 / 10 / 6 / 6"],
                  ["Battery repairs per plan while searching (by size)", "40 / 40 / 20 / 3 / 3"],
                  ["Max stops between launch and recovery", "8"],
                  ["Weight update", "every 50 iterations, reaction 0.1"],
                  ["Simulated annealing start", "a 3% worse move is accepted with probability 0.5; cools to 0.2% of that"],
                  ["Local search", "on every new best and every 25 iterations"],
                  ["Random seed", "1 (one run per setting)"],
                ]}
              />
            </Panel>

            <Details summary="What this algorithm is not">
              <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-muted">
                <li>It is not the paper&apos;s three-phase heuristic, and its operators are our design choices, not taken from Murray &amp; Raj.</li>
                <li>The schedule evaluator is a heuristic. It never breaks a rule, but it can miss the best timing of a plan.</li>
                <li>Runs use one seed each. Spread over several seeds is not measured yet.</li>
              </ul>
            </Details>
          </>
        );
      }}
    </Frame>
  );
}

// ------------------------------------------------------------
// Route viewer (results page)
// ------------------------------------------------------------

const UAV_COLORS = ["var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)"];

function useSolution(run: AlnsRun | null) {
  const [state, setState] = useState<{ key: string; sol: AlnsSolution | null; error: string | null }>({ key: "", sol: null, error: null });
  const key = run ? `${run.problemName}_${run.vehicleFileID}_${run.numUAVs}` : "";
  useEffect(() => {
    if (!key) return;
    let alive = true;
    fetch(`/data/alns/${key}.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
      })
      .then((sol) => alive && setState({ key, sol, error: null }))
      .catch((e) => alive && setState({ key, sol: null, error: String(e.message ?? e) }));
    return () => {
      alive = false;
    };
  }, [key]);
  return state.key === key ? state : { key, sol: null, error: null };
}

function RouteMap({ sol }: { sol: AlnsSolution }) {
  const W = 640;
  const H = 440;
  const pad = 28;
  const byId = new Map(sol.nodes.map((n) => [n.id, n]));
  const lat0 = mean(sol.nodes.map((n) => n.lat))!;
  const k = Math.cos((lat0 * Math.PI) / 180);
  const xs = sol.nodes.map((n) => n.lon * k);
  const ys = sol.nodes.map((n) => n.lat);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const s = Math.min((W - 2 * pad) / (x1 - x0 || 1), (H - 2 * pad) / (y1 - y0 || 1));
  const ox = (W - s * (x1 - x0)) / 2;
  const oy = (H - s * (y1 - y0)) / 2;
  const P = (id: number) => {
    const n = byId.get(id)!;
    return [ox + (n.lon * k - x0) * s, H - (oy + (n.lat - y0) * s)] as const;
  };
  const uavIds = [...new Set(sol.sorties.map((t) => t.uav))].sort((a, b) => a - b);
  const color = (u: number) => UAV_COLORS[Math.max(0, u - 2) % UAV_COLORS.length];
  const uavCustomers = new Set(sol.sorties.map((t) => t.customer));
  const truckPath = sol.truck_route.map((id) => P(id).join(",")).join(" ");
  return (
    <div className="flex flex-col gap-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-xl border border-line bg-[var(--scene-1)]" role="img" aria-label="Truck route and UAV sorties">
        <polyline points={truckPath} fill="none" stroke="var(--s1)" strokeWidth={2} strokeLinejoin="round" />
        {sol.sorties.map((t, i) => {
          const pts = [P(t.launch), P(t.customer), P(t.recovery)].map((p) => p.join(",")).join(" ");
          return (
            <polyline key={i} points={pts} fill="none" stroke={color(t.uav)} strokeWidth={1.6} strokeDasharray="5 4" strokeLinejoin="round">
              <title>{`UAV ${t.uav}: launch at ${t.launch === 0 ? "depot" : t.launch} → customer ${t.customer} → recovery at ${t.recovery === 0 ? "depot" : t.recovery}\nAirborne ${t.airborne.toFixed(0)} s of ${t.endurance.toFixed(0)} s, hover ${t.hover.toFixed(0)} s`}</title>
            </polyline>
          );
        })}
        {sol.nodes.map((n) => {
          const [x, y] = P(n.id);
          if (n.id === 0)
            return (
              <rect key={n.id} x={x - 7} y={y - 7} width={14} height={14} rx={2} fill="var(--depot)" stroke="var(--scene-1)" strokeWidth={2}>
                <title>Depot</title>
              </rect>
            );
          const drone = uavCustomers.has(n.id);
          return (
            <circle key={n.id} cx={x} cy={y} r={drone ? 5 : 5.5} fill={drone ? "var(--scene-1)" : "var(--s1)"} stroke={drone ? "var(--foreground)" : "var(--scene-1)"} strokeWidth={drone ? 1.6 : 2}>
              <title>{`Customer ${n.id} · ${drone ? "by UAV" : "by truck"} · parcel ${n.parcelLbs} lbs`}</title>
            </circle>
          );
        })}
      </svg>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-sm bg-[var(--depot)]" /> Depot
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-5 bg-[var(--s1)]" /> Truck route ({sol.truck_route.length - 2} truck customers)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-full border-[1.6px] border-foreground" /> UAV customer
        </span>
        {uavIds.map((u) => (
          <span key={u} className="flex items-center gap-1.5">
            <svg width="20" height="4" aria-hidden="true">
              <line x1="0" y1="2" x2="20" y2="2" stroke={color(u)} strokeWidth="2" strokeDasharray="5 3" />
            </svg>
            UAV {u}
          </span>
        ))}
      </div>
      <Caption>Straight lines between locations; the truck really drives on roads (its times come from the paper&apos;s road data). Hover a line or point for details.</Caption>
    </div>
  );
}

// Best makespan over the run (one series: no legend; the title names it).
function Convergence({ sol, runtime }: { sol: AlnsSolution; runtime: number | null }) {
  const h = sol.history;
  if (h.length < 2) return <Caption>The starting solution was already the best one found.</Caption>;
  const W = 640;
  const H = 200;
  const L = 64;
  const R = 12;
  const T = 12;
  const B = 30;
  // The x-axis spans the whole run, so it is visible when the best was found early.
  const tMax = Math.max(runtime ?? 0, ...h.map((p) => p.time), 0.001);
  const yMin = Math.min(...h.map((p) => p.makespan));
  const yMax = Math.max(...h.map((p) => p.makespan));
  const span = yMax - yMin || 1;
  const X = (t: number) => L + ((W - L - R) * t) / tMax;
  const Y = (m: number) => T + ((H - T - B) * (yMax - m)) / span;
  let d = `M${X(h[0].time)},${Y(h[0].makespan)}`;
  for (let i = 1; i < h.length; i++) d += ` H${X(h[i].time)} V${Y(h[i].makespan)}`;
  d += ` H${X(tMax)}`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Best makespan over time">
      {[yMin, (yMin + yMax) / 2, yMax].map((v) => (
        <g key={v}>
          <line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} stroke="var(--grid)" />
          <text x={L - 8} y={Y(v) + 4} textAnchor="end" fontSize="11" fill="var(--axis)">
            {v.toFixed(0)}
          </text>
        </g>
      ))}
      <text x={L} y={H - 8} fontSize="11" fill="var(--axis)">
        0 s
      </text>
      <text x={W - R} y={H - 8} textAnchor="end" fontSize="11" fill="var(--axis)">
        {tMax.toFixed(1)} s
      </text>
      <path d={d} fill="none" stroke="var(--s1)" strokeWidth={2} />
      {h.map((p, i) => (
        <circle key={i} cx={X(p.time)} cy={Y(p.makespan)} r={4} fill="var(--s1)" stroke="var(--panel)" strokeWidth={2}>
          <title>{`${p.time.toFixed(2)} s, iteration ${p.iteration}: ${p.makespan.toFixed(1)} s`}</title>
        </circle>
      ))}
    </svg>
  );
}

function RunViewer({ runs }: { runs: AlnsRun[] }) {
  const solved = useMemo(() => runs.filter((r) => r.ofv !== null).sort((a, b) => (a.numCustomers ?? 0) - (b.numCustomers ?? 0) || a.problemName.localeCompare(b.problemName) || (a.vehicleFileID ?? 0) - (b.vehicleFileID ?? 0) || (a.numUAVs ?? 0) - (b.numUAVs ?? 0)), [runs]);
  const [pick, setPick] = useState("");
  const run = solved.find((r) => alnsKey(r) === pick) ?? solved[0] ?? null;
  const { sol, error } = useSolution(run);
  if (!run) return <Caption>No solved runs match the filters.</Caption>;
  return (
    <div className="flex flex-col gap-4">
      <Field label="Run">
        <Select value={alnsKey(run)} options={solved.map(alnsKey)} onChange={setPick} format={(k) => {
          const r = solved.find((x) => alnsKey(x) === k)!;
          return `${r.numCustomers} customers · ${r.problemName} · vehicle ${r.vehicleFileID} · ${r.numUAVs} UAV${r.numUAVs === 1 ? "" : "s"} · ${fmt(r.ofv, 1)} s`;
        }} />
      </Field>
      {error && <Note tone="error">Could not load this solution ({error}).</Note>}
      {!sol && !error && <Loading label="Loading solution…" />}
      {sol && (
        <>
          <div className="grid grid-cols-1 gap-5 xl:grid-cols-[3fr_2fr]">
            <RouteMap sol={sol} />
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-2 gap-3 text-sm">
                {[
                  ["Makespan", `${fmt(sol.makespan, 1)} s`],
                  ["Start solution", `${fmt(run.initialOfv, 1)} s`],
                  ["Truck customers", run.numTruckCust],
                  ["UAV customers", run.numUAVcust],
                  ["Iterations", run.iterations?.toLocaleString()],
                  ["Verified", run.verified ? "Yes" : "No"],
                ].map(([k, v]) => (
                  <div key={String(k)} className="rounded-lg border border-line bg-panel-2/50 px-3 py-2">
                    <div className="text-xs text-muted">{k}</div>
                    <div className="font-semibold tabular-nums">{v}</div>
                  </div>
                ))}
              </div>
              <div>
                <div className="mb-1 text-sm font-semibold">Best makespan (s) during the run</div>
                <Convergence sol={sol} runtime={run.runtime} />
              </div>
            </div>
          </div>
          <DataTable
            name={`alns_sorties_${run.problemName}_${run.vehicleFileID}_${run.numUAVs}`}
            rows={sol.sorties}
            columns={[
              { key: "uav", label: "UAV", value: (t) => t.uav, numeric: true },
              { key: "l", label: "Launch at", value: (t) => (t.launch === 0 ? "Depot" : t.launch) },
              { key: "c", label: "Customer", value: (t) => t.customer, numeric: true },
              { key: "r", label: "Recovered at", value: (t) => (t.recovery === 0 ? "Depot" : t.recovery) },
              { key: "ls", label: "Launch start (s)", value: (t) => t.launch_start, numeric: true },
              { key: "rs", label: "Recovery start (s)", value: (t) => t.recovery_start, numeric: true },
              { key: "h", label: "Hover (s)", value: (t) => t.hover, numeric: true },
              { key: "a", label: "In the air (s)", value: (t) => t.airborne, numeric: true },
              { key: "e", label: "Endurance limit (s)", value: (t) => t.endurance, numeric: true },
              { key: "u", label: "Battery used", value: (t) => `${((100 * t.airborne) / t.endurance).toFixed(0)}%` },
            ]}
          />
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------
// Page 2: Our algorithm results
// ------------------------------------------------------------

const STATUS_STYLE: Record<string, string> = {
  solved: "bg-mint/10 text-mint border-mint/30",
  invalid: "bg-rose/10 text-rose border-rose/30",
  error: "bg-rose/10 text-rose border-rose/30",
  not_run: "bg-panel-2 text-muted border-line",
};

export function AlgorithmResults() {
  const { f, setF, keep } = useFilters();
  return (
    <Frame title="Our algorithm results" subtitle="ALNS run on the same 1,600 settings as the paper's heuristic: 100 problems × 4 vehicle files × 1–4 UAVs. Same rules as the paper (Etype 1 energy model, driver required, truck ends at the depot)." tags={["ALNS", "1,600 settings", "Verified schedules"]}>
      {(data) => {
        const paperH = data.paper.filter((p) => p.method === "Heuristic");
        const byKey = new Map(data.alns.map((r) => [alnsKey(r), r]));
        // One row per paper heuristic setting, so settings not run yet are visible.
        const rows: AlnsRun[] = paperH.filter(keep).map(
          (p) =>
            byKey.get(alnsKey(p)) ?? {
              problemName: p.problemName, numCustomers: p.numCustomers, vehicleFileID: p.vehicleFileID, numUAVs: p.numUAVs, etype: null, seed: null, timeLimit: null,
              status: "not_run", ofv: null, initialOfv: null, runtime: null, iterations: null, evaluations: null, numUAVcust: null, numTruckCust: null, waitingTruck: null, waitingUAV: null, verified: null, message: "", timestamp: "",
            },
        );
        const done = rows.filter((r) => r.status !== "not_run");
        const solved = rows.filter((r) => r.status === "solved");
        return (
          <>
            {done.length < rows.length && (
              <Note tone="warn">
                <b>Batch still running:</b> {done.length.toLocaleString()} of {rows.length.toLocaleString()} settings shown have a result. Press <b>Refresh recorded data</b> after <Code>npm run data</Code> to load new ones.
              </Note>
            )}
            <FilterBar f={f} setF={setF} />
            <KpiRow>
              <Kpi label="Solved and verified" value={solved.filter((r) => r.verified).length} tone="mint" detail={`Runs whose final schedule passed the independent checker, of ${done.length} finished runs shown.`} />
              <Kpi label="Average makespan (s)" value={mean(finite(solved.map((r) => r.ofv)))} digits={1} tone="orange" detail="Time until every package is delivered and every vehicle is back at the depot. Lower is better." />
              <Kpi label="Average runtime (s)" value={mean(finite(done.map((r) => r.runtime)))} digits={1} tone="violet" detail="Wall-clock seconds per run, including reading the data. Each run stops at its time limit (5–45 s by size)." />
              <Kpi label="Gain over the start solution" value={mean(finite(solved.map((r) => (r.initialOfv && r.ofv ? (100 * (r.initialOfv - r.ofv)) / r.initialOfv : null))))} digits={1} suffix="%" detail="How much ALNS shortened the makespan of its own starting solution, on average." />
            </KpiRow>

            <Panel title="Summary by customer count">
              <SimpleTable
                head={["Customers", "Settings", "Solved", "Verified", "Avg makespan (s)", "Avg runtime (s)", "Avg iterations", "Avg UAV customers", "Avg truck wait (s)", "Avg UAV hover (s)"]}
                rows={SIZES.filter((n) => rows.some((r) => r.numCustomers === n)).map((n) => {
                  const g = rows.filter((r) => r.numCustomers === n);
                  const s = g.filter((r) => r.status === "solved");
                  return [n, g.length, s.length, s.filter((r) => r.verified).length, fmt(mean(finite(s.map((r) => r.ofv))), 1), fmt(mean(finite(s.map((r) => r.runtime))), 1), fmt(mean(finite(s.map((r) => r.iterations))), 0), fmt(mean(finite(s.map((r) => r.numUAVcust))), 1), fmt(mean(finite(s.map((r) => r.waitingTruck))), 1), fmt(mean(finite(s.map((r) => r.waitingUAV))), 1)];
                })}
              />
              <Caption>Truck wait: time the truck stands at a stop with nothing to do, waiting for a UAV. UAV hover: time UAVs wait in the air for the truck or driver (it counts against the battery). These are our definitions; the paper computes its waiting times differently, so compare them only between our own runs.</Caption>
            </Panel>

            <Panel title="Look at one solution" subtitle="Truck route, UAV sorties and how the best makespan improved during the run.">
              <RunViewer runs={solved} />
            </Panel>

            <Panel title="All ALNS runs">
              <DataTable
                name="alns_results"
                rows={rows}
                columns={[
                  { key: "problem", label: "Problem", value: (r) => r.problemName },
                  { key: "cust", label: "Customers", value: (r) => r.numCustomers, numeric: true },
                  { key: "veh", label: "Vehicle file", value: (r) => r.vehicleFileID },
                  { key: "uavs", label: "UAVs", value: (r) => r.numUAVs, numeric: true },
                  { key: "status", label: "Status", value: (r) => r.status, render: (r) => <Badge className={STATUS_STYLE[r.status] ?? STATUS_STYLE.error}>{r.status === "not_run" ? "Not run yet" : r.status[0].toUpperCase() + r.status.slice(1)}</Badge> },
                  { key: "ofv", label: "Makespan (s)", value: (r) => r.ofv, numeric: true },
                  { key: "init", label: "Start makespan (s)", value: (r) => r.initialOfv, numeric: true },
                  { key: "time", label: "Runtime (s)", value: (r) => r.runtime, numeric: true },
                  { key: "it", label: "Iterations", value: (r) => r.iterations, numeric: true },
                  { key: "uavc", label: "UAV customers", value: (r) => r.numUAVcust, numeric: true },
                  { key: "trc", label: "Truck customers", value: (r) => r.numTruckCust, numeric: true },
                  { key: "ver", label: "Verified", value: (r) => r.verified },
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
// Page 3: ALNS vs paper
// ------------------------------------------------------------

type Verdict = "ALNS better" | "Tie" | "Paper better";
type Pair = { paper: PaperRun; alns: AlnsRun; ip: PaperRun | null; diff: number; pct: number; verdict: Verdict; ipGap: number | null };

const VERDICT_STYLE: Record<Verdict, string> = {
  "ALNS better": "bg-cyan/10 text-cyan border-cyan/30",
  Tie: "bg-panel-2 text-muted border-line",
  "Paper better": "bg-orange/10 text-orange border-orange/30",
};

function pairUp(data: ReproductionData): Pair[] {
  const alns = new Map(data.alns.filter((r) => r.ofv !== null && r.verified).map((r) => [alnsKey(r), r]));
  const ip = new Map(data.paper.filter((p) => p.method === "IP").map((p) => [alnsKey(p), p]));
  const out: Pair[] = [];
  for (const p of data.paper) {
    if (p.method !== "Heuristic" || p.ofv === null) continue;
    const a = alns.get(alnsKey(p));
    if (!a) continue;
    const diff = a.ofv! - p.ofv;
    const ipRun = ip.get(alnsKey(p)) ?? null;
    out.push({
      paper: p, alns: a, ip: ipRun, diff, pct: (100 * diff) / p.ofv,
      verdict: Math.abs(diff) <= TIE ? "Tie" : diff < 0 ? "ALNS better" : "Paper better",
      ipGap: ipRun && ipRun.isOptimal && ipRun.ofv ? (100 * (a.ofv! - ipRun.ofv)) / ipRun.ofv : null,
    });
  }
  return out;
}

// Average % difference per group. Diverging: left of 0 (ALNS better) and right of 0 (paper better).
function DiffBars({ groups }: { groups: { label: string; pct: number | null; n: number }[] }) {
  const shown = groups.filter((g) => g.pct !== null) as { label: string; pct: number; n: number }[];
  if (!shown.length) return null;
  const W = 720;
  const rowH = 30;
  const L = 170; // row labels + room for a value label left of the longest bar
  const R = 60;
  const H = shown.length * rowH + 28;
  const m = Math.max(1, ...shown.map((g) => Math.abs(g.pct)));
  const X = (v: number) => L + ((W - L - R) * (v + m)) / (2 * m);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-3xl" role="img" aria-label="Average makespan difference, ALNS vs paper">
      <line x1={X(0)} x2={X(0)} y1={4} y2={H - 22} stroke="var(--axis)" />
      <text x={X(-m)} y={H - 6} fontSize="11" fill="var(--axis)">
        ← ALNS shorter
      </text>
      <text x={X(m)} y={H - 6} fontSize="11" fill="var(--axis)" textAnchor="end">
        paper shorter →
      </text>
      {shown.map((g, i) => {
        const y = 6 + i * rowH;
        const x0 = Math.min(X(0), X(g.pct));
        const w = Math.max(2, Math.abs(X(g.pct) - X(0)));
        const better = g.pct < 0;
        return (
          <g key={g.label}>
            <text x={8} y={y + 14} fontSize="12" fill="var(--foreground)">
              {g.label}
            </text>
            <rect x={x0} y={y + 2} width={w} height={rowH - 10} rx={4} fill={better ? "var(--cyan)" : "var(--orange)"}>
              <title>{`${g.label}: ${g.pct >= 0 ? "+" : ""}${g.pct.toFixed(2)}% average over ${g.n} runs`}</title>
            </rect>
            <text x={better ? x0 - 6 : x0 + w + 6} y={y + 14} textAnchor={better ? "end" : "start"} fontSize="11" fill="var(--muted)">
              {`${g.pct >= 0 ? "+" : ""}${g.pct.toFixed(2)}%`}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function breakdown(pairs: Pair[], label: string, keyOf: (p: Pair) => number | null, values: readonly number[], name: (v: number) => string) {
  const rows = values
    .map((v) => {
      const g = pairs.filter((p) => keyOf(p) === v);
      if (!g.length) return null;
      const pct = g.map((p) => p.pct);
      const k = (x: Verdict) => g.filter((p) => p.verdict === x).length;
      return [name(v), g.length, k("ALNS better"), k("Tie"), k("Paper better"), fmt(mean(pct), 2), fmt(median(pct), 2), fmt(Math.min(...pct), 2), fmt(Math.max(...pct), 2), fmt(mean(finite(g.map((p) => p.alns.runtime))), 1), fmt(mean(finite(g.map((p) => p.paper.totalTime))), 1)];
    })
    .filter(Boolean) as ReactNode[][];
  return <SimpleTable head={[label, "Runs", "ALNS better", "Tie", "Paper better", "Avg diff %", "Median diff %", "Best %", "Worst %", "ALNS time (s)", "Paper time (s)"]} rows={rows} />;
}

export function AlgorithmCompare() {
  const { f, setF, keep } = useFilters();
  return (
    <Frame title="Our algorithm vs the paper" subtitle="Each ALNS run next to the paper's heuristic run with the same problem, vehicle file and number of UAVs. On the 8-customer problems we also compare with the paper's proven optimal values." tags={["ALNS vs Murray & Raj heuristic", "Makespan", "Lower is better"]}>
      {(data) => {
        const pairs = pairUp(data).filter((p) => keep(p.paper));
        const n = (v: Verdict) => pairs.filter((p) => p.verdict === v).length;
        const withOpt = pairs.filter((p) => p.ipGap !== null);
        const bySize = SIZES.map((s) => {
          const g = pairs.filter((p) => p.paper.numCustomers === s);
          return { label: `${s} customers`, pct: mean(g.map((p) => p.pct)), n: g.length };
        });
        return (
          <>
            <Note>
              <b>Diff % = (ALNS makespan − paper makespan) / paper makespan.</b> Negative means ALNS found a shorter delivery time. Only ALNS runs with a verified schedule are compared. A tie means the two makespans are within 0.01 s.
            </Note>
            <FilterBar f={f} setF={setF} />
            <KpiRow>
              <Kpi label="Compared runs" value={pairs.length} detail="Settings where both the paper's heuristic and our ALNS have a result (out of 1,600)." />
              <Kpi label="ALNS better" value={n("ALNS better")} tone="mint" detail={`ALNS found a shorter makespan. Ties: ${n("Tie")}. Paper better: ${n("Paper better")}.`} />
              <Kpi label="Average difference" value={mean(pairs.map((p) => p.pct))} digits={2} suffix="%" tone="orange" detail="Average of Diff % over the compared runs. Negative = ALNS shorter on average." />
              <Kpi label="Gap to proven optimum" value={mean(finite(withOpt.map((p) => p.ipGap)))} digits={3} suffix="%" tone="violet" detail={`Average distance of ALNS from the paper's proven optimal makespan, over ${withOpt.length} 8-customer runs where the exact model proved optimality. ${withOpt.filter((p) => (p.ipGap ?? 1) < 0.01).length} of them reach the optimum.`} />
            </KpiRow>

            <Panel title="Average difference by customer count" subtitle="Bars left of the line: ALNS shorter on average. Right: the paper's heuristic shorter.">
              <DiffBars groups={bySize} />
            </Panel>

            <Panel title="By customer count" subtitle="Runtime: ALNS has a fixed time limit per size (5/5/10/20/45 s). The paper's times were measured on the authors' computer in 2019, so they are only a rough guide.">
              {breakdown(pairs, "Customers", (p) => p.paper.numCustomers, SIZES, (v) => String(v))}
            </Panel>

            <Panel title="By drone type and by fleet size">
              <div className="flex flex-col gap-4">
                {breakdown(pairs, "Vehicle file", (p) => p.paper.vehicleFileID, [101, 102, 103, 104], (v) => `${v} · ${VEHICLE_LABEL[v]}`)}
                {breakdown(pairs, "UAVs", (p) => p.paper.numUAVs, UAV_COUNTS, (v) => String(v))}
              </div>
            </Panel>

            {withOpt.length > 0 && (
              <Panel title="8 customers: against the proven optimum" subtitle="The paper's exact model proved the optimal makespan for these runs. Nobody can beat it; the question is how close each heuristic gets.">
                <SimpleTable
                  head={["Method", "Runs", "Reached the optimum", "Avg gap %", "Worst gap %"]}
                  rows={[
                    ["Our ALNS", withOpt.length, withOpt.filter((p) => p.ipGap! < 0.01).length, fmt(mean(withOpt.map((p) => p.ipGap!)), 3), fmt(Math.max(...withOpt.map((p) => p.ipGap!)), 2)],
                    (() => {
                      const g = withOpt.map((p) => (100 * (p.paper.ofv! - p.ip!.ofv!)) / p.ip!.ofv!);
                      return ["Paper's heuristic", withOpt.length, g.filter((x) => x < 0.01).length, fmt(mean(g), 3), fmt(Math.max(...g), 2)];
                    })(),
                  ]}
                />
              </Panel>
            )}

            <Panel title="Run by run">
              <DataTable
                name="alns_vs_paper"
                rows={pairs}
                columns={[
                  { key: "problem", label: "Problem", value: (p) => p.paper.problemName },
                  { key: "cust", label: "Customers", value: (p) => p.paper.numCustomers, numeric: true },
                  { key: "veh", label: "Vehicle file", value: (p) => p.paper.vehicleFileID },
                  { key: "uavs", label: "UAVs", value: (p) => p.paper.numUAVs, numeric: true },
                  { key: "pofv", label: "Paper makespan (s)", value: (p) => p.paper.ofv, numeric: true },
                  { key: "aofv", label: "ALNS makespan (s)", value: (p) => p.alns.ofv, numeric: true },
                  { key: "diff", label: "Difference (s)", value: (p) => Number(p.diff.toFixed(2)), numeric: true },
                  { key: "pct", label: "Difference (%)", value: (p) => Number(p.pct.toFixed(3)), numeric: true },
                  { key: "verdict", label: "Result", value: (p) => p.verdict, render: (p) => <Badge className={VERDICT_STYLE[p.verdict]}>{p.verdict}</Badge> },
                  { key: "opt", label: "Proven optimum (s)", value: (p) => (p.ip?.isOptimal ? p.ip.ofv : null), numeric: true },
                  { key: "ptime", label: "Paper time (s)", value: (p) => p.paper.totalTime, numeric: true },
                  { key: "atime", label: "ALNS time (s)", value: (p) => p.alns.runtime, numeric: true },
                ]}
              />
            </Panel>

            <Details summary="How fair is this comparison?">
              <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-muted">
                <li>Same problems, drone types, fleet sizes and rules (Etype 1, driver, truck ends at the depot). Our schedule evaluator was checked on all of the paper&apos;s own solutions (see Our algorithm).</li>
                <li>Different computers and years: the paper&apos;s runtimes are from 2019 hardware. ALNS runs for a fixed time per size.</li>
                <li>One ALNS run (seed 1) per setting. With 320 settings per size the averages are meaningful, but the spread over seeds is not measured yet.</li>
                <li>The paper&apos;s waiting times use a different definition, so only makespans are compared here.</li>
              </ul>
            </Details>
          </>
        );
      }}
    </Frame>
  );
}
