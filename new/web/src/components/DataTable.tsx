"use client";

import { ReactNode, useMemo, useState } from "react";
import { ExportButton, cx } from "./ui";

export type Column<T> = {
  key: string;
  label: string;
  value: (row: T) => string | number | boolean | null | undefined;
  render?: (row: T) => ReactNode;
  numeric?: boolean;
};

const PAGE = 25;

export function DataTable<T>({ rows, columns, name, empty = "No records match these filters." }: { rows: T[]; columns: Column<T>[]; name: string; empty?: string }) {
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const [page, setPage] = useState(0);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key)!;
    return [...rows].sort((a, b) => {
      const x = col.value(a);
      const y = col.value(b);
      if (x === y) return 0;
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      return (x < y ? -1 : 1) * sort.dir;
    });
  }, [rows, columns, sort]);

  const pages = Math.max(1, Math.ceil(sorted.length / PAGE));
  const current = Math.min(page, pages - 1);
  const shown = sorted.slice(current * PAGE, current * PAGE + PAGE);
  const exportRows = useMemo(() => sorted.map((r) => Object.fromEntries(columns.map((c) => [c.label, c.value(r)]))), [sorted, columns]);

  const fmtCell = (v: unknown, numeric?: boolean) => {
    if (v === null || v === undefined || v === "") return <span className="text-muted/60">—</span>;
    if (typeof v === "boolean") return v ? "Yes" : "No";
    if (typeof v === "number" && numeric) return v.toLocaleString("en-US", { maximumFractionDigits: 2 });
    return String(v);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-max text-left text-sm">
          <thead className="bg-panel-2 text-xs tracking-wide text-muted uppercase">
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={cx("cursor-pointer px-3 py-2.5 font-semibold whitespace-nowrap select-none hover:text-foreground", c.numeric && "text-right")} onClick={() => setSort(sort?.key === c.key ? { key: c.key, dir: sort.dir === 1 ? -1 : 1 } : { key: c.key, dir: 1 })}>
                  {c.label}
                  {sort?.key === c.key && <span className="ml-1 text-cyan">{sort.dir === 1 ? "↑" : "↓"}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r, i) => (
              <tr key={i} className="border-t border-line odd:bg-panel even:bg-panel-2/40 hover:bg-cyan/[0.04]">
                {columns.map((c) => (
                  <td key={c.key} className={cx("px-3 py-2 whitespace-nowrap", c.numeric && "text-right tabular-nums")}>
                    {c.render ? c.render(r) : fmtCell(c.value(r), c.numeric)}
                  </td>
                ))}
              </tr>
            ))}
            {!shown.length && (
              <tr>
                <td colSpan={columns.length} className="px-3 py-8 text-center text-muted">
                  {empty}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted">
        <span>
          {sorted.length.toLocaleString()} rows{pages > 1 && ` · page ${current + 1} of ${pages}`}
        </span>
        <div className="flex items-center gap-2">
          {pages > 1 && (
            <>
              <button className="rounded border border-line bg-panel px-2 py-1 hover:text-foreground disabled:opacity-40" disabled={current === 0} onClick={() => setPage(current - 1)}>
                ← Prev
              </button>
              <button className="rounded border border-line bg-panel px-2 py-1 hover:text-foreground disabled:opacity-40" disabled={current >= pages - 1} onClick={() => setPage(current + 1)}>
                Next →
              </button>
            </>
          )}
          <ExportButton rows={exportRows} name={name} />
        </div>
      </div>
    </div>
  );
}

export function WinnerBadge({ winner }: { winner: string }) {
  const style =
    winner === "Proposed" ? "bg-mint/10 text-mint border-mint/30" : winner === "Archive" ? "bg-orange/10 text-orange border-orange/30" : winner === "Tie" ? "bg-violet/10 text-violet border-violet/30" : "bg-panel-2 text-muted border-line";
  return <span className={cx("rounded-full border px-2 py-0.5 text-xs font-semibold", style)}>{winner}</span>;
}
