"use client";

import { useEffect, useState } from "react";
import type { InstanceData, ResultsData, Row, SourceExcerpt } from "./types";

// Files are produced by scripts/build-data.mjs (runs before dev/build).
const cache = new Map<string, Promise<unknown>>();
let version = 0;

function load<T>(url: string): Promise<T> {
  const key = `${url}?v=${version}`;
  if (!cache.has(key)) {
    cache.set(
      key,
      fetch(key, { cache: version ? "no-store" : "default" }).then((r) => {
        if (!r.ok) throw new Error(`${url}: ${r.status}`);
        return r.json();
      }),
    );
  }
  return cache.get(key) as Promise<T>;
}

export function refreshData() {
  version++;
  cache.clear();
}

type State<T> = { data: T | null; error: string | null };

function useJSON<T>(url: string | null, stamp = 0): State<T> {
  const [state, setState] = useState<State<T> & { url: string | null }>({ data: null, error: null, url: null });
  useEffect(() => {
    if (!url) return;
    let alive = true;
    load<T>(url)
      .then((data) => alive && setState({ data, error: null, url }))
      .catch((e) => alive && setState({ data: null, error: String(e.message ?? e), url }));
    return () => {
      alive = false;
    };
  }, [url, stamp]);
  return state.url === url ? state : { data: null, error: null };
}

export const useResults = (stamp = 0) => useJSON<ResultsData>("/data/results.json", stamp);
export const useInstance = (name: string | null) => useJSON<InstanceData>(name ? `/data/solutions/${name}.json` : null);
export const useSources = () => useJSON<Record<string, SourceExcerpt>>("/data/source.json");

export function configuration(r: Row) {
  const f = (v: number | null) => (v === null ? "?" : String(v));
  return `vehicle=${f(r.vehicleFileID)} | UAVs=${f(r.numUAVs)} | E=${f(r.Etype)} | limit=${f(r.cutoffTime)}s | depot=${f(r.requireTruckAtDepot)} | driver=${f(r.requireDriver)} | iter=${f(r.ITER)}`;
}

export const experimentLabel = (r: Pick<Row, "algorithm" | "source">) => `${r.algorithm} · ${r.source}`;
