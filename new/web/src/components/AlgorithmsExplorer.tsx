"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { ALGORITHMS, type Algorithm } from "@/lib/algorithms";
import { useSources } from "@/lib/data";
import { DataTable } from "./DataTable";
import { Button, Caption, FadeSwap, Hero, Loading, Note, Page, Panel, Tabs, cx } from "./ui";

gsap.registerPlugin(useGSAP);

const TABS = ["Walkthrough & flow", "Pseudocode", "Actual implementation"] as const;

const KEYWORDS = new Set("def return if elif else for while in not and or is None True False import from as with try except raise class lambda yield pass break continue global assert del".split(" "));

// Minimal Python highlighter that builds React nodes (no innerHTML).
function highlight(line: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(#.*$)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(\b\d+(?:\.\d+)?\b)|(\b[A-Za-z_]\w*\b)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(line))) {
    if (m.index > last) out.push(line.slice(last, m.index));
    const [tok] = m;
    const next = line.slice(m.index + tok.length).trimStart();
    const cls = m[1] ? "text-muted italic" : m[2] ? "text-orange" : m[3] ? "text-violet" : KEYWORDS.has(tok) ? "text-rose" : next.startsWith("(") ? "text-cyan" : "";
    out.push(cls ? <span key={i++} className={cls}>{tok}</span> : tok);
    last = m.index + tok.length;
  }
  if (last < line.length) out.push(line.slice(last));
  return out;
}

function Code({ code, start = 1, maxHeight = 520 }: { code: string; start?: number; maxHeight?: number }) {
  const lines = code.split("\n");
  return (
    <div className="code overflow-auto rounded-xl border border-line bg-code" style={{ maxHeight }}>
      <table className="w-full border-collapse">
        <tbody>
          {lines.map((l, i) => (
            <tr key={i} className="hover:bg-cyan/[0.05]">
              <td className="sticky left-0 w-12 border-r border-line bg-code pr-3 pl-4 text-right text-muted/60 select-none">{start + i}</td>
              <td className="pl-3 pr-4 whitespace-pre text-foreground">{highlight(l)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Flow({ steps, active }: { steps: string[]; active: number }) {
  const root = useRef<HTMLDivElement>(null);
  useGSAP(
    () => {
      // Colours come from theme classes; GSAP only adds the motion.
      gsap.to(".flow-node", { scale: (i: number) => (i === active ? 1.05 : 1), duration: 0.45, ease: "back.out(2)" });
      const pulse = root.current?.querySelectorAll(".flow-pulse")[Math.max(0, active - 1)];
      if (pulse && active > 0) gsap.fromTo(pulse, { left: "0%", opacity: 1 }, { left: "100%", opacity: 0, duration: 0.6, ease: "power2.in" });
    },
    { scope: root, dependencies: [active, steps] },
  );
  return (
    <div ref={root} className="flex flex-wrap items-center gap-y-4 py-2">
      {steps.map((s, i) => (
        <div key={s} className="flex items-center">
          <div className={cx("flow-node rounded-lg border px-3.5 py-2.5 text-center text-xs font-medium transition-colors duration-300 sm:text-sm", i === active ? "border-cyan bg-cyan text-panel shadow-md" : i < active ? "border-cyan/40 bg-cyan/[0.08] text-cyan" : "border-line bg-panel text-foreground")}>{s}</div>
          {i < steps.length - 1 && (
            <div className={cx("flow-link relative mx-2 h-0.5 w-6 rounded-full transition-colors duration-300 sm:w-10", i < active ? "bg-cyan" : "bg-line-strong")}>
              <span className="flow-pulse absolute top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-cyan opacity-0" />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function Walkthrough({ algo }: { algo: Algorithm }) {
  const [step, setStep] = useState(0);
  const [auto, setAuto] = useState(false);
  useEffect(() => {
    if (!auto) return;
    const id = setInterval(() => setStep((s) => (s + 1) % algo.steps.length), 1800);
    return () => clearInterval(id);
  }, [auto, algo.steps.length]);
  // Map the step position onto the (usually shorter) flow diagram.
  const flowActive = Math.round((step / Math.max(1, algo.steps.length - 1)) * (algo.flow.length - 1));
  return (
    <>
      <Flow steps={algo.flow} active={flowActive} />
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0}>
          ← Previous
        </Button>
        <Button onClick={() => setStep(Math.min(algo.steps.length - 1, step + 1))} disabled={step === algo.steps.length - 1}>
          Next →
        </Button>
        <Button tone="primary" onClick={() => setAuto(!auto)}>
          {auto ? "❚❚ Pause walkthrough" : "▶ Auto-play"}
        </Button>
        <span className="ml-auto text-xs text-muted">
          Step {step + 1} of {algo.steps.length}
        </span>
      </div>
      <ol className="flex flex-col gap-2">
        {algo.steps.map((s, i) => (
          <li key={i}>
            <button onClick={() => setStep(i)} className={cx("flex w-full gap-3 rounded-xl border px-4 py-3 text-left text-sm transition-all", i === step ? "border-cyan/40 bg-cyan/[0.07] text-foreground" : "border-transparent text-muted hover:bg-panel-2")}>
              <span className={cx("grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-bold", i === step ? "bg-cyan text-panel" : i < step ? "bg-cyan/20 text-cyan" : "bg-panel-2 text-muted")}>{i + 1}</span>
              {s}
            </button>
          </li>
        ))}
      </ol>
      <Caption>Educational walkthrough of the source, not a recorded optimizer execution.</Caption>
      <div className="grid gap-4 md:grid-cols-2">
        <Note tone="ok">
          <b>Strengths.</b> {algo.strengths}
        </Note>
        <Note tone="warn">
          <b>Limitations.</b> {algo.limitations}
        </Note>
      </div>
    </>
  );
}

export default function AlgorithmsExplorer() {
  const [id, setId] = useState(ALGORITHMS[0].id);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Walkthrough & flow");
  const { data: sources, error } = useSources();
  const algo = ALGORITHMS.find((a) => a.id === id)!;
  const excerpt = sources?.[`${algo.source}#${algo.fn}`];
  const cards = useRef<HTMLDivElement>(null);
  useGSAP(
    () => {
      gsap.to(".algo-card", { y: (i, el) => ((el as HTMLElement).dataset.active === "true" ? -4 : 0), duration: 0.35, ease: "power2.out" });
    },
    { scope: cards, dependencies: [id] },
  );

  return (
    <Page>
      <Hero title="Inside the optimization engine." subtitle="Source-grounded explanations of the search, Gurobi models and scheduling components in the proposed heuristic, next to the original reference methods. No solver is imported or run by this dashboard." tags={["Source-grounded"]} />

      <div ref={cards} className="reveal grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {ALGORITHMS.map((a) => (
          <button key={a.id} data-active={a.id === id} onClick={() => setId(a.id)} className={cx("algo-card panel flex flex-col gap-2 p-4 text-left transition-colors", a.id === id ? "border-cyan! ring-2 ring-cyan/15" : "hover:border-line-strong")}>
            <span className={cx("w-fit rounded-full px-2 py-0.5 text-[0.65rem] font-bold tracking-wider uppercase", a.family === "Proposed" ? "bg-cyan/10 text-cyan" : "bg-orange/10 text-orange")}>{a.family}</span>
            <span className="font-serif text-[1.05rem] font-semibold">{a.name}</span>
            <span className="text-xs leading-relaxed text-muted">{a.role}</span>
          </button>
        ))}
      </div>

      <Panel title={algo.name} subtitle={<span className="code text-xs">{algo.source} · {algo.fn}()</span>}>
        <div className="mb-5 grid gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-line bg-panel-2/60 p-4">
            <div className="eyebrow mb-2">Inputs</div>
            <p className="text-sm leading-relaxed">{algo.inputs}</p>
          </div>
          <div className="rounded-xl border border-line bg-panel-2/60 p-4">
            <div className="eyebrow mb-2">Outputs</div>
            <p className="text-sm leading-relaxed">{algo.outputs}</p>
          </div>
        </div>
        <div className="flex flex-col gap-5">
          <Tabs tabs={TABS} value={tab} onChange={setTab} />
          <FadeSwap k={tab + id}>
            {tab === "Walkthrough & flow" && <Walkthrough key={id} algo={algo} />}
            {tab === "Pseudocode" && <Code code={algo.pseudocode} />}
            {tab === "Actual implementation" &&
              (error ? (
                <Note tone="error">Cannot load source excerpts: {error}</Note>
              ) : !sources ? (
                <Loading label="Loading source…" />
              ) : excerpt ? (
                <>
                  <Caption>
                    {excerpt.file}:{excerpt.line} · copied from the checked-in source when the dashboard data was built.
                  </Caption>
                  <Code code={excerpt.code} start={excerpt.line} maxHeight={640} />
                </>
              ) : (
                <Note tone="warn">Function {algo.fn} was not found in this source revision.</Note>
              ))}
          </FadeSwap>
        </div>
      </Panel>

      <Panel title="How the approaches differ">
        <DataTable
          name="algorithms"
          rows={ALGORITHMS}
          columns={[
            { key: "name", label: "Algorithm", value: (a) => a.name },
            { key: "family", label: "Family", value: (a) => a.family },
            { key: "role", label: "Role", value: (a) => a.role },
            { key: "fn", label: "Function", value: (a) => `${a.fn}()` },
          ]}
        />
        <div className="mt-4">
          <Note>The current main.py only accepts problemType = 3 and calls proposed_heuristic_with_gurobi. The original heuristic and IP live in old/ as reference code. Historical experiments are not assumed to use the current source revision.</Note>
        </div>
      </Panel>
    </Page>
  );
}
