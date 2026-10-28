"use client";

import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { box, compact, isNum, niceTicks } from "@/lib/stats";

gsap.registerPlugin(useGSAP);

const M = { top: 14, right: 18, bottom: 40, left: 62 };
// Gridlines and labels follow the theme through CSS variables.
const GRID = "stroke-(--grid)";
const AXIS = "fill-(--axis)";

export type Series<V> = { name: string; color: string; values: V };

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  // null until the first measurement, so entrance animations start at the final layout.
  const [measured, setWidth] = useState<number | null>(null);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, measured ?? 640, measured !== null] as const;
}

type Tip = { x: number; y: number; content: ReactNode } | null;

function useTip() {
  const [tip, setTip] = useState<Tip>(null);
  const show = (e: React.MouseEvent, content: ReactNode) => {
    const host = (e.currentTarget as SVGElement).closest("[data-chart]")!.getBoundingClientRect();
    setTip({ x: e.clientX - host.left, y: e.clientY - host.top, content });
  };
  return { tip, show, hide: () => setTip(null) };
}

function Tooltip({ tip, width }: { tip: Tip; width: number }) {
  if (!tip) return null;
  const left = tip.x > width - 220 ? tip.x - 14 : tip.x + 14;
  return (
    <div
      className="pointer-events-none absolute z-20 max-w-[240px] rounded-lg border border-line bg-tooltip px-3 py-2 text-xs leading-relaxed shadow-lg"
      style={{ left, top: tip.y + 12, transform: tip.x > width - 220 ? "translateX(-100%)" : undefined }}
    >
      {tip.content}
    </div>
  );
}

export function ChartCard({ title, subtitle, legend, children }: { title: string; subtitle?: string; legend?: { name: string; color: string }[]; children: ReactNode }) {
  return (
    <figure className="reveal rounded-xl border border-line bg-panel p-4">
      <figcaption className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold">{title}</div>
          {subtitle && <div className="mt-0.5 text-xs text-muted">{subtitle}</div>}
        </div>
        {legend && legend.length > 0 && (
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {legend.map((l) => (
              <span key={l.name} className="flex items-center gap-1.5 text-xs text-muted">
                <span className="h-2.5 w-2.5 rounded-sm" style={{ background: l.color }} />
                {l.name}
              </span>
            ))}
          </div>
        )}
      </figcaption>
      {children}
    </figure>
  );
}

type Scale = { (v: number): number; ticks: number[]; log: boolean };

function linear(d0: number, d1: number, r0: number, r1: number, zero = true): Scale {
  let lo = zero ? Math.min(0, d0) : d0;
  let hi = d1;
  if (!isNum(lo) || !isNum(hi)) {
    lo = 0;
    hi = 1;
  }
  const ticks = niceTicks(lo, hi);
  lo = Math.min(lo, ticks[0] ?? lo);
  hi = Math.max(hi, ticks[ticks.length - 1] ?? hi);
  if (lo === hi) hi = lo + 1;
  const s = ((v: number) => r0 + ((v - lo) / (hi - lo)) * (r1 - r0)) as Scale;
  s.ticks = ticks;
  s.log = false;
  return s;
}

function logScale(d0: number, d1: number, r0: number, r1: number): Scale {
  const lo = Math.floor(Math.log10(Math.max(d0, 1e-3)));
  const hi = Math.ceil(Math.log10(Math.max(d1, 1e-3)));
  const top = hi === lo ? hi + 1 : hi;
  const s = ((v: number) => r0 + ((Math.log10(Math.max(v, 1e-3)) - lo) / (top - lo)) * (r1 - r0)) as Scale;
  s.ticks = Array.from({ length: top - lo + 1 }, (_, i) => 10 ** (lo + i));
  s.log = true;
  return s;
}

function YAxis({ y, width, label, height }: { y: Scale; width: number; label?: string; height: number }) {
  return (
    <g>
      {y.ticks.map((t) => (
        <g key={t} transform={`translate(0 ${y(t)})`}>
          <line x1={M.left} x2={width - M.right} className={GRID} strokeDasharray={t === 0 ? undefined : "3 4"} />
          <text x={M.left - 8} dy="0.32em" textAnchor="end" className={AXIS} fontSize="11">
            {compact(t)}
          </text>
        </g>
      ))}
      {label && (
        <text transform={`translate(14 ${(M.top + height - M.bottom) / 2}) rotate(-90)`} textAnchor="middle" className={AXIS} fontSize="11">
          {label}
        </text>
      )}
    </g>
  );
}

function XLabels({ categories, x, band, height, rotate }: { categories: (string | number)[]; x: (c: string | number) => number; band: number; height: number; rotate?: boolean }) {
  // Thin out labels when bands get too narrow to read.
  const every = Math.max(1, Math.ceil(28 / band));
  return (
    <g>
      {categories.filter((_, i) => i % every === 0).map((c) => (
        <text
          key={String(c)}
          x={x(c) + band / 2}
          y={height - M.bottom + 16}
          textAnchor={rotate ? "end" : "middle"}
          className={AXIS}
          fontSize="11"
          transform={rotate ? `rotate(-35 ${x(c) + band / 2} ${height - M.bottom + 16})` : undefined}
        >
          {String(c)}
        </text>
      ))}
    </g>
  );
}

// Entrance animation once per data change. Transforms are cleared afterwards so
// later re-layouts (resizes) never inherit a stale SVG transform origin.
function useGrow(scope: React.RefObject<HTMLDivElement | null>, sig: unknown, measured: boolean) {
  useGSAP(
    () => {
      const root = scope.current;
      if (!measured || !root) return;
      const grow = root.querySelectorAll(".grow");
      const pop = root.querySelectorAll(".pop");
      if (grow.length) gsap.fromTo(grow, { scaleY: 0, transformOrigin: "50% 100%" }, { scaleY: 1, duration: 0.8, ease: "power3.out", stagger: { amount: 0.35 }, clearProps: "transform" });
      if (pop.length) gsap.fromTo(pop, { opacity: 0 }, { opacity: 1, duration: 0.6, ease: "power2.out", stagger: { amount: 0.4 }, clearProps: "opacity" });
      root.querySelectorAll<SVGPathElement>(".draw").forEach((p) => {
        const len = p.getTotalLength();
        gsap.fromTo(p, { strokeDasharray: len, strokeDashoffset: len }, { strokeDashoffset: 0, duration: 1.1, ease: "power2.inOut", clearProps: "strokeDasharray,strokeDashoffset" });
      });
    },
    { scope, dependencies: [JSON.stringify(sig), measured] },
  );
}

function Empty({ height }: { height: number }) {
  return (
    <div className="grid place-items-center text-sm text-muted" style={{ height }}>
      No values to plot in this scope.
    </div>
  );
}

// ---------------------------------------------------------------------------

export function BoxChart({ categories, series, yLabel, height = 300, log = false }: { categories: (string | number)[]; series: Series<Record<string, number[]>>[]; yLabel?: string; height?: number; log?: boolean }) {
  const [ref, width, measured] = useWidth<HTMLDivElement>();
  const { tip, show, hide } = useTip();
  const all = series.flatMap((s) => Object.values(s.values).flat()).filter(isNum);
  const sig = JSON.stringify([categories, series.map((s) => [s.name, Object.values(s.values).map((v) => v.length)])]);
  useGrow(ref, [sig], measured);
  if (!all.length)
    return (
      <div ref={ref}>
        <Empty height={height} />
      </div>
    );
  const y = log ? logScale(Math.min(...all), Math.max(...all), height - M.bottom, M.top) : linear(Math.min(...all), Math.max(...all), height - M.bottom, M.top);
  const band = (width - M.left - M.right) / categories.length;
  const x = (c: string | number) => M.left + categories.indexOf(c) * band;
  const inner = band * 0.75;
  const w = Math.min(46, inner / series.length);

  return (
    <div ref={ref} data-chart className="relative">
      <svg width={width} height={height} onMouseLeave={hide}>
        <YAxis y={y} width={width} label={yLabel} height={height} />
        <XLabels categories={categories} x={x} band={band} height={height} />
        {categories.map((c) =>
          series.map((s, i) => {
            const b = box((s.values[String(c)] ?? []).filter(isNum));
            if (!b) return null;
            const cxp = x(c) + (band - w * series.length) / 2 + i * w + w / 2;
            const bw = w * 0.7;
            return (
              <g
                key={`${c}-${s.name}`}
                onMouseMove={(e) =>
                  show(
                    e,
                    <>
                      <b style={{ color: s.color }}>{s.name}</b> · {c}
                      <br />n = {b.n} · median {compact(b.median)}
                      <br />Q1 {compact(b.q1)} · Q3 {compact(b.q3)}
                      <br />mean {compact(b.mean)}
                    </>,
                  )
                }
              >
                <line x1={cxp} x2={cxp} y1={y(b.min)} y2={y(b.max)} stroke={s.color} strokeOpacity="0.6" />
                <line x1={cxp - bw / 4} x2={cxp + bw / 4} y1={y(b.min)} y2={y(b.min)} stroke={s.color} strokeOpacity="0.6" />
                <line x1={cxp - bw / 4} x2={cxp + bw / 4} y1={y(b.max)} y2={y(b.max)} stroke={s.color} strokeOpacity="0.6" />
                <rect className="grow" x={cxp - bw / 2} y={y(b.q3)} width={bw} height={Math.max(1, y(b.q1) - y(b.q3))} rx="3" fill={s.color} fillOpacity="0.22" stroke={s.color} />
                <line x1={cxp - bw / 2} x2={cxp + bw / 2} y1={y(b.median)} y2={y(b.median)} className="stroke-(--foreground)" strokeWidth="2" />
                {b.outliers.slice(0, 60).map((o, k) => (
                  <circle key={k} className="pop" cx={cxp} cy={y(o)} r="2.4" fill={s.color} fillOpacity="0.7" />
                ))}
              </g>
            );
          }),
        )}
      </svg>
      <Tooltip tip={tip} width={width} />
    </div>
  );
}

export function LineChart({ categories, series, yLabel, height = 280, zeroLine = false }: { categories: (string | number)[]; series: Series<Record<string, number | null>>[]; yLabel?: string; height?: number; zeroLine?: boolean }) {
  const [ref, width, measured] = useWidth<HTMLDivElement>();
  const { tip, show, hide } = useTip();
  const all = series.flatMap((s) => Object.values(s.values)).filter(isNum);
  const sig = JSON.stringify([categories, series.map((s) => [s.name, s.values])]);
  useGrow(ref, [sig], measured);
  if (!all.length)
    return (
      <div ref={ref}>
        <Empty height={height} />
      </div>
    );
  const y = linear(Math.min(...all), Math.max(...all), height - M.bottom, M.top, zeroLine || Math.min(...all) > 0);
  const band = (width - M.left - M.right) / categories.length;
  const x = (c: string | number) => M.left + categories.indexOf(c) * band;

  return (
    <div ref={ref} data-chart className="relative">
      <svg width={width} height={height} onMouseLeave={hide}>
        <defs>
          {series.map((s, i) => (
            <linearGradient key={s.name} id={`lg-${i}-${s.color.slice(1)}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor={s.color} stopOpacity="0.25" />
              <stop offset="1" stopColor={s.color} stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>
        <YAxis y={y} width={width} label={yLabel} height={height} />
        <XLabels categories={categories} x={x} band={band} height={height} />
        {series.map((s, i) => {
          const pts = categories.map((c) => [x(c) + band / 2, s.values[String(c)]] as const).filter((p): p is readonly [number, number] => isNum(p[1]));
          if (!pts.length) return null;
          const d = pts.map(([px, py], k) => `${k ? "L" : "M"}${px},${y(py)}`).join(" ");
          const area = `${d} L${pts[pts.length - 1][0]},${y(Math.max(0, y.ticks[0] ?? 0))} L${pts[0][0]},${y(Math.max(0, y.ticks[0] ?? 0))} Z`;
          return (
            <g key={s.name}>
              {series.length <= 3 && <path d={area} fill={`url(#lg-${i}-${s.color.slice(1)})`} className="pop" />}
              <path className="draw" d={d} fill="none" stroke={s.color} strokeWidth="2.5" strokeLinejoin="round" />
              {pts.map(([px, py], k) => (
                <circle
                  key={k}
                  cx={px}
                  cy={y(py)}
                  r="4.5"
                  className="pop fill-(--panel)"
                  stroke={s.color}
                  strokeWidth="2.5"
                  onMouseMove={(e) =>
                    show(
                      e,
                      <>
                        <b style={{ color: s.color }}>{s.name}</b>
                        <br />
                        {categories[categories.findIndex((c) => x(c) + band / 2 === px)]} · {py.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                      </>,
                    )
                  }
                />
              ))}
            </g>
          );
        })}
      </svg>
      <Tooltip tip={tip} width={width} />
    </div>
  );
}

export type Point = { x: number; y: number; label: string };

export function ScatterChart({ series, xLabel, yLabel, height = 320, logX = true }: { series: Series<Point[]>[]; xLabel: string; yLabel: string; height?: number; logX?: boolean }) {
  const [ref, width, measured] = useWidth<HTMLDivElement>();
  const { tip, show, hide } = useTip();
  const pts = series.flatMap((s) => s.values);
  const sig = JSON.stringify(series.map((s) => [s.name, s.values.length]));
  useGrow(ref, [sig], measured);
  if (!pts.length)
    return (
      <div ref={ref}>
        <Empty height={height} />
      </div>
    );
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const x = logX ? logScale(Math.min(...xs), Math.max(...xs), M.left, width - M.right) : linear(Math.min(...xs), Math.max(...xs), M.left, width - M.right);
  const y = linear(Math.min(...ys), Math.max(...ys), height - M.bottom, M.top);
  return (
    <div ref={ref} data-chart className="relative">
      <svg width={width} height={height} onMouseLeave={hide}>
        <YAxis y={y} width={width} label={yLabel} height={height} />
        {x.ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={M.top} y2={height - M.bottom} className={GRID} strokeDasharray="3 4" />
            <text x={x(t)} y={height - M.bottom + 16} textAnchor="middle" className={AXIS} fontSize="11">
              {compact(t)}
            </text>
          </g>
        ))}
        <text x={(M.left + width - M.right) / 2} y={height - 4} textAnchor="middle" className={AXIS} fontSize="11">
          {xLabel}
          {logX ? " · log scale" : ""}
        </text>
        {series.map((s) =>
          s.values.map((p, i) => (
            <circle
              key={`${s.name}-${i}`}
              className="pop"
              cx={x(p.x)}
              cy={y(p.y)}
              r="3.6"
              fill={s.color}
              fillOpacity="0.55"
              stroke={s.color}
              onMouseMove={(e) =>
                show(
                  e,
                  <>
                    <b style={{ color: s.color }}>{s.name}</b>
                    <br />
                    {p.label}
                    <br />
                    {xLabel}: {p.x.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                    <br />
                    {yLabel}: {p.y.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                  </>,
                )
              }
            />
          )),
        )}
      </svg>
      <Tooltip tip={tip} width={width} />
    </div>
  );
}

// Grouped or stacked bars over categories.
export function BarChart({ categories, series, yLabel, height = 280, stacked = false, rotate = false }: { categories: (string | number)[]; series: Series<Record<string, number>>[]; yLabel?: string; height?: number; stacked?: boolean; rotate?: boolean }) {
  const [ref, width, measured] = useWidth<HTMLDivElement>();
  const { tip, show, hide } = useTip();
  const bottom = rotate ? 70 : 0;
  const totals = categories.map((c) => (stacked ? series.reduce((a, s) => a + (s.values[String(c)] ?? 0), 0) : Math.max(...series.map((s) => s.values[String(c)] ?? 0))));
  const lows = series.flatMap((s) => Object.values(s.values)).filter(isNum);
  const sig = JSON.stringify([categories, series.map((s) => s.values)]);
  useGrow(ref, [sig], measured);
  if (!lows.length)
    return (
      <div ref={ref}>
        <Empty height={height} />
      </div>
    );
  const y = linear(Math.min(0, ...lows), Math.max(...totals, 0), height - M.bottom - bottom, M.top);
  const band = (width - M.left - M.right) / categories.length;
  const x = (c: string | number) => M.left + categories.indexOf(c) * band;
  const inner = band * 0.78;
  const w = stacked ? inner : inner / series.length;

  return (
    <div ref={ref} data-chart className="relative">
      <svg width={width} height={height} onMouseLeave={hide}>
        <YAxis y={y} width={width} label={yLabel} height={height - bottom} />
        <XLabels categories={categories} x={x} band={band} height={height - bottom} rotate={rotate} />
        {categories.map((c) => {
          let acc = 0;
          return series.map((s, i) => {
            const v = s.values[String(c)] ?? 0;
            if (!v) return null;
            const left = x(c) + (band - inner) / 2 + (stacked ? 0 : i * w);
            const y0 = stacked ? y(acc) : y(0);
            const y1 = stacked ? y(acc + v) : y(v);
            acc += v;
            return (
              <rect
                key={`${c}-${s.name}`}
                className={v >= 0 ? "grow" : "pop"}
                x={left + 1}
                y={Math.min(y0, y1)}
                width={Math.max(1, w - 2)}
                height={Math.max(1, Math.abs(y0 - y1))}
                rx={Math.min(4, w / 4)}
                fill={s.color}
                fillOpacity="0.85"
                onMouseMove={(e) =>
                  show(
                    e,
                    <>
                      <b style={{ color: s.color }}>{s.name}</b>
                      <br />
                      {c}: {v.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                    </>,
                  )
                }
              />
            );
          });
        })}
      </svg>
      <Tooltip tip={tip} width={width} />
    </div>
  );
}

// One bar per item, sorted; positive above zero, negative below.
export function RankedBars({ items, yLabel, height = 280 }: { items: { label: string; value: number; color: string; detail?: string }[]; yLabel?: string; height?: number }) {
  const [ref, width, measured] = useWidth<HTMLDivElement>();
  const { tip, show, hide } = useTip();
  const sorted = useMemo(() => [...items].sort((a, b) => b.value - a.value), [items]);
  useGrow(ref, [sorted.length, sorted[0]?.value], measured);
  if (!sorted.length)
    return (
      <div ref={ref}>
        <Empty height={height} />
      </div>
    );
  const vals = sorted.map((i) => i.value);
  const y = linear(Math.min(0, ...vals), Math.max(0, ...vals), height - M.bottom, M.top);
  const band = (width - M.left - M.right) / sorted.length;
  return (
    <div ref={ref} data-chart className="relative">
      <svg width={width} height={height} onMouseLeave={hide}>
        <YAxis y={y} width={width} label={yLabel} height={height} />
        {sorted.map((it, i) => (
          <rect
            key={i}
            className="pop"
            x={M.left + i * band + band * 0.12}
            y={Math.min(y(0), y(it.value))}
            width={Math.max(1, band * 0.76)}
            height={Math.max(1, Math.abs(y(it.value) - y(0)))}
            rx={Math.min(3, band / 4)}
            fill={it.color}
            fillOpacity="0.85"
            onMouseMove={(e) =>
              show(
                e,
                <>
                  <b>{it.label}</b>
                  <br />
                  {it.value.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                  {it.detail && (
                    <>
                      <br />
                      {it.detail}
                    </>
                  )}
                </>,
              )
            }
          />
        ))}
        <line x1={M.left} x2={width - M.right} y1={y(0)} y2={y(0)} className="stroke-(--line-strong)" />
        <text x={(M.left + width - M.right) / 2} y={height - 14} textAnchor="middle" className={AXIS} fontSize="11">
          {sorted.length} compatible pairs, sorted by value
        </text>
      </svg>
      <Tooltip tip={tip} width={width} />
    </div>
  );
}

export function histogram(values: number[], bins = 16) {
  if (!values.length) return { edges: [] as number[], labels: [] as string[], index: () => 0 };
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const step = (hi - lo || 1) / bins;
  const edges = Array.from({ length: bins }, (_, i) => lo + i * step);
  const labels = edges.map((e) => `${compact(e)}`);
  const index = (v: number) => Math.min(bins - 1, Math.floor((v - lo) / step));
  return { edges, labels, index };
}
