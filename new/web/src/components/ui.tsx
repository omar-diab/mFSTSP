"use client";

import { ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { download, toCSV } from "@/lib/csv";

gsap.registerPlugin(useGSAP);

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

// Page-level entrance: children marked .reveal slide in with a stagger.
export function Page({ children }: { children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  useGSAP(
    () => {
      gsap.from(".reveal", { y: 24, opacity: 0, duration: 0.7, ease: "power3.out", stagger: 0.07, clearProps: "all" });
    },
    { scope: root },
  );
  return (
    <div ref={root} className="mx-auto flex w-full max-w-[1500px] flex-col gap-6 px-4 pt-6 pb-16 sm:px-8 lg:pt-10">
      {children}
    </div>
  );
}

export function Hero({ title, subtitle, tags = [] }: { title: string; subtitle: string; tags?: string[] }) {
  return (
    <section className="reveal panel relative overflow-hidden px-6 py-7 sm:px-8 sm:py-8">
      <div className="eyebrow mb-3">mFSTSP · Research workspace</div>
      <h1 className="max-w-4xl font-serif text-3xl leading-tight font-bold tracking-tight sm:text-[2.4rem]">{title}</h1>
      <p className="mt-3 max-w-3xl text-[0.95rem] leading-relaxed text-muted">{subtitle}</p>
      <div className="mt-5 flex flex-wrap gap-2">
        {["Recorded data · read-only", "Truck + multiple UAVs", ...tags].map((t) => (
          <span key={t} className="rounded-md border border-line bg-panel-2 px-2.5 py-1 text-[0.68rem] font-semibold tracking-wider text-muted uppercase">
            {t}
          </span>
        ))}
      </div>
    </section>
  );
}

export function Panel({ title, subtitle, actions, children, className }: { title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("reveal panel p-5 sm:p-6", className)}>
      {(title || actions) && (
        <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-lg font-bold tracking-tight">{title}</h2>}
            {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

// Animated KPI: numbers count up whenever the value changes.
export function Kpi({ label, value, suffix = "", digits = 0, detail, tone = "cyan" }: { label: string; value: number | null; suffix?: string; digits?: number; detail: string; tone?: "cyan" | "orange" | "mint" | "violet" }) {
  const el = useRef<HTMLSpanElement>(null);
  const last = useRef(0);
  const [open, setOpen] = useState(false);
  useGSAP(
    () => {
      if (!el.current) return;
      if (value === null || !Number.isFinite(value)) {
        el.current.textContent = "Unavailable";
        return;
      }
      const state = { v: last.current };
      gsap.to(state, {
        v: value,
        duration: 1.1,
        ease: "power3.out",
        onUpdate: () => {
          if (el.current) el.current.textContent = state.v.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits }) + suffix;
        },
      });
      last.current = value;
    },
    { dependencies: [value, digits, suffix] },
  );
  const toneClass = { cyan: "bg-cyan", orange: "bg-orange", mint: "bg-mint", violet: "bg-violet" }[tone];
  return (
    <div className="reveal panel relative overflow-hidden p-5">
      <div className={cx("absolute inset-y-0 left-0 w-1", toneClass)} />
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm text-muted">{label}</span>
        <button onClick={() => setOpen(!open)} className="grid h-5 w-5 shrink-0 place-items-center rounded-full border border-line text-[0.65rem] text-muted hover:border-cyan hover:text-cyan" aria-label={`About ${label}`} aria-expanded={open}>
          i
        </button>
      </div>
      <div className="mt-2 text-[1.85rem] leading-none font-bold tracking-tight text-foreground tabular-nums">
        <span ref={el}>—</span>
      </div>
      {open && <p className="mt-3 border-t border-line pt-3 text-xs leading-relaxed text-muted">{detail}</p>}
    </div>
  );
}

export function KpiRow({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{children}</div>;
}

type Tone = "info" | "warn" | "ok" | "error";
export function Note({ tone = "info", children }: { tone?: Tone; children: ReactNode }) {
  const styles: Record<Tone, string> = {
    info: "border-cyan/30 bg-cyan/[0.06] [&>span]:text-cyan",
    warn: "border-orange/35 bg-orange/[0.07] [&>span]:text-orange",
    ok: "border-mint/35 bg-mint/[0.07] [&>span]:text-mint",
    error: "border-rose/35 bg-rose/[0.07] [&>span]:text-rose",
  };
  const icon = { info: "ℹ", warn: "!", ok: "✓", error: "×" }[tone];
  return (
    <div className={cx("flex gap-3 rounded-xl border px-4 py-3 text-sm leading-relaxed", styles[tone])}>
      <span className="mt-px font-bold">{icon}</span>
      <div>{children}</div>
    </div>
  );
}

export function Caption({ children }: { children: ReactNode }) {
  return <p className="text-xs leading-relaxed text-muted">{children}</p>;
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: readonly T[]; value: T; onChange: (t: T) => void }) {
  const bar = useRef<HTMLDivElement>(null);
  const ink = useRef<HTMLSpanElement>(null);
  useGSAP(
    () => {
      const active = bar.current?.querySelector<HTMLButtonElement>(`[data-active="true"]`);
      if (active && ink.current) gsap.to(ink.current, { x: active.offsetLeft, width: active.offsetWidth, duration: 0.45, ease: "power3.out" });
    },
    { dependencies: [value], scope: bar },
  );
  return (
    <div ref={bar} className="relative flex gap-1 overflow-x-auto border-b border-line">
      {tabs.map((t) => (
        <button key={t} data-active={t === value} onClick={() => onChange(t)} className={cx("shrink-0 px-4 py-2.5 text-sm font-medium transition-colors", t === value ? "text-cyan" : "text-muted hover:text-foreground")}>
          {t}
        </button>
      ))}
      <span ref={ink} className="absolute bottom-0 left-0 h-0.5 w-0 rounded-full bg-cyan" />
    </div>
  );
}

// Fades content in whenever `k` changes (tab switches, filter changes).
export function FadeSwap({ k, children }: { k: string; children: ReactNode }) {
  const el = useRef<HTMLDivElement>(null);
  useGSAP(() => {
    gsap.fromTo(el.current, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.45, ease: "power2.out" });
  }, { dependencies: [k] });
  return (
    <div ref={el} className="flex flex-col gap-5">
      {children}
    </div>
  );
}

export function Field({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={cx("flex min-w-0 flex-col gap-1.5", className)}>
      <span className="text-xs font-semibold tracking-wide text-muted uppercase">{label}</span>
      {children}
    </label>
  );
}

const control = "w-full rounded-lg border border-line bg-panel px-3 py-2 text-sm text-foreground outline-none transition-colors hover:border-line-strong focus:border-cyan/60 focus:ring-2 focus:ring-cyan/15";

export function Select<T extends string | number>({ value, options, onChange, format }: { value: T; options: readonly T[]; onChange: (v: T) => void; format?: (v: T) => string }) {
  return (
    <select className={control} value={String(value)} onChange={(e) => onChange(options.find((o) => String(o) === e.target.value) as T)}>
      {options.map((o) => (
        <option key={String(o)} value={String(o)}>
          {format ? format(o) : String(o)}
        </option>
      ))}
    </select>
  );
}

export function Chips<T extends string | number>({ options, value, onChange, format }: { options: readonly T[]; value: T[]; onChange: (v: T[]) => void; format?: (v: T) => string }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = value.includes(o);
        return (
          <button
            key={String(o)}
            onClick={() => onChange(on ? value.filter((v) => v !== o) : [...value, o])}
            className={cx("rounded-lg border px-3 py-1.5 text-xs font-medium transition-all", on ? "border-cyan/50 bg-cyan/10 text-cyan" : "border-line bg-panel text-muted hover:border-line-strong hover:text-foreground")}
          >
            {format ? format(o) : String(o)}
          </button>
        );
      })}
    </div>
  );
}

export function Segmented<T extends string>({ options, value, onChange }: { options: readonly T[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex flex-wrap rounded-lg border border-line bg-panel-2 p-0.5">
      {options.map((o) => (
        <button key={o} onClick={() => onChange(o)} className={cx("rounded-md px-3 py-1.5 text-xs font-medium transition-colors", o === value ? "bg-panel text-cyan shadow-sm" : "text-muted hover:text-foreground")}>
          {o}
        </button>
      ))}
    </div>
  );
}

// Searchable multi-select; an empty selection means "all".
export function MultiSelect({ options, value, onChange, placeholder = "All", format }: { options: string[]; value: string[]; onChange: (v: string[]) => void; placeholder?: string; format?: (v: string) => string }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const box = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const shown = useMemo(() => options.filter((o) => (format ? format(o) : o).toLowerCase().includes(query.toLowerCase())), [options, query, format]);
  const label = value.length === 0 ? placeholder : value.length === 1 ? (format ? format(value[0]) : value[0]) : `${value.length} selected`;
  return (
    <div ref={box} className="relative">
      <button className={cx(control, "flex items-center justify-between text-left")} onClick={() => setOpen(!open)} aria-expanded={open} aria-controls={id}>
        <span className={cx("truncate", !value.length && "text-muted")}>{label}</span>
        <span className="ml-2 text-muted">▾</span>
      </button>
      {open && (
        <div id={id} className="absolute z-30 mt-1 w-full min-w-[260px] rounded-lg border border-line bg-panel p-2 shadow-xl">
          <input autoFocus className={cx(control, "mb-2")} placeholder="Search…" value={query} onChange={(e) => setQuery(e.target.value)} />
          <div className="mb-1 flex justify-between px-1 text-xs">
            <button className="text-cyan hover:underline" onClick={() => onChange([...new Set([...value, ...shown])])}>
              Select shown
            </button>
            <button className="text-muted hover:text-foreground" onClick={() => onChange([])}>
              Clear (all)
            </button>
          </div>
          <div className="max-h-64 overflow-y-auto">
            {shown.map((o) => (
              <label key={o} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-panel-2">
                <input type="checkbox" checked={value.includes(o)} onChange={(e) => onChange(e.target.checked ? [...value, o] : value.filter((v) => v !== o))} />
                <span className="truncate">{format ? format(o) : o}</span>
              </label>
            ))}
            {!shown.length && <p className="px-2 py-3 text-sm text-muted">No matches.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

export function Button({ children, onClick, tone = "ghost", className, disabled }: { children: ReactNode; onClick?: () => void; tone?: "ghost" | "primary"; className?: string; disabled?: boolean }) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg border px-3.5 py-2 text-sm font-medium transition-all disabled:opacity-40",
        tone === "primary" ? "border-cyan bg-cyan text-panel hover:opacity-90" : "border-line bg-panel text-foreground hover:border-line-strong hover:bg-panel-2",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function ExportButton({ rows, name }: { rows: Record<string, unknown>[]; name: string }) {
  return (
    <Button onClick={() => download(`${name}.csv`, toCSV(rows))} disabled={!rows.length}>
      ↓ Export CSV
    </Button>
  );
}

export function Details({ summary, children }: { summary: string; children: ReactNode }) {
  return (
    <details className="reveal group panel overflow-hidden">
      <summary className="flex cursor-pointer list-none items-center justify-between px-5 py-4 text-sm font-semibold hover:bg-panel-2">
        {summary}
        <span className="text-muted transition-transform group-open:rotate-180">▾</span>
      </summary>
      <div className="border-t border-line p-5">{children}</div>
    </details>
  );
}

export function Loading({ label = "Reading recorded experiments…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-16 text-sm text-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-cyan/25 border-t-cyan" />
      {label}
    </div>
  );
}
