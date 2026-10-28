"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import RouteBrowser from "./RouteBrowser";
import { useWorkspace } from "./Shell";
import { Field, Hero, Loading, Note, Page, Panel, Segmented, Select } from "./ui";

const MODES = ["Delivery playback", "Algorithm execution"] as const;

export default function Studio() {
  const { data, sizes } = useWorkspace();
  const params = useSearchParams();
  const [mode, setMode] = useState<(typeof MODES)[number]>("Delivery playback");
  const [instance, setInstance] = useState(params.get("instance") ?? "");
  const file = params.get("file");

  const scoped = (data?.inventory ?? []).filter((b) => sizes.includes(b.numCustomers ?? -1) && b.savedSolutions > 0);
  const chosen = scoped.find((b) => b.problemName === instance) ?? scoped[0];

  return (
    <Page>
      <Hero title="Watch the delivery system move." subtitle="Inspect recorded truck and drone assignments in 3D. Follow the timeline, compare saved solutions, and examine launch and rendezvous events." tags={["Real coordinates · illustrative height"]} />
      <div className="reveal">
        <Segmented options={MODES} value={mode} onChange={setMode} />
      </div>
      {mode === "Algorithm execution" ? (
        <Panel title="Optimization-step playback is unavailable">
          <div className="flex flex-col gap-3">
            <Note tone="warn">No saved population, generation, incumbent history or optimization trace was found. A final route cannot reconstruct the search trajectory, so no synthetic search steps are shown as experimental evidence.</Note>
            <p className="text-sm text-muted">Use Algorithms explained for a source-based walkthrough, or Delivery playback for the recorded schedule events.</p>
          </div>
        </Panel>
      ) : !data ? (
        <Loading />
      ) : !chosen ? (
        <Note>Select at least one customer count in the sidebar.</Note>
      ) : (
        <Panel>
          <div className="flex flex-col gap-5">
            <Field label="Benchmark instance" className="max-w-md">
              <Select value={chosen.problemName} options={scoped.map((b) => b.problemName)} onChange={setInstance} format={(v) => `${v} · ${scoped.find((b) => b.problemName === v)?.numCustomers} customers`} />
            </Field>
            <RouteBrowser key={chosen.problemName} instance={chosen.problemName} animated compare initialFile={chosen.problemName === params.get("instance") ? file : null} />
          </div>
        </Panel>
      )}
    </Page>
  );
}
