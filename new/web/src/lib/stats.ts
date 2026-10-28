export function mean(values: number[]) {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : NaN;
}

export function quantile(sorted: number[], q: number) {
  if (!sorted.length) return NaN;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

export type Box = { min: number; q1: number; median: number; q3: number; max: number; outliers: number[]; n: number; mean: number };

// Tukey box: whiskers at the furthest points within 1.5 IQR.
export function box(values: number[]): Box | null {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const q1 = quantile(s, 0.25);
  const q3 = quantile(s, 0.75);
  const iqr = q3 - q1;
  const inside = s.filter((v) => v >= q1 - 1.5 * iqr && v <= q3 + 1.5 * iqr);
  return {
    min: inside[0],
    q1,
    median: quantile(s, 0.5),
    q3,
    max: inside[inside.length - 1],
    outliers: s.filter((v) => v < q1 - 1.5 * iqr || v > q3 + 1.5 * iqr),
    n: s.length,
    mean: mean(s),
  };
}

export function groupBy<T, K extends string | number>(items: T[], key: (t: T) => K) {
  const out = new Map<K, T[]>();
  for (const item of items) {
    const k = key(item);
    if (!out.has(k)) out.set(k, []);
    out.get(k)!.push(item);
  }
  return out;
}

export const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function fmt(v: number | null | undefined, digits = 2) {
  return isNum(v) ? v.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits }) : "Unavailable";
}

export function niceTicks(min: number, max: number, count = 5) {
  if (!isNum(min) || !isNum(max)) return [];
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const raw = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw)!;
  const ticks = [];
  for (let t = Math.ceil(min / step) * step; t <= max + step * 1e-9; t += step) ticks.push(Number(t.toPrecision(12)));
  return ticks;
}

export function compact(v: number) {
  const a = Math.abs(v);
  if (a >= 1e6) return (v / 1e6).toFixed(1) + "M";
  if (a >= 1e4) return (v / 1e3).toFixed(0) + "k";
  if (a >= 1e3) return (v / 1e3).toFixed(1) + "k";
  if (a >= 10 || a === 0) return v.toFixed(0);
  if (a >= 1) return v.toFixed(1);
  return v.toPrecision(2);
}
