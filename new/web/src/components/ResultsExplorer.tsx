"use client";

import { useMemo, useState } from "react";
import { configuration, experimentLabel } from "@/lib/data";
import { useTokens } from "@/lib/theme";
import { groupBy, isNum, mean } from "@/lib/stats";
import { METRICS, type Metric, type Row } from "@/lib/types";
import { BoxChart, ChartCard, LineChart, ScatterChart } from "./charts";
import { DataTable, type Column } from "./DataTable";
import RouteBrowser from "./RouteBrowser";
import { useWorkspace } from "./Shell";
import { Caption, Chips, Details, FadeSwap, Field, Hero, Kpi, KpiRow, Loading, MultiSelect, Note, Page, Panel, Segmented, Select, Tabs } from "./ui";

export const RECORD_COLUMNS: Column<Row>[] = [
  { key: "problemName", label: "Instance", value: (r) => r.problemName },
  { key: "numCustomers", label: "Customers", value: (r) => r.numCustomers, numeric: true },
  { key: "algorithm", label: "Algorithm", value: (r) => r.algorithm },
  { key: "source", label: "Source", value: (r) => r.source },
  { key: "vehicleFileID", label: "Vehicle", value: (r) => r.vehicleFileID, numeric: true },
  { key: "numUAVs", label: "UAVs", value: (r) => r.numUAVs, numeric: true },
  { key: "Etype", label: "Etype", value: (r) => r.Etype, numeric: true },
  { key: "cutoffTime", label: "Limit (s)", value: (r) => r.cutoffTime, numeric: true },
  { key: "outcome", label: "Outcome", value: (r) => r.outcome },
  { key: "ofv", label: "Makespan (s)", value: (r) => r.ofv, numeric: true },
  { key: "totalTime", label: "Runtime (s)", value: (r) => r.totalTime, numeric: true },
  { key: "numUAVcust", label: "UAV cust.", value: (r) => r.numUAVcust, numeric: true },
  { key: "numTruckCust", label: "Truck cust.", value: (r) => r.numTruckCust, numeric: true },
  { key: "waitingTruck", label: "Truck wait (s)", value: (r) => r.waitingTruck, numeric: true },
  { key: "waitingUAV", label: "UAV wait (s)", value: (r) => r.waitingUAV, numeric: true },
  { key: "isOptimal", label: "isOptimal", value: (r) => r.isOptimal, numeric: true },
  { key: "bestBound", label: "Best bound", value: (r) => r.bestBound, numeric: true },
  { key: "strategy", label: "Strategy", value: (r) => r.strategy },
  { key: "timestamp", label: "Timestamp", value: (r) => r.timestamp },
];

const TABS = ["Performance", "Detailed records", "Saved routes"] as const;

export default function ResultsExplorer({ mode }: { mode: "ours" | "paper" }) {
  const { data, sizes } = useWorkspace();
  if (!data) return <Page>{heroFor(mode)}<Loading /></Page>;
  return <Explorer mode={mode} rows={data.results} inventory={data.inventory} sizes={sizes} />;
}

function heroFor(mode: "ours" | "paper") {
  return mode === "ours" ? (
    <Hero title="Every experiment, in context." subtitle="Explore the proposed Gurobi-assisted heuristic: recorded outcomes, runtime against quality, and saved delivery routes. Browsing never runs the optimizer." />
  ) : (
    <Hero title="The reference benchmark." subtitle="Archived original-method results (three-phase heuristic and IP), kept separate from local experiments. Provenance is the repository archive; publication tables have not been independently verified." tags={["Archive provenance"]} />
  );
}

function Explorer({ mode, rows, inventory, sizes }: { mode: "ours" | "paper"; rows: Row[]; inventory: { problemName: string; numCustomers: number | null; locations: boolean; truckTravel: boolean; savedSolutions: number; issue: string }[]; sizes: number[] }) {
  const base = useMemo(() => rows.filter((r) => (mode === "ours" ? r.cohort === "proposed" : r.cohort !== "proposed")), [rows, mode]);
  const experiments = useMemo(() => [...new Set(base.map(experimentLabel))].sort(), [base]);
  const [chosen, setChosen] = useState<string[]>(() => experiments.filter((e) => (mode === "ours" ? !e.includes("No-Gurobi") : e.includes("archive"))));
  const [configs, setConfigs] = useState<string[]>([]);
  const [instances, setInstances] = useState<string[]>([]);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Performance");
  const [metric, setMetric] = useState<Metric>("ofv");
  const [outcome, setOutcome] = useState<"All" | "Recorded solutions" | "No valid solution">("All");
  const [routeInstance, setRouteInstance] = useState("");
  const { series: palette } = useTokens();

  const scoped = useMemo(() => base.filter((r) => chosen.includes(experimentLabel(r)) && sizes.includes(r.numCustomers ?? -1)), [base, chosen, sizes]);
  const configOptions = useMemo(() => [...new Set(scoped.map(configuration))].sort(), [scoped]);
  const instanceOptions = useMemo(() => [...new Set(scoped.map((r) => r.problemName))].sort(), [scoped]);
  const df = useMemo(() => scoped.filter((r) => (!configs.length || configs.includes(configuration(r))) && (!instances.length || instances.includes(r.problemName))), [scoped, configs, instances]);
  const solved = df.filter((r) => r.solved);
  const runtimes = solved.map((r) => r.totalTime).filter((v): v is number => isNum(v) && v >= 0);

  const colorOf = (label: string) => palette[(experiments.indexOf(label) + (mode === "ours" ? 0 : 1)) % palette.length];
  const present = [...new Set(solved.map(experimentLabel))].sort();
  const sizeCats = sizes.filter((s) => df.some((r) => r.numCustomers === s));
  const values = (r: Row) => r[metric] as number | null;

  const boxSeries = present.map((label) => {
    const byN = groupBy(
      solved.filter((r) => experimentLabel(r) === label && isNum(values(r)) && values(r)! >= 0),
      (r) => String(r.numCustomers),
    );
    return { name: label, color: colorOf(label), values: Object.fromEntries([...byN].map(([k, v]) => [k, v.map((r) => values(r)!)])) };
  });
  const trendSeries = boxSeries.map((s) => ({ ...s, values: Object.fromEntries(Object.entries(s.values).map(([k, v]) => [k, v.length ? mean(v) : null])) }));
  const scatter = present.map((label) => ({
    name: label,
    color: colorOf(label),
    values: solved.filter((r) => experimentLabel(r) === label && isNum(r.totalTime) && r.totalTime > 0 && isNum(r.ofv)).map((r) => ({ x: r.totalTime!, y: r.ofv!, label: `${r.problemName} · ${r.numCustomers} customers · ${configuration(r)}` })),
  }));

  const routeOptions = instanceOptions.length ? instanceOptions : [];
  const routeValue = routeOptions.includes(routeInstance) ? routeInstance : routeOptions[0];
  const shownRecords = outcome === "All" ? df : df.filter((r) => r.solved === (outcome === "Recorded solutions"));
  const available = inventory.filter((b) => sizes.includes(b.numCustomers ?? -1));
  const withRecords = new Set(df.map((r) => r.problemName));

  return (
    <Page>
      {heroFor(mode)}

      <Panel title="Scope" subtitle={mode === "ours" ? "Summary and runner files can describe different runs of the same experiment. They stay separate records; pooled counts describe records, not unique benchmark performance." : "Local reruns of the original methods (performance_summary.csv) are kept apart from the archive and are off by default."}>
        <div className="flex flex-col gap-4">
          <Field label="Experiments (algorithm · source file)">
            <Chips options={experiments} value={chosen} onChange={setChosen} />
          </Field>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Experiment configuration (empty = all)">
              <MultiSelect options={configOptions} value={configs} onChange={setConfigs} />
            </Field>
            <Field label="Benchmark instance (empty = all)">
              <MultiSelect options={instanceOptions} value={instances} onChange={setInstances} />
            </Field>
          </div>
        </div>
      </Panel>

      <KpiRow>
        <Kpi label="Recorded runs" value={df.length} detail="All recorded rows in scope; repeated experiments are retained." />
        <Kpi label="Recorded solutions" value={solved.length} detail="Rows with a positive finite objective. This is not an independent feasibility proof." tone="mint" />
        <Kpi label="No valid solution" value={df.length - solved.length} detail="Failed status or invalid objective. Experiments that were never run are not counted as failures." tone="orange" />
        <Kpi label="Mean runtime" value={runtimes.length ? mean(runtimes) : null} suffix=" s" digits={2} detail="Mean of the recorded runtime measurements. Hardware and software differ across files, so runtime is descriptive only." tone="violet" />
      </KpiRow>

      {df.length === 0 ? (
        <Note>No recorded runs match these filters. Pick at least one experiment and customer count.</Note>
      ) : (
        <Panel>
          <div className="flex flex-col gap-5">
            <Tabs tabs={TABS} value={tab} onChange={setTab} />
            <FadeSwap k={tab}>
              {tab === "Performance" && (
                <>
                  <Field label="Performance metric" className="max-w-xs">
                    <Select value={metric} options={Object.keys(METRICS) as Metric[]} onChange={setMetric} format={(m) => METRICS[m]} />
                  </Field>
                  <ChartCard title="Recorded distribution by benchmark size" subtitle={`${METRICS[metric]} · box = interquartile range, white line = median`} legend={boxSeries}>
                    <BoxChart categories={sizeCats} series={boxSeries} yLabel={METRICS[metric]} />
                  </ChartCard>
                  <div className="grid gap-5 xl:grid-cols-2">
                    <ChartCard title="Runtime versus solution quality" subtitle="Each point is one recorded run" legend={scatter}>
                      <ScatterChart series={scatter} xLabel="Runtime (s)" yLabel="Makespan (s)" />
                    </ChartCard>
                    <ChartCard title="Mean recorded metric across problem sizes" subtitle="Mixed configurations may remain in scope" legend={trendSeries}>
                      <LineChart categories={sizeCats} series={trendSeries} yLabel={METRICS[metric]} height={320} />
                    </ChartCard>
                  </div>
                </>
              )}
              {tab === "Detailed records" && (
                <>
                  <Segmented options={["All", "Recorded solutions", "No valid solution"] as const} value={outcome} onChange={setOutcome} />
                  <DataTable rows={shownRecords} columns={RECORD_COLUMNS} name={`${mode}_records`} />
                  <Note>isOptimal is an optimality flag, not feasibility validation. bestBound = -1 means no bound was recorded. Validation dictionaries, when saved, appear with the saved routes.</Note>
                </>
              )}
              {tab === "Saved routes" &&
                (routeValue ? (
                  <>
                    <Field label="Instance to inspect" className="max-w-md">
                      <Select value={routeValue} options={routeOptions} onChange={setRouteInstance} format={(v) => `${v} · ${df.find((r) => r.problemName === v)?.numCustomers ?? "?"} customers`} />
                    </Field>
                    <RouteBrowser instance={routeValue} kind={mode === "ours" ? "proposed" : "original"} />
                  </>
                ) : (
                  <Note>No instance in scope.</Note>
                ))}
            </FadeSwap>
          </div>
        </Panel>
      )}

      <Details summary="Benchmark availability and coverage">
        <Caption>Benchmarks without selected records are missing results, not unsolved runs.</Caption>
        <div className="mt-3">
          <DataTable
            name={`${mode}_inventory`}
            rows={available}
            columns={[
              { key: "problemName", label: "Instance", value: (b) => b.problemName },
              { key: "numCustomers", label: "Customers", value: (b) => b.numCustomers, numeric: true },
              { key: "locations", label: "Locations", value: (b) => b.locations },
              { key: "truckTravel", label: "Truck travel", value: (b) => b.truckTravel },
              { key: "savedSolutions", label: "Saved solutions", value: (b) => b.savedSolutions, numeric: true },
              { key: "has", label: "Has selected record", value: (b) => withRecords.has(b.problemName) },
              { key: "issue", label: "Issue", value: (b) => b.issue },
            ]}
          />
        </div>
      </Details>
    </Page>
  );
}
