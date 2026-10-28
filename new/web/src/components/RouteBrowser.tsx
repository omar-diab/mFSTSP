"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import gsap from "gsap";
import { useInstance } from "@/lib/data";
import { distances, project, vehicleColors, vehiclesOf } from "@/lib/playback";
import { fmt } from "@/lib/stats";
import type { InstanceData, SolutionFile } from "@/lib/types";
import { download } from "@/lib/csv";
import { useTokens } from "@/lib/theme";
import Scene3D, { vehicleStates } from "./Scene3D";
import { DataTable } from "./DataTable";
import { Button, Caption, Details, Field, FadeSwap, Kpi, KpiRow, Loading, Note, Segmented, Select, Tabs, cx } from "./ui";

const SPEEDS = [0.25, 0.5, 1, 2, 4] as const;
// At 1x the whole recorded schedule plays in this many seconds.
const BASE_SECONDS = 30;

function filesFor(data: InstanceData, kind: "proposed" | "original" | "all") {
  return kind === "all" ? data.solutions : data.solutions.filter((s) => s.kind === kind);
}

function defaultFile(files: SolutionFile[], wanted?: string | null) {
  return (files.find((f) => f.file === wanted) ?? files.find((f) => f.algorithm === "mFSTSP Gurobi Heuristic") ?? files[0])?.file ?? "";
}

export default function RouteBrowser({ instance, kind = "all", animated = false, initialFile, compare = false }: { instance: string; kind?: "proposed" | "original" | "all"; animated?: boolean; initialFile?: string | null; compare?: boolean }) {
  const { data, error } = useInstance(instance);
  if (error) return <Note tone="error">Cannot read saved solutions: {error}</Note>;
  if (!data) return <Loading label="Loading saved solutions…" />;
  const files = filesFor(data, kind);
  if (!files.length) return <Note>No saved solution is available for this instance. A route is not invented from coordinates.</Note>;
  return <Browser key={instance} data={data} files={files} animated={animated} initialFile={initialFile} compare={compare} />;
}

function Browser({ data, files, animated, initialFile, compare }: { data: InstanceData; files: SolutionFile[]; animated: boolean; initialFile?: string | null; compare: boolean }) {
  const [fileName, setFileName] = useState(() => defaultFile(files, initialFile));
  const file = files.find((f) => f.file === fileName) ?? files[0];
  const [snapIdx, setSnapIdx] = useState(file.snapshots.length - 1);
  const header = (
    <div className="grid gap-4 md:grid-cols-3">
      <Field label="Saved solution / vehicle configuration" className="md:col-span-2">
        <Select value={file.file} options={files.map((f) => f.file)} onChange={(v) => { setFileName(v); setSnapIdx((files.find((f) => f.file === v)?.snapshots.length ?? 1) - 1); }} format={(v) => { const f = files.find((x) => x.file === v)!; return `${v.replace("tbl_solutions_", "").replace(".csv", "")} · ${f.algorithm}`; }} />
      </Field>
      <Field label="Recorded snapshot (file order)">
        <Select value={Math.min(snapIdx, file.snapshots.length - 1)} options={file.snapshots.map((_, i) => i)} onChange={setSnapIdx} format={(i) => `Snapshot ${i + 1} of ${file.snapshots.length}`} />
      </Field>
    </div>
  );
  // Keyed so playback state starts fresh for each recorded snapshot.
  return <Player key={`${file.file}#${snapIdx}`} data={data} file={file} snapIdx={Math.min(snapIdx, file.snapshots.length - 1)} animated={animated} compare={compare} header={header} />;
}

function Player({ data, file, snapIdx, animated, compare, header }: { data: InstanceData; file: SolutionFile; snapIdx: number; animated: boolean; compare: boolean; header: React.ReactNode }) {
  const snap = file.snapshots[snapIdx];
  const vehicles = useMemo(() => (snap ? vehiclesOf(snap) : []), [snap]);
  const { series: palette } = useTokens();
  const colors = useMemo(() => vehicleColors(vehicles, palette), [vehicles, palette]);
  const [selected, setSelected] = useState<string>("");
  const [hidden, setHidden] = useState<string[]>([]);
  const visible = useMemo(() => new Set(vehicles.filter((v) => !hidden.includes(v))), [vehicles, hidden]);
  const [time, setTime] = useState(animated ? 0 : (snap?.duration ?? 0));
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(1);
  const [tab, setTab] = useState<"Vehicle activity & events" | "Delivery times">("Vehicle activity & events");
  const [other, setOther] = useState("");

  const duration = snap?.duration ?? 0;
  const timeRef = useRef(time);
  useEffect(() => {
    timeRef.current = time;
  }, [time]);

  useEffect(() => {
    if (!playing) return;
    const tick = (_t: number, dt: number) => {
      const next = timeRef.current + (dt / 1000) * speed * (duration / BASE_SECONDS);
      if (next >= duration) {
        setTime(duration);
        setPlaying(false);
      } else setTime(next);
    };
    gsap.ticker.add(tick);
    return () => gsap.ticker.remove(tick);
  }, [playing, speed, duration]);

  const xy = useMemo(() => project(data.coords), [data.coords]);
  const dist = useMemo(() => (snap ? distances(snap, xy) : {}), [snap, xy]);
  const states = useMemo(() => (snap ? vehicleStates(snap, data.coords, time) : []), [snap, data.coords, time]);
  const inspected = selected || vehicles[0];
  const probe = states.find((s) => s.vehicle === inspected);
  const delivered = snap ? snap.deliveries.filter(([, t]) => t <= time).length : 0;

  if (!snap) return <Note tone="error">This solution file has no readable snapshot.</Note>;

  const otherFile = data.solutions.find((f) => f.file === other);
  const otherSnap = otherFile?.snapshots[otherFile.snapshots.length - 1];

  return (
    <div className="flex flex-col gap-5">
      {header}

      <Caption>
        Source: Problems/{data.problemName}/{file.file}. Saved routes are separate snapshots, not assumed to match a selected summary row or the current algorithm version.
      </Caption>
      {file.snapshots.length > 1 && <Note>This file holds {file.snapshots.length} appended solution snapshots (dates are not recorded). Only the selected block is shown; histories are never merged. Original-method files can include local reruns.</Note>}
      {snap.warnings.map((w) => (
        <Note key={w} tone="warn">
          {w}
        </Note>
      ))}

      <KpiRow>
        <Kpi label="Saved makespan" value={snap.ofv} suffix=" s" digits={1} detail="Objective read directly from the saved solution file." tone="orange" />
        <Kpi label="Vehicles recorded" value={vehicles.length} detail="Unique vehicle IDs in the saved assignments, not the declared fleet size." />
        <Kpi label="Route geometry" value={(dist[inspected] ?? 0) / 1000} suffix=" km" digits={1} detail={`Straight-line length of ${inspected}'s recorded segments; not a road-network distance.`} tone="violet" />
        <Kpi label="Delivered so far" value={delivered} detail="Deliveries completed at the current playback time. UAV delivery times in proposed files are illustrative midpoints." tone="mint" />
      </KpiRow>

      <div className="flex flex-wrap items-end gap-4">
        <Field label="Inspect vehicle" className="w-48">
          <Select value={inspected} options={vehicles} onChange={setSelected} />
        </Field>
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold tracking-wide text-muted uppercase">Show vehicles</span>
          <div className="flex flex-wrap gap-1.5">
            {vehicles.map((v) => {
              const on = !hidden.includes(v);
              return (
                <button key={v} onClick={() => setHidden(on ? [...hidden, v] : hidden.filter((h) => h !== v))} className={cx("flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-all", on ? "border-line bg-panel text-foreground" : "border-line/60 text-muted/60 line-through")}>
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: colors[v], opacity: on ? 1 : 0.3 }} />
                  {v}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <Scene3D coords={data.coords} snap={snap} time={time} colors={colors} visible={visible} selected={selected || null} height={animated ? 580 : 460} />

      <div className="panel flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          {animated && (
            <>
              <Button tone="primary" onClick={() => { if (time >= duration) setTime(0); setPlaying(!playing); }}>
                {playing ? "❚❚ Pause" : "▶ Play"}
              </Button>
              <Button onClick={() => { setTime(0); setPlaying(true); }}>↺ Restart</Button>
              <Segmented options={SPEEDS.map((s) => `${s}×`)} value={`${speed}×`} onChange={(v) => setSpeed(Number(v.replace("×", "")) as (typeof SPEEDS)[number])} />
            </>
          )}
          <span className="ml-auto font-mono text-sm tabular-nums text-cyan">
            t = {fmt(time, 1)} s <span className="text-muted">/ {fmt(duration, 1)} s</span>
          </span>
        </div>
        <input type="range" min={0} max={duration || 1} step={(duration || 1) / 1000} value={time} onChange={(e) => { setPlaying(false); setTime(Number(e.target.value)); }} aria-label="Recorded schedule time" />
        {probe && (
          <p className="text-sm">
            <b style={{ color: colors[probe.vehicle] }}>{probe.vehicle}</b> · {probe.status} · node {probe.a} → {probe.b} · segment progress {Math.round(probe.f * 100)}%
          </p>
        )}
        <Caption>Real benchmark coordinates, locally projected in metres. Arc height is illustrative, not measured altitude; lines are schematic, not road or flight trajectories. Between recorded UAV activities the drone is drawn on the truck, which is an inference.</Caption>
        {!animated && (
          <Link href={`/studio?instance=${data.problemName}&file=${file.file}`} className="text-sm text-cyan hover:underline">
            Open this solution in the 3D delivery studio →
          </Link>
        )}
      </div>

      {compare && (
        <Details summary="Compare another saved solution side by side">
          <div className="flex flex-col gap-4">
            <Field label="Second saved solution" className="md:max-w-md">
              <Select value={other || ""} options={["", ...data.solutions.map((f) => f.file)]} onChange={setOther} format={(v) => (v ? v.replace("tbl_solutions_", "").replace(".csv", "") + " · " + data.solutions.find((f) => f.file === v)!.algorithm : "Choose a solution…")} />
            </Field>
            {otherFile && otherSnap && (
              <div className="grid gap-4 lg:grid-cols-2">
                {[
                  [file, snap],
                  [otherFile, otherSnap],
                ].map(([f, s], i) => {
                  const sn = s as typeof snap;
                  const vs = vehiclesOf(sn);
                  return (
                    <div key={i} className="flex flex-col gap-2">
                      <div className="flex justify-between text-xs text-muted">
                        <span>{(f as SolutionFile).file}</span>
                        <span className="text-orange">makespan {fmt(sn.ofv, 1)} s</span>
                      </div>
                      <Scene3D coords={data.coords} snap={sn} time={time} colors={vehicleColors(vs, palette)} visible={new Set(vs)} height={380} />
                    </div>
                  );
                })}
              </div>
            )}
            <Caption>Both scenes follow the same playback clock. The two files use independent configurations, so a geometric comparison is not a fair performance comparison.</Caption>
          </div>
        </Details>
      )}

      <Details summary="Saved configuration & validation">
        <div className="grid gap-4 md:grid-cols-2">
          <pre className="code overflow-auto rounded-lg border border-line bg-code p-4">{JSON.stringify(snap.config, null, 2)}</pre>
          <div>
            <Caption>Recorded validation (a solver claim, not independently certified):</Caption>
            <pre className="code mt-2 overflow-auto rounded-lg border border-line bg-code p-4">{JSON.stringify(snap.validation ?? { status: "No validation dictionary recorded" }, null, 2)}</pre>
          </div>
        </div>
      </Details>

      <Tabs tabs={["Vehicle activity & events", "Delivery times"] as const} value={tab} onChange={setTab} />
      <FadeSwap k={tab}>
        {tab === "Vehicle activity & events" ? (
          <>
            <DataTable
              name={`${data.problemName}_assignments`}
              rows={snap.segments}
              columns={[
                { key: "v", label: "Vehicle", value: (s) => s[0] },
                { key: "s", label: "Start (s)", value: (s) => s[1], numeric: true },
                { key: "e", label: "End (s)", value: (s) => s[2], numeric: true },
                { key: "a", label: "From", value: (s) => s[3], numeric: true },
                { key: "b", label: "To", value: (s) => s[4], numeric: true },
                { key: "st", label: "Status", value: (s) => s[5] },
              ]}
            />
            {snap.events.length > 0 && <DataTable name={`${data.problemName}_events`} rows={snap.events} columns={[{ key: "v", label: "Vehicle", value: (e) => e.vehicle }, { key: "t", label: "Event", value: (e) => e.type }, { key: "n", label: "Node", value: (e) => e.node, numeric: true }, { key: "time", label: "Time (s)", value: (e) => e.time, numeric: true }]} />}
          </>
        ) : (
          <>
            <Caption>Proposed-file UAV times are illustrative midpoints. Original assignment delivery times and proposed truck service times are recorded.</Caption>
            <DataTable name={`${data.problemName}_deliveries`} rows={snap.deliveries} columns={[{ key: "n", label: "Node", value: (d) => d[0], numeric: true }, { key: "t", label: "Completion time (s)", value: (d) => d[1], numeric: true }]} />
          </>
        )}
      </FadeSwap>
      <div>
        <Button onClick={() => download(`${data.problemName}_${file.file.replace(".csv", "")}_snapshot${snapIdx + 1}.json`, JSON.stringify(snap, null, 2), "application/json")}>↓ Download parsed solution (JSON)</Button>
      </div>
    </div>
  );
}
