"use client";

import { useEffect, useState } from "react";
import type { ReproductionData } from "./types";

// public/data/reproduction.json is produced by scripts/build-data.mjs (runs before dev/build).
let version = 0;
let cached: Promise<ReproductionData> | null = null;

function load(): Promise<ReproductionData> {
  if (!cached) {
    cached = fetch(`/data/reproduction.json?v=${version}`, { cache: version ? "no-store" : "default" }).then((r) => {
      if (!r.ok) throw new Error(`reproduction.json: ${r.status}`);
      return r.json();
    });
  }
  return cached;
}

export function refreshData() {
  version++;
  cached = null;
}

export function useReproduction(stamp = 0) {
  const [state, setState] = useState<{ data: ReproductionData | null; error: string | null; stamp: number }>({ data: null, error: null, stamp: -1 });
  useEffect(() => {
    let alive = true;
    load()
      .then((data) => alive && setState({ data, error: null, stamp }))
      .catch((e) => alive && setState({ data: null, error: String(e.message ?? e), stamp }));
    return () => {
      alive = false;
    };
  }, [stamp]);
  return state;
}
