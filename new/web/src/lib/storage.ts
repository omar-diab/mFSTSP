"use client";

import { useSyncExternalStore } from "react";

type Kind = "local" | "session";

// In-memory fallback for when browser storage is blocked.
const memory = new Map<string, string>();
const EVENT = "mfstsp-storage";

function area(kind: Kind) {
  try {
    return kind === "local" ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

function read(kind: Kind, key: string) {
  try {
    return area(kind)?.getItem(key) ?? memory.get(`${kind}:${key}`) ?? null;
  } catch {
    return memory.get(`${kind}:${key}`) ?? null;
  }
}

export function writeStored(kind: Kind, key: string, value: string) {
  memory.set(`${kind}:${key}`, value);
  try {
    area(kind)?.setItem(key, value);
  } catch {}
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

// Returns undefined during server rendering and hydration, then the stored value (or null).
export function useStored(kind: Kind, key: string): string | null | undefined {
  return useSyncExternalStore(
    subscribe,
    () => read(kind, key),
    () => undefined,
  );
}
