"use client";

import { useMemo, useState } from "react";
import { configuration, experimentLabel } from "@/lib/data";
import { pairResults, type MatchRule, type Pair } from "@/lib/compare";
import { groupBy, isNum, mean } from "@/lib/stats";
import { METRICS, type Metric, type Row } from "@/lib/types";
import { BarChart, BoxChart, ChartCard, LineChart, RankedBars, histogram } from "./charts";
import { DataTable, WinnerBadge, type Column } from "./DataTable";
import { useTokens } from "@/lib/theme";
import { useWorkspace } from "./Shell";
import { Caption, FadeSwap, Field, Hero, Kpi, KpiRow, Loading, MultiSelect, Note, Page, Panel, Select, Tabs } from "./ui";

const TABS = ["Performance overview", "Distributions & coverage", "Pairing audit"] as const;
const RULES = { "Strict (all recorded flags)": "strict", "Same instance + fleet (relaxed)": "relaxed" } as const;

export default function Comparison() {
  const { data, sizes } = useWorkspace();
  const hero = <Hero title="Evidence before improvement." subtitle="Compare the proposed Gurobi-assisted heuristic with archived reference runs under matching benchmark conditions. Every score stays attached to its configuration and source." />;
  if (!data) return <Page>{hero}<Loading /></Page>;
  return <Dashboard rows={data.results} sizes={sizes} hero={hero} />;
}

function Dashboard({ rows, sizes, hero }: { rows: Row[]; sizes: number[]; hero: React.ReactNode }) {
  const proposed = useMemo(() => rows.filter((r) => r.cohort === "proposed"), [rows]);
  const archived = useMemo(() => rows.filter((r) => r.cohort === "archive"), [rows]);
  const experiments = useMemo(() => [...new Set(proposed.map(experimentLabel))].sort((a, b) => Number(a.includes("No-Gurobi")) - Number(b.includes("No-Gurobi")) || b.localeCompare(a)), [proposed]);
  const baselines = useMemo(() => [...new Set(archived.map((r) => r.algorithm))].sort(), [archived]);

  const [experiment, setExperiment] = useState(experiments[0] ?? "");
  const [baseline, setBaseline] = useState(baselines.find((b) => b.includes("Heuristic")) ?? baselines[0] ?? "");
  const [metric, setMetric] = useState<Metric>("ofv");
  const [ruleLabel, setRuleLabel] = useState<keyof typeof RULES>("Strict (all recorded flags)");
  const [instances, setInstances] = useState<string[]>([]);
  const [vehicles, setVehicles] = useState<string[]>([]);
  const [fleets, setFleets] = useState<string[]>([]);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Performance overview");
  const rule: MatchRule = RULES[ruleLabel];
  const tk = useTokens();
  const OURS = tk.cyan;
  const THEIRS = tk.orange;
  const WIN = { Proposed: tk.mint, Archive: tk.orange, Tie: tk.violet, "Not comparable": tk["line-strong"] };

  const scope = (r: Row) =>
    sizes.includes(r.numCustomers ?? -1) &&
    (!instances.length || instances.includes(r.problemName)) &&
    (!vehicles.length || vehicles.includes(String(r.vehicleFileID))) &&
    (!fleets.length || fleets.includes(String(r.numUAVs)));
  const ours = useMemo(() => proposed.filter((r) => experimentLabel(r) === experiment && scope(r)), [proposed, experiment, sizes, instances, vehicles, fleets]); // eslint-disable-line react-hooks/exhaustive-deps
  const archive = useMemo(() => archived.filter((r) => r.algorithm === baseline && scope(r)), [archived, baseline, sizes, instances, vehicles, fleets]); // eslint-disable-line react-hooks/exhaustive-deps
  const pairs = useMemo(() => pairResults(ours, archive, metric, rule), [ours, archive, metric, rule]);
  const valid = pairs.filter((p) => p.comparable && p.winner !== "Not comparable");
  const wins = valid.filter((p) => p.winner === "Proposed").length;
  const losses = valid.filter((p) => p.winner === "Archive").length;
  const ties = valid.filter((p) => p.winner === "Tie").length;
  const improvements = valid.map((p) => p.improvement).filter(isNum);
  const strictPairs = useMemo(() => (rule === "relaxed" ? pairResults(ours, archive, metric, "strict").filter((p) => p.comparable).length : null), [rule, ours, archive, metric]);

  const allInstances = useMemo(() => [...new Set([...proposed, ...archived].filter((r) => sizes.includes(r.numCustomers ?? -1)).map((r) => r.problemName))].sort(), [proposed, archived, sizes]);
  const vehicleOptions = [...new Set(archived.map((r) => String(r.vehicleFileID)))].sort();
  const fleetOptions = [...new Set(archived.map((r) => String(r.numUAVs)))].sort();

  const metricOf = (r: Row | null) => (r ? (r[metric] as number | null) : null);
  const sizeCats = sizes.filter((s) => [...ours, ...archive].some((r) => r.numCustomers === s));

  // Descriptive views, used when no compatible pairs exist and on the coverage tab.
  const cohorts = [
    { name: "Proposed", color: OURS, rows: ours },
    { name: "Archive", color: THEIRS, rows: archive },
  ];
  const descriptive = cohorts.map((c) => {
    const byN = groupBy(
      c.rows.filter((r) => r.solved && isNum(metricOf(r)) && metricOf(r)! >= 0),
      (r) => String(r.numCustomers),
    );
    return { name: c.name, color: c.color, values: Object.fromEntries([...byN].map(([k, v]) => [k, v.map((r) => metricOf(r)!)])) };
  });
  const descriptiveMean = descriptive.map((s) => ({ ...s, values: Object.fromEntries(Object.entries(s.values).map(([k, v]) => [k, mean(v)])) }));

  const pairedMeans = [
    { name: "Proposed", color: OURS, values: Object.fromEntries([...groupBy(valid, (p) => String(p.numCustomers))].map(([k, v]) => [k, mean(v.map((p) => metricOf(p.ours)!))])) },
    { name: "Archive", color: THEIRS, values: Object.fromEntries([...groupBy(valid, (p) => String(p.numCustomers))].map(([k, v]) => [k, mean(v.map((p) => metricOf(p.archive)!))])) },
  ];
  const improvementBySize = [{ name: "Mean paired improvement", color: tk.mint, values: Object.fromEntries([...groupBy(valid.filter((p) => isNum(p.improvement)), (p) => String(p.numCustomers))].map(([k, v]) => [k, mean(v.map((p) => p.improvement!))])) }];

  const hist = histogram(improvements);
  const histSeries = (["Proposed", "Archive", "Tie"] as const).map((w) => ({
    name: w,
    color: WIN[w],
    values: Object.fromEntries(hist.labels.map((l) => [l, 0])) as Record<string, number>,
  }));
  valid.forEach((p) => {
    if (!isNum(p.improvement) || p.winner === "Not comparable") return;
    const s = histSeries.find((h) => h.name === p.winner)!;
    s.values[hist.labels[hist.index(p.improvement)]]++;
  });

  const outcomes = [...new Set([...ours, ...archive].map((r) => r.outcome))];
  const coverage = cohorts.flatMap((c) =>
    outcomes.map((o, i) => ({
      name: `${c.name} · ${o}`,
      // Secondary outcomes use a lighter tint of the cohort colour.
      color: c.name === "Proposed" ? (i ? tk.s6 : OURS) : i ? tk.rose : THEIRS,
      values: Object.fromEntries(sizeCats.map((n) => [`${n} · ${c.name}`, c.rows.filter((r) => r.numCustomers === n && r.outcome === o).length])),
    })),
  );
  const coverageCats = sizeCats.flatMap((n) => [`${n} · Proposed`, `${n} · Archive`]);

  const audit = useMemo(() => {
    const g = groupBy([...ours.map((r) => ({ cohort: "Proposed", r })), ...archive.map((r) => ({ cohort: "Archive", r }))], (x) => `${x.cohort}|${configuration(x.r)}`);
    return [...g].map(([k, v]) => ({ cohort: k.split("|")[0], configuration: configuration(v[0].r), recorded_runs: v.length }));
  }, [ours, archive]);

  const pairColumns: Column<Pair>[] = [
    { key: "problemName", label: "Instance", value: (p) => p.problemName },
    { key: "n", label: "Customers", value: (p) => p.numCustomers, numeric: true },
    { key: "veh", label: "Vehicle", value: (p) => p.vehicleFileID, numeric: true },
    { key: "uav", label: "UAVs", value: (p) => p.numUAVs, numeric: true },
    { key: "status", label: "Status", value: (p) => p.status },
    { key: "ours", label: `Proposed ${METRICS[metric]}`, value: (p) => metricOf(p.ours), numeric: true },
    { key: "arch", label: `Archive ${METRICS[metric]}`, value: (p) => metricOf(p.archive), numeric: true },
    { key: "imp", label: "Improvement (%)", value: (p) => p.improvement, numeric: true, render: (p) => (isNum(p.improvement) ? <span className={p.improvement >= 0 ? "text-mint" : "text-orange"}>{p.improvement >= 0 ? "+" : ""}{p.improvement.toFixed(2)}%</span> : <span className="text-muted/60">—</span>) },
    { key: "winner", label: "Winner", value: (p) => p.winner, render: (p) => <WinnerBadge winner={p.winner} /> },
    { key: "or", label: "Proposed runs", value: (p) => p.oursRuns, numeric: true },
    { key: "ar", label: "Archive runs", value: (p) => p.archiveRuns, numeric: true },
    { key: "oc", label: "Proposed config", value: (p) => (p.ours ? configuration(p.ours) : null) },
    { key: "ac", label: "Archive config", value: (p) => (p.archive ? configuration(p.archive) : null) },
  ];

  const winner = wins === losses ? "Tie" : wins > losses ? "Proposed" : "Archive";

  return (
    <Page>
      {hero}
      <Panel title="What to compare">
        <div className="flex flex-col gap-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <Field label="Proposed experiment">
              <Select value={experiment} options={experiments} onChange={setExperiment} />
            </Field>
            <Field label="Archived reference algorithm">
              <Select value={baseline} options={baselines} onChange={setBaseline} />
            </Field>
            <Field label="Compare metric">
              <Select value={metric} options={Object.keys(METRICS) as Metric[]} onChange={setMetric} format={(m) => METRICS[m]} />
            </Field>
            <Field label="Matching rule">
              <Select value={ruleLabel} options={Object.keys(RULES) as (keyof typeof RULES)[]} onChange={setRuleLabel} />
            </Field>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <Field label="Instances (empty = all)">
              <MultiSelect options={allInstances} value={instances} onChange={setInstances} />
            </Field>
            <Field label="Vehicle type">
              <MultiSelect options={vehicleOptions} value={vehicles} onChange={setVehicles} />
            </Field>
            <Field label="UAV fleet size">
              <MultiSelect options={fleetOptions} value={fleets} onChange={setFleets} />
            </Field>
          </div>
          <Caption>
            {rule === "strict"
              ? "Matching key: instance, customer count, vehicle type, UAV count, truck count, depot requirement, driver requirement, endurance model (Etype), cutoff and iteration setting."
              : "Relaxed key: instance, customer count, vehicle type and UAV count only. Endurance model, time limit and flags may differ."}{" "}
            Repeated runs: best makespan per configuration; recorded-run counts stay in the export.
          </Caption>
        </div>
      </Panel>

      {rule === "relaxed" && (
        <Note tone="warn">
          Relaxed matching pairs runs whose conditions differ: the proposed runs use Etype 3 with a 3,600 s limit, while the archived heuristic uses Etype 1 with a 5 s limit. Treat these results as a descriptive side-by-side, not a controlled improvement claim.{" "}
          {strictPairs !== null && `Under strict matching this scope has ${strictPairs} compatible pairs.`}
        </Note>
      )}

      <KpiRow>
        <Kpi label="Compatible solutions" value={valid.length} detail="Both sides have a positive finite objective and the selected matching key matches." />
        <Kpi label="Proposed wins" value={wins} detail="Wins count only for the selected metric within compatible pairs." tone="mint" />
        <Kpi label="Archive wins" value={losses} detail="Runtime environments differ; descriptive runtime is not a controlled speed benchmark." tone="orange" />
        <Kpi label="Mean improvement" value={improvements.length ? mean(improvements) : null} suffix="%" digits={2} detail="Mean per-pair percentage. Lower-is-better metrics use (archive − proposed) / archive; UAV customers reverse the sign. Zero reference values are undefined." tone="violet" />
      </KpiRow>

      {(metric === "numUAVcust" || metric === "numTruckCust") && <Note>Service counts describe how work is split, not overall solution quality. More UAV customers is treated only as a utilization preference.</Note>}

      <Panel>
        <div className="flex flex-col gap-5">
          <Tabs tabs={TABS} value={tab} onChange={setTab} />
          <FadeSwap k={tab + rule + metric}>
            {tab === "Performance overview" &&
              (valid.length === 0 ? (
                <>
                  <Note tone="warn">
                    No compatible solved pairs in this scope, so an improvement figure or a best-algorithm ranking would be unsupported.
                    {rule === "strict" && " Proposed runs use vehicle 101, 3 UAVs, Etype 3 and a 3,600 s limit; the archived heuristic uses Etype 1 and a 5 s limit. Switch the matching rule to relaxed for a labelled side-by-side."}
                  </Note>
                  <ChartCard title="Descriptive distributions only · configurations differ" subtitle={METRICS[metric]} legend={descriptive}>
                    <BoxChart categories={sizeCats} series={descriptive} yLabel={METRICS[metric]} />
                  </ChartCard>
                  <ChartCard title="Descriptive mean by size · unmatched conditions, no improvement inference" legend={descriptiveMean}>
                    <LineChart categories={sizeCats} series={descriptiveMean} yLabel={METRICS[metric]} />
                  </ChartCard>
                </>
              ) : (
                <>
                  <Note tone="ok">
                    Best by compatible-pair win count for {METRICS[metric]}: <b>{winner}</b> ({wins} proposed, {losses} archive, {ties} ties).
                  </Note>
                  <div className="grid gap-5 xl:grid-cols-2">
                    <ChartCard title="Mean paired value by problem size" subtitle={`${METRICS[metric]} over compatible pairs`} legend={pairedMeans}>
                      <BarChart categories={sizeCats.filter((n) => valid.some((p) => p.numCustomers === n))} series={pairedMeans} yLabel={METRICS[metric]} />
                    </ChartCard>
                    <ChartCard title="Mean paired improvement by problem size" subtitle="Positive = proposed better">
                      <LineChart categories={sizeCats.filter((n) => valid.some((p) => p.numCustomers === n))} series={improvementBySize} yLabel="Improvement (%)" zeroLine />
                    </ChartCard>
                  </div>
                  <ChartCard title="Improvement per compatible pair" subtitle="Green = proposed better, orange = archive better" legend={[{ name: "Proposed better", color: WIN.Proposed }, { name: "Archive better", color: WIN.Archive }, { name: "Tie", color: WIN.Tie }]}>
                    <RankedBars items={valid.filter((p) => isNum(p.improvement)).map((p) => ({ label: `${p.problemName} · ${p.numCustomers} customers`, value: p.improvement!, color: WIN[p.winner], detail: `proposed ${metricOf(p.ours)?.toFixed(1)} vs archive ${metricOf(p.archive)?.toFixed(1)}` }))} yLabel="Improvement (%)" />
                  </ChartCard>
                </>
              ))}
            {tab === "Distributions & coverage" && (
              <>
                {valid.length > 0 && (
                  <ChartCard title="Compatible-pair improvement distribution" subtitle="Improvement (%) bins, stacked by winner" legend={histSeries}>
                    <BarChart categories={hist.labels} series={histSeries} stacked yLabel="Pairs" />
                  </ChartCard>
                )}
                <ChartCard title="Recorded outcome coverage" subtitle="Runs per customer count and cohort" legend={coverage.filter((s) => Object.values(s.values).some(Boolean))}>
                  <BarChart categories={coverageCats} series={coverage} stacked yLabel="Runs" rotate />
                </ChartCard>
                <Note>A missing record is not the same as an unsolved run. Unsolved status is shown only when it is recorded or an objective is missing or invalid.</Note>
              </>
            )}
            {tab === "Pairing audit" && (
              <>
                <DataTable rows={audit} name="configuration_audit" columns={[{ key: "c", label: "Cohort", value: (a) => a.cohort }, { key: "cfg", label: "Configuration", value: (a) => a.configuration }, { key: "n", label: "Recorded runs", value: (a) => a.recorded_runs, numeric: true }]} />
                <Note tone="warn">The legacy frontend_data comparison files pick best runs per instance without requiring equal configurations. Their headline improvements are not reused here.</Note>
              </>
            )}
            <div>
              <h3 className="mb-3 text-sm font-semibold">
                Pairing table · {pairs.length} configurations in scope ({valid.length} compatible)
              </h3>
              <DataTable rows={pairs} columns={pairColumns} name="comparison_pairs" />
            </div>
          </FadeSwap>
        </div>
      </Panel>
    </Page>
  );
}
