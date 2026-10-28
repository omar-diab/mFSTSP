"use client";

import { useRef } from "react";
import Link from "next/link";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import SplashScreen from "@/components/SplashScreen";
import { PAGES, useWorkspace } from "@/components/Shell";
import { Kpi } from "@/components/ui";
import { useStored, writeStored } from "@/lib/storage";

gsap.registerPlugin(useGSAP);

const BLURBS: Record<string, string> = {
  "/comparison": "Pair the proposed heuristic with archived runs under matching conditions. Wins, improvements and an audit of every configuration.",
  "/results": "Every proposed-heuristic run: outcomes, runtime against makespan, size trends and saved routes.",
  "/paper": "The archived reference benchmark from the original three-phase heuristic and IP, kept separate from local runs.",
  "/algorithms": "Step-by-step walkthroughs, flow diagrams, pseudocode and the real source of each component.",
  "/studio": "Replay recorded truck and drone schedules in an interactive 3D scene with a scrubbable timeline.",
};

// Decorative route: customers, a truck tour and three drone sorties.
const NODES = [
  [80, 210], [150, 120], [260, 80], [360, 140], [420, 230], [340, 300], [220, 290], [130, 300], [300, 200], [200, 180],
];
const TOUR = [0, 1, 2, 3, 4, 5, 6, 7, 0];
const SORTIES = [
  [1, 9, 3],
  [3, 8, 5],
  [5, 6, 7],
];

function arc(a: number[], b: number[], lift = 60) {
  const mx = (a[0] + b[0]) / 2;
  const my = (a[1] + b[1]) / 2 - lift;
  return `M${a[0]},${a[1]} Q${mx},${my} ${b[0]},${b[1]}`;
}

function HeroArt({ play }: { play: boolean }) {
  const root = useRef<SVGSVGElement>(null);
  useGSAP(
    () => {
      if (!play) return;
      const tour = root.current!.querySelector<SVGPathElement>(".tour")!;
      const len = tour.getTotalLength();
      const tl = gsap.timeline({ delay: 0.3 });
      tl.fromTo(".node", { scale: 0, transformOrigin: "50% 50%" }, { scale: 1, duration: 0.5, ease: "back.out(3)", stagger: 0.05 })
        .fromTo(tour, { strokeDasharray: len, strokeDashoffset: len }, { strokeDashoffset: 0, duration: 2.2, ease: "power2.inOut" }, 0.4)
        .fromTo(".sortie", { opacity: 0 }, { opacity: 1, duration: 0.4, stagger: 0.25 }, 1.2);
      const truck = { p: 0 };
      gsap.to(truck, {
        p: 1,
        duration: 12,
        ease: "none",
        repeat: -1,
        onUpdate: () => {
          const pt = tour.getPointAtLength(truck.p * len);
          root.current?.querySelector(".truck")?.setAttribute("transform", `translate(${pt.x} ${pt.y})`);
        },
      });
      root.current!.querySelectorAll<SVGPathElement>(".sortie-path").forEach((path, i) => {
        const l = path.getTotalLength();
        const d = { p: 0 };
        const drone = root.current!.querySelectorAll(".drone")[i];
        gsap.to(d, {
          p: 1,
          duration: 3.2,
          ease: "sine.inOut",
          repeat: -1,
          yoyo: true,
          delay: 1.5 + i * 0.8,
          onUpdate: () => {
            const pt = path.getPointAtLength(d.p * l);
            drone.setAttribute("transform", `translate(${pt.x} ${pt.y})`);
          },
        });
      });
      gsap.to(".sortie-path", { strokeDashoffset: -20, duration: 1, ease: "none", repeat: -1 });
    },
    { scope: root, dependencies: [play] },
  );
  return (
    <svg ref={root} viewBox="0 0 500 380" className="h-full w-full" aria-hidden="true">
      <defs>
        <radialGradient id="home-glow">
          <stop offset="0" className="[stop-color:var(--orange)]" stopOpacity="0.22" />
          <stop offset="1" className="[stop-color:var(--orange)]" stopOpacity="0" />
        </radialGradient>
      </defs>
      {Array.from({ length: 9 }, (_, i) => (
        <line key={`h${i}`} x1="0" x2="500" y1={i * 48} y2={i * 48} className="stroke-(--grid)" />
      ))}
      {Array.from({ length: 11 }, (_, i) => (
        <line key={`v${i}`} y1="0" y2="380" x1={i * 50} x2={i * 50} className="stroke-(--grid)" />
      ))}
      <circle cx={NODES[0][0]} cy={NODES[0][1]} r="60" fill="url(#home-glow)" />
      <path d={TOUR.map((n, i) => `${i ? "L" : "M"}${NODES[n][0]},${NODES[n][1]}`).join(" ")} fill="none" className="tour stroke-orange" strokeWidth="3" strokeLinejoin="round" />
      {SORTIES.map(([a, c, b], i) => (
        <g key={i} className="sortie" opacity="0">
          <path d={`${arc(NODES[a], NODES[c])} ${arc(NODES[c], NODES[b]).replace("M", "L")}`} fill="none" className="sortie-path stroke-cyan" strokeWidth="1.8" strokeDasharray="5 5" />
        </g>
      ))}
      {NODES.map(([x, y], i) =>
        i === 0 ? (
          <rect key={i} x={x - 8} y={y - 8} width="16" height="16" rx="3" className="node fill-foreground" />
        ) : (
          <circle key={i} cx={x} cy={y} r={SORTIES.some((s) => s[1] === i) ? 6 : 5} className={SORTIES.some((s) => s[1] === i) ? "node fill-mint" : "node fill-(--node)"} />
        ),
      )}
      <g className="truck" transform={`translate(${NODES[0][0]} ${NODES[0][1]})`}>
        <rect x="-11" y="-7" width="22" height="14" rx="3" className="fill-orange stroke-(--panel)" strokeWidth="2" />
      </g>
      {SORTIES.map(([a], i) => (
        <g key={i} className="drone" transform={`translate(${NODES[a][0]} ${NODES[a][1]})`}>
          <path d="M0,-7 L7,0 L0,7 L-7,0 Z" className="fill-cyan stroke-(--panel)" strokeWidth="1.5" />
        </g>
      ))}
    </svg>
  );
}

export default function Home() {
  const { data } = useWorkspace();
  // The splash plays once per browser session; "pending" covers the page
  // until the client knows whether it already played.
  const seen = useStored("session", "mfstsp.splash");
  const splash = seen === undefined ? "pending" : seen === "1" ? "done" : "show";
  const root = useRef<HTMLDivElement>(null);
  const finish = () => writeStored("session", "mfstsp.splash", "1");

  useGSAP(
    () => {
      if (splash !== "done") return;
      gsap
        .timeline()
        .from(".h-line", { y: 50, opacity: 0, duration: 0.9, ease: "power4.out", stagger: 0.12 })
        .from(".h-fade", { y: 20, opacity: 0, duration: 0.7, ease: "power3.out", stagger: 0.1 }, "-=0.5")
        .from(".h-card", { y: 40, opacity: 0, duration: 0.7, ease: "power3.out", stagger: 0.08, clearProps: "transform" }, "-=0.4");
    },
    { scope: root, dependencies: [splash] },
  );

  const proposedSolved = data?.results.filter((r) => r.cohort === "proposed" && r.algorithm === "mFSTSP Gurobi Heuristic" && r.source.startsWith("results/") && r.solved).length ?? null;

  return (
    <>
      {splash === "show" && <SplashScreen onFinish={finish} />}
      {splash === "pending" && <div className="fixed inset-0 z-50 bg-black" />}
      <div ref={root} className="mx-auto flex w-full max-w-[1500px] flex-col gap-8 px-4 pt-8 pb-16 sm:px-8 lg:pt-12">
        <section className="panel relative grid overflow-hidden lg:grid-cols-[1.1fr_1fr]">
          <div className="relative flex flex-col justify-center gap-5 p-7 sm:p-10">
            <div className="h-fade eyebrow">Multiple flying sidekicks TSP · research workspace</div>
            <h1 className="font-serif text-4xl leading-[1.08] font-bold tracking-tight sm:text-[3.6rem]">
              <span className="h-line block">One truck.</span>
              <span className="h-line block text-cyan">Multiple drones.</span>
              <span className="h-line block text-muted">Every result on record.</span>
            </h1>
            <p className="h-fade max-w-xl leading-relaxed text-muted">
              A read-only dashboard for the mFSTSP experiments: the proposed Gurobi-assisted heuristic, the original paper&apos;s reference methods, and every saved delivery route, replayable in 3D.
            </p>
            <div className="h-fade flex flex-wrap gap-3">
              <Link href="/comparison" className="rounded-lg border border-cyan bg-cyan px-5 py-3 text-sm font-semibold text-panel shadow-sm transition-opacity hover:opacity-90">
                Open the comparison →
              </Link>
              <Link href="/studio" className="rounded-lg border border-line bg-panel px-5 py-3 text-sm font-semibold transition-colors hover:border-line-strong hover:bg-panel-2">
                Watch a delivery in 3D
              </Link>
            </div>
          </div>
          <div className="h-fade relative min-h-[280px] border-t border-line bg-panel-2 lg:border-t-0 lg:border-l">
            <HeroArt play={splash === "done"} />
          </div>
        </section>

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <div className="h-card">
            <Kpi label="Benchmark instances" value={data?.inventory.length ?? null} detail="Problem folders under new/Problems with customer and depot coordinates." />
          </div>
          <div className="h-card">
            <Kpi label="Recorded result rows" value={data?.results.length ?? null} detail="Rows across performance_summary.csv, the archive and the runner's results/all_*.csv files." tone="orange" />
          </div>
          <div className="h-card">
            <Kpi label="Saved solution files" value={data?.savedFiles ?? null} detail="tbl_solutions_*.csv files with replayable routes and schedules." tone="violet" />
          </div>
          <div className="h-card">
            <Kpi label="Proposed runs solved" value={proposedSolved} detail="Gurobi-assisted heuristic runs in results/all_solved.csv with a positive finite makespan." tone="mint" />
          </div>
        </div>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          {PAGES.map((p, i) => (
            // GSAP animates the wrapper; the link keeps its own CSS hover transition.
            <div key={p.href} className="h-card flex">
            <Link
              href={p.href}
              className="group panel relative flex flex-1 flex-col gap-3 overflow-hidden p-5 transition-all duration-300 hover:-translate-y-0.5 hover:border-cyan/50 hover:shadow-md"
            >
              <span className="text-xs font-bold text-muted">0{i + 1}</span>
              <svg viewBox="0 0 24 24" className="h-7 w-7 text-cyan transition-transform duration-300 group-hover:scale-110" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d={p.icon} />
              </svg>
              <span className="font-serif text-[1.1rem] font-semibold">{p.label}</span>
              <span className="text-sm leading-relaxed text-muted">{BLURBS[p.href]}</span>
              <span className="mt-auto pt-2 text-sm text-cyan opacity-0 transition-opacity group-hover:opacity-100">Open →</span>
            </Link>
            </div>
          ))}
        </section>
      </div>
    </>
  );
}
