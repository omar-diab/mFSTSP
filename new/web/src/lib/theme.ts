"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { writeStored } from "./storage";
import { THEME_KEY as KEY } from "./theme-script";

export type Theme = "light" | "dark";

// The <head> script always sets data-theme, so the attribute is the source of truth.
function subscribe(cb: () => void) {
  const mo = new MutationObserver(cb);
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => mo.disconnect();
}

const current = (): Theme => (document.documentElement.dataset.theme === "dark" ? "dark" : "light");

export function useResolvedTheme(): Theme {
  return useSyncExternalStore(subscribe, current, () => "light");
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const theme = useResolvedTheme();
  const set = (t: Theme) => {
    document.documentElement.dataset.theme = t;
    writeStored("local", KEY, t);
  };
  return [theme, set];
}

const TOKENS = ["foreground", "panel", "panel-2", "line", "line-strong", "muted", "cyan", "orange", "violet", "mint", "rose", "grid", "axis", "scene-1", "scene-2", "scene-grid", "node", "depot", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"] as const;
export type Tokens = Record<(typeof TOKENS)[number], string> & { series: string[] };

const FALLBACK: Tokens = {
  foreground: "#1c2430", panel: "#ffffff", "panel-2": "#f2f4f7", line: "#e1e5eb", "line-strong": "#c9d0da", muted: "#5d6877",
  cyan: "#1f5fbf", orange: "#c4620f", violet: "#6b4fd1", mint: "#13805c", rose: "#c0284d", grid: "#e6e9ee", axis: "#6b7584",
  "scene-1": "#ffffff", "scene-2": "#eef1f5", "scene-grid": "rgba(31,95,191,0.09)", node: "#8a95a5", depot: "#1c2430",
  s1: "#1f5fbf", s2: "#d97706", s3: "#7c3aed", s4: "#059669", s5: "#db2777", s6: "#0891b2", s7: "#65a30d", s8: "#dc2626",
  series: ["#1f5fbf", "#d97706", "#7c3aed", "#059669", "#db2777", "#0891b2", "#65a30d", "#dc2626"],
};

function readTokens(): Tokens {
  const css = getComputedStyle(document.documentElement);
  const out = { ...FALLBACK } as Tokens;
  for (const t of TOKENS) out[t] = css.getPropertyValue(`--${t}`).trim() || FALLBACK[t];
  out.series = [out.s1, out.s2, out.s3, out.s4, out.s5, out.s6, out.s7, out.s8];
  return out;
}

// Resolved colour values for SVG attributes and canvas drawing.
export function useTokens(): Tokens {
  const theme = useResolvedTheme();
  const [tokens, setTokens] = useState<{ theme: string; t: Tokens }>({ theme: "", t: FALLBACK });
  useEffect(() => {
    // Read after the attribute change has applied the new variables.
    const id = requestAnimationFrame(() => setTokens({ theme, t: readTokens() }));
    return () => cancelAnimationFrame(id);
  }, [theme]);
  return tokens.t;
}
