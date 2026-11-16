"use client";

import { ReactNode, createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { refreshData, useReproduction } from "@/lib/data";
import { useStored, writeStored } from "@/lib/storage";
import { useTheme } from "@/lib/theme";
import { SIZES, type ReproductionData } from "@/lib/types";
import SplashScreen from "./SplashScreen";
import { cx } from "./ui";

gsap.registerPlugin(useGSAP);

// All pages live under one parent group, "Results".
export const PAGES = [
  { href: "/results/paper", label: "Paper results", icon: "M6 3h9l5 5v13H6zM14 3v6h6M9 13h8M9 17h8" },
  { href: "/results/ours", label: "Our results", icon: "M3 17l5-5 4 4 8-8M14 8h6v6" },
  { href: "/results/compare", label: "Compare", icon: "M4 19V9m6 10V5m6 14v-7m4 7H2" },
] as const;

type Workspace = {
  sizes: number[];
  setSizes: (s: number[]) => void;
  data: ReproductionData | null;
  error: string | null;
  refresh: () => void;
};

const Ctx = createContext<Workspace | null>(null);

export function useWorkspace() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useWorkspace outside Shell");
  return ctx;
}

function Icon({ d, className }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={cx("h-[18px] w-[18px] shrink-0", className)} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

const ICONS = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z",
  collapse: "M15 6l-6 6 6 6M4 4v16",
  expand: "M9 6l6 6-6 6M20 4v16",
  close: "M6 6l12 12M18 6L6 18",
  menu: "M4 7h16M4 12h16M4 17h16",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6",
  filter: "M4 5h16l-6 7.5V19l-4 2v-8.5z",
  info: "M12 8h.01M11 12h1v5h1M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z",
};

// The same mark is the browser-tab icon (app/icon.svg).
function LogoMark() {
  return (
    <span className="relative grid h-9 w-9 shrink-0 place-items-center rounded-[9px] bg-[#1b2a44] shadow-sm">
      <svg viewBox="0 0 40 40" className="h-7 w-7" aria-hidden="true">
        <rect x="9" y="22" width="22" height="9" rx="2" fill="#ff9a4d" />
        <rect x="24" y="18" width="7" height="6" rx="1.5" fill="#ffb878" />
        <circle cx="14" cy="32" r="2.4" fill="#0b0f17" stroke="#dce6f6" />
        <circle cx="27" cy="32" r="2.4" fill="#0b0f17" stroke="#dce6f6" />
        <g className="transition-transform duration-500 group-hover:-translate-y-1">
          <rect x="13" y="10" width="14" height="3" rx="1.5" fill="#5ff3ff" />
          <ellipse cx="11" cy="9" rx="5" ry="1.2" fill="#dce6f6" opacity="0.6" />
          <ellipse cx="29" cy="9" rx="5" ry="1.2" fill="#dce6f6" opacity="0.6" />
        </g>
      </svg>
    </span>
  );
}

function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/results/paper" className="group flex min-w-0 items-center gap-3" aria-label="mFSTSP home">
      <LogoMark />
      {!compact && (
        <span className="min-w-0 leading-tight">
          <span className="block font-serif text-[1.1rem] font-bold tracking-tight">mFSTSP</span>
          <span className="block truncate text-[0.7rem] text-muted">Optimization research lab</span>
        </span>
      )}
    </Link>
  );
}

const THEMES = {
  light: { label: "Light", icon: "M12 4V2m0 20v-2m8-8h2M2 12h2m13.66-5.66 1.41-1.41M4.93 19.07l1.41-1.41m0-11.32L4.93 4.93m14.14 14.14-1.41-1.41M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10z" },
  dark: { label: "Dark", icon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" },
} as const;

function ThemeToggle({ compact = false, tip = false }: { compact?: boolean; tip?: boolean }) {
  const [theme, setTheme] = useTheme();
  if (compact) {
    // One button that switches to the other theme, showing where it goes.
    const next = theme === "dark" ? "light" : "dark";
    return (
      <RailButton label={`Switch to ${THEMES[next].label.toLowerCase()} theme`} onClick={() => setTheme(next)} tip={tip}>
        <Icon d={THEMES[next].icon} />
      </RailButton>
    );
  }
  return (
    <div className="grid grid-cols-2 rounded-lg bg-panel-2 p-0.5" role="radiogroup" aria-label="Theme">
      {(["light", "dark"] as const).map((t) => (
        <button key={t} role="radio" aria-checked={theme === t} onClick={() => setTheme(t)} className={cx("flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors", theme === t ? "bg-panel text-foreground shadow-sm" : "text-muted hover:text-foreground")}>
          <Icon d={THEMES[t].icon} className="h-3.5 w-3.5" />
          {THEMES[t].label}
        </button>
      ))}
    </div>
  );
}

// Hover label shown beside icons when the sidebar is collapsed.
function Tip({ label }: { label: string }) {
  return (
    <span className="pointer-events-none absolute top-1/2 left-full z-50 ml-3 -translate-y-1/2 rounded-md bg-foreground px-2 py-1 text-xs font-medium whitespace-nowrap text-panel opacity-0 shadow-md transition-opacity group-hover/tip:opacity-100 group-focus-visible/tip:opacity-100">
      {label}
    </span>
  );
}

function RailButton({ label, onClick, children, tip = false }: { label: string; onClick: () => void; children: ReactNode; tip?: boolean }) {
  return (
    <button onClick={onClick} aria-label={label} title={tip ? undefined : label} className="group/tip relative grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-panel-2 hover:text-foreground">
      {children}
      {tip && <Tip label={label} />}
    </button>
  );
}

const NAV = PAGES;

function Nav({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const list = useRef<HTMLDivElement>(null);
  const ink = useRef<HTMLSpanElement>(null);
  useGSAP(
    () => {
      const active = list.current?.querySelector<HTMLElement>("[data-active='true']");
      if (!ink.current) return;
      if (active) gsap.to(ink.current, { y: active.offsetTop, height: active.offsetHeight, opacity: 1, duration: 0.45, ease: "power3.out" });
      else gsap.to(ink.current, { opacity: 0, duration: 0.2 });
    },
    { dependencies: [pathname, collapsed], scope: list },
  );
  return (
    <div ref={list} className="relative flex flex-col gap-0.5">
      <span ref={ink} className="absolute top-0 left-0 w-full rounded-lg bg-cyan/10 opacity-0" />
      {NAV.map((p) => {
        const active = pathname === p.href;
        return (
          <Link
            key={p.href}
            href={p.href}
            onClick={onNavigate}
            data-active={active}
            aria-label={collapsed ? p.label : undefined}
            aria-current={active ? "page" : undefined}
            className={cx("group/tip relative flex h-10 items-center gap-3 rounded-lg text-sm font-medium transition-colors", collapsed ? "justify-center" : "px-3", active ? "text-cyan" : "text-muted hover:bg-panel-2 hover:text-foreground")}
          >
            <Icon d={p.icon} />
            {collapsed ? <Tip label={p.label} /> : <span className="truncate">{p.label}</span>}
          </Link>
        );
      })}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="px-3 text-[0.68rem] font-semibold tracking-[0.12em] text-muted/80 uppercase">{title}</span>
      {children}
    </div>
  );
}

// A sidebar group whose items can be hidden; the open/closed choice is remembered.
function CollapsibleSection({ title, storageKey, children }: { title: string; storageKey: string; children: ReactNode }) {
  const stored = useStored("local", storageKey);
  const open = stored !== "closed";
  const body = useRef<HTMLDivElement>(null);
  const chevron = useRef<SVGSVGElement>(null);
  // The stored value is unknown (undefined) until hydration; the first known state is applied without animation.
  const ready = useRef(false);
  useGSAP(
    () => {
      const el = body.current;
      if (!el || !chevron.current) return;
      if (!ready.current) {
        gsap.set(el, { height: open ? "auto" : 0, opacity: open ? 1 : 0 });
        gsap.set(chevron.current, { rotate: open ? 0 : -90 });
        if (stored !== undefined) ready.current = true;
        return;
      }
      gsap.to(chevron.current, { rotate: open ? 0 : -90, duration: 0.35, ease: "power3.out" });
      if (open) {
        gsap.to(el, { height: "auto", opacity: 1, duration: 0.45, ease: "power3.out" });
        gsap.fromTo(el.querySelectorAll("a"), { x: -10, opacity: 0 }, { x: 0, opacity: 1, duration: 0.4, ease: "power3.out", stagger: 0.05, delay: 0.05 });
      } else {
        gsap.to(el, { height: 0, opacity: 0, duration: 0.35, ease: "power3.inOut" });
      }
    },
    { dependencies: [open, stored] },
  );
  return (
    <div className="flex flex-col gap-2">
      <button
        onClick={() => writeStored("local", storageKey, open ? "closed" : "open")}
        aria-expanded={open}
        className="flex items-center justify-between rounded-md px-3 py-1 text-[0.68rem] font-semibold tracking-[0.12em] text-muted/80 uppercase transition-colors hover:text-foreground"
      >
        {title}
        <svg ref={chevron} viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {/* Kept mounted so it can animate; inert keeps hidden links out of tab order. */}
      <div ref={body} className="overflow-hidden" inert={!open}>
        {children}
      </div>
    </div>
  );
}

function SizeFilter({ ws }: { ws: Workspace }) {
  const all = ws.sizes.length === SIZES.length;
  return (
    <div className="flex flex-col gap-2 px-1">
      <div className="grid grid-cols-5 gap-1 rounded-lg bg-panel-2 p-1">
        {SIZES.map((n) => {
          const on = ws.sizes.includes(n);
          return (
            <button key={n} onClick={() => ws.setSizes(on ? ws.sizes.filter((s) => s !== n) : [...ws.sizes, n].sort((a, b) => a - b))} aria-pressed={on} className={cx("rounded-md py-1.5 text-xs font-semibold tabular-nums transition-colors", on ? "bg-panel text-cyan shadow-sm" : "text-muted hover:text-foreground")}>
              {n}
            </button>
          );
        })}
      </div>
      <div className="flex items-center justify-between px-1 text-[0.7rem] text-muted">
        <span>{all ? "All customer counts" : ws.sizes.length ? `${ws.sizes.length} of ${SIZES.length} sizes` : "No sizes selected"}</span>
        {!all && (
          <button onClick={() => ws.setSizes([...SIZES])} className="font-medium text-cyan hover:underline">
            Select all
          </button>
        )}
      </div>
    </div>
  );
}

function DataStatus({ ws }: { ws: Workspace }) {
  const { data } = ws;
  return (
    <details className="group rounded-lg border border-line text-xs">
      <summary className="flex cursor-pointer list-none items-center gap-2.5 px-3 py-2.5">
        <span className={cx("h-2 w-2 shrink-0 rounded-full", !data ? "bg-muted animate-pulse" : "bg-mint")} />
        <span className="min-w-0 flex-1">
          <span className="block font-semibold">{data ? "Recorded data loaded" : "Loading data…"}</span>
          {data && (
            <span className="block truncate text-muted">
              {data.paper.length.toLocaleString()} paper runs · {data.ours.filter((r) => r.status !== "not_run").length.toLocaleString()} of ours
            </span>
          )}
        </span>
        <span className="text-muted transition-transform group-open:rotate-180">▾</span>
      </summary>
      <div className="flex flex-col gap-2 border-t border-line p-3 leading-relaxed text-muted">
        <p>Read-only: no solver runs while browsing.</p>
        <p>Sources: old/performance_summary_archive.csv (paper) and old/reproduction/our_results.csv (written by old/reproduce.py).</p>
        {data && <p>Built {new Date(data.generatedAt).toLocaleString()} by scripts/build-data.mjs.</p>}
        <button onClick={ws.refresh} className="mt-1 flex items-center justify-center gap-1.5 rounded-md border border-line bg-panel px-3 py-1.5 font-medium text-foreground hover:bg-panel-2">
          <Icon d={ICONS.refresh} className="h-3.5 w-3.5" />
          Refresh recorded data
        </button>
      </div>
    </details>
  );
}

function Sidebar({ ws, collapsed, onToggle, onNavigate, onClose }: { ws: Workspace; collapsed: boolean; onToggle?: () => void; onNavigate?: () => void; onClose?: () => void }) {
  return (
    <div className={cx("flex h-full flex-col", collapsed ? "items-center px-2 py-4" : "px-3 py-4")}>
      <div className={cx("flex items-center pb-5", collapsed ? "flex-col gap-3" : "justify-between gap-2 px-1")}>
        <Logo compact={collapsed} />
        {onToggle && (
          <RailButton label={collapsed ? "Expand sidebar (⌘B)" : "Collapse sidebar (⌘B)"} onClick={onToggle} tip={collapsed}>
            <Icon d={collapsed ? ICONS.expand : ICONS.collapse} />
          </RailButton>
        )}
        {onClose && (
          <RailButton label="Close menu" onClick={onClose}>
            <Icon d={ICONS.close} />
          </RailButton>
        )}
      </div>

      <nav aria-label="Workspace" className={cx("flex flex-col gap-6", collapsed ? "w-full" : "min-h-0 flex-1 overflow-y-auto")}>
        {collapsed ? (
          <Nav collapsed />
        ) : (
          <>
            <CollapsibleSection title="Results" storageKey="mfstsp.results-open">
              <Nav collapsed={false} onNavigate={onNavigate} />
            </CollapsibleSection>
            <Section title="Customer counts">
              <SizeFilter ws={ws} />
            </Section>
          </>
        )}
      </nav>

      {collapsed ? (
        <div className="mt-auto flex flex-col items-center gap-1 border-t border-line pt-3">
          <RailButton label={`Filter: ${ws.sizes.length === SIZES.length ? "all sizes" : ws.sizes.join(", ") || "none"} — expand to change`} onClick={onToggle ?? (() => {})} tip>
            <Icon d={ICONS.filter} />
            {ws.sizes.length !== SIZES.length && <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-cyan" />}
          </RailButton>
          <RailButton label="Refresh recorded data" onClick={ws.refresh} tip>
            <Icon d={ICONS.refresh} />
          </RailButton>
          <ThemeToggle compact tip />
        </div>
      ) : (
        <div className="mt-auto flex flex-col gap-3 border-t border-line px-1 pt-4">
          <DataStatus ws={ws} />
          {/* On small screens the theme button lives in the top bar instead. */}
          {!onClose && <ThemeToggle />}
        </div>
      )}
    </div>
  );
}

export default function Shell({ children }: { children: ReactNode }) {
  const [stamp, setStamp] = useState(0);
  const [menu, setMenu] = useState(false);
  const { data, error } = useReproduction(stamp);

  // The splash plays once per browser session, on whichever page is opened first.
  // "pending" covers the page until the client knows whether it already played.
  const seen = useStored("session", "mfstsp.splash");
  const splash = seen === undefined ? "pending" : seen === "1" ? "done" : "show";

  // The size filter is remembered between visits.
  const stored = useStored("local", "mfstsp.sizes");
  const sizes = useMemo(() => {
    try {
      const saved = JSON.parse(stored ?? "null");
      if (Array.isArray(saved)) return saved.filter((s) => (SIZES as readonly number[]).includes(s));
    } catch {}
    return [...SIZES];
  }, [stored]);
  const setSizes = (s: number[]) => writeStored("local", "mfstsp.sizes", JSON.stringify(s));

  // Mobile drawer: slides in when mounted, slides out before unmounting.
  const drawer = useRef<HTMLDivElement>(null);
  const backdrop = useRef<HTMLButtonElement>(null);
  const closing = useRef(false);
  useGSAP(
    () => {
      if (!menu || !drawer.current || !backdrop.current) return;
      closing.current = false;
      gsap
        .timeline()
        .fromTo(backdrop.current, { opacity: 0 }, { opacity: 1, duration: 0.4, ease: "power2.out" }, 0)
        .fromTo(drawer.current, { xPercent: -100 }, { xPercent: 0, duration: 0.55, ease: "expo.out" }, 0)
        .fromTo(drawer.current.querySelectorAll("nav a, nav button, nav span"), { x: -18, opacity: 0 }, { x: 0, opacity: 1, duration: 0.45, ease: "power3.out", stagger: 0.03 }, 0.12);
    },
    { dependencies: [menu] },
  );
  // Lock page scrolling behind the open drawer.
  useEffect(() => {
    if (!menu) return;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [menu]);
  const closeMenu = () => {
    if (!drawer.current || !backdrop.current || closing.current) return setMenu(false);
    closing.current = true;
    gsap
      .timeline({ onComplete: () => setMenu(false) })
      .to(drawer.current, { xPercent: -100, duration: 0.35, ease: "power3.in" }, 0)
      .to(backdrop.current, { opacity: 0, duration: 0.35, ease: "power2.in" }, 0);
  };

  // The desktop sidebar can collapse to an icon rail; the choice is remembered.
  const collapsed = useStored("local", "mfstsp.sidebar") === "collapsed";
  const toggle = () => writeStored("local", "mfstsp.sidebar", collapsed ? "open" : "collapsed");
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        writeStored("local", "mfstsp.sidebar", collapsed ? "open" : "collapsed");
      }
      if (e.key === "Escape") closeMenu();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [collapsed]);

  const ws: Workspace = {
    sizes,
    setSizes,
    data,
    error,
    refresh: () => {
      refreshData();
      setStamp((s) => s + 1);
    },
  };

  return (
    <Ctx.Provider value={ws}>
      <div className="flex min-h-full flex-1">
        <aside className={cx("sticky top-0 z-30 hidden h-screen shrink-0 border-r border-line bg-panel transition-[width] duration-300 ease-out lg:block", collapsed ? "w-[68px]" : "w-[264px]")}>
          <Sidebar ws={ws} collapsed={collapsed} onToggle={toggle} />
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-40 flex items-center justify-between border-b border-line bg-panel/95 px-4 py-2.5 backdrop-blur lg:hidden">
            <Logo />
            <div className="flex items-center gap-1">
              <ThemeToggle compact />
              <RailButton label="Open menu" onClick={() => setMenu(true)}>
                <Icon d={ICONS.menu} />
              </RailButton>
            </div>
          </header>
          {menu && (
            <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
              <button ref={backdrop} className="absolute inset-0 bg-black/40 opacity-0 backdrop-blur-[2px]" aria-label="Close menu" onClick={closeMenu} />
              <div ref={drawer} className="absolute inset-y-0 left-0 w-[284px] max-w-[85vw] border-r border-line bg-panel shadow-2xl">
                <Sidebar ws={ws} collapsed={false} onNavigate={closeMenu} onClose={closeMenu} />
              </div>
            </div>
          )}
          <main className="flex-1">
            {error && (
              <div className="m-6 rounded-xl border border-rose/30 bg-rose/5 p-4 text-sm text-rose">
                Could not load dashboard data ({error}). Run <code className="code">npm run data</code> in new/web, then refresh.
              </div>
            )}
            {children}
          </main>
          <footer className="border-t border-line px-6 py-5 text-center text-xs text-muted">mFSTSP research workspace · Reproducing Murray &amp; Raj (2019) · No benchmark or result files are written by this application.</footer>
        </div>
      </div>
      {splash === "show" && <SplashScreen onFinish={() => writeStored("session", "mfstsp.splash", "1")} />}
      {splash === "pending" && <div className="fixed inset-0 z-50 bg-black" />}
    </Ctx.Provider>
  );
}
