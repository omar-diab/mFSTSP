import type { Coord, Segment, Snapshot } from "./types";

export type XY = Map<number, [number, number]>;

// Local east/north metres around the depot.
export function project(coords: Coord[]): XY {
  const depot = coords.find((c) => c[0] === 0) ?? coords[0];
  const [, lon0, lat0] = depot;
  const k = 111320;
  const xy: XY = new Map(coords.map(([id, lon, lat]) => [id, [(lon - lon0) * k * Math.cos((lat0 * Math.PI) / 180), (lat - lat0) * k]]));
  // The original formulations use c+1 as a separate return-depot ID.
  const maxId = Math.max(...coords.map((c) => c[0]));
  if (!xy.has(maxId + 1)) xy.set(maxId + 1, xy.get(0) ?? [0, 0]);
  return xy;
}

export const vehiclesOf = (snap: Snapshot) =>
  [...new Set(snap.segments.map((s) => s[0]))].sort((a, b) => (a.startsWith("Truck") === b.startsWith("Truck") ? a.localeCompare(b, undefined, { numeric: true }) : a.startsWith("Truck") ? -1 : 1));

export function timelines(snap: Snapshot) {
  const out = new Map<string, Segment[]>();
  for (const s of snap.segments) {
    if (!out.has(s[0])) out.set(s[0], []);
    out.get(s[0])!.push(s);
  }
  for (const list of out.values()) list.sort((a, b) => a[1] - b[1]);
  return out;
}

export type Position = { a: number; b: number; f: number; status: string; recorded: boolean };

export function position(timeline: Segment[], t: number): Position {
  let previous = timeline.length ? timeline[0][3] : 0;
  for (const s of timeline) {
    if (t < s[1]) return { a: previous, b: previous, f: 0, status: "Between recorded activities", recorded: false };
    if (t <= s[2]) return { a: s[3], b: s[4], f: (t - s[1]) / Math.max(s[2] - s[1], 1e-9), status: s[5], recorded: true };
    previous = s[4];
  }
  return { a: previous, b: previous, f: 0, status: "Recorded activities complete", recorded: false };
}

export function at(xy: XY, p: Position): [number, number] {
  const a = xy.get(p.a) ?? xy.get(0)!;
  const b = xy.get(p.b) ?? xy.get(0)!;
  return [a[0] + (b[0] - a[0]) * p.f, a[1] + (b[1] - a[1]) * p.f];
}

// Straight-line geometry only; not road-network distance.
export function distances(snap: Snapshot, xy: XY) {
  const out: Record<string, number> = {};
  for (const [v, , , a, b] of snap.segments) {
    const p = xy.get(a);
    const q = xy.get(b);
    if (p && q) out[v] = (out[v] ?? 0) + Math.hypot(p[0] - q[0], p[1] - q[1]);
  }
  return out;
}

// The truck takes the second series colour (orange) so it stands apart from the drones.
export function vehicleColors(vehicles: string[], palette: string[]) {
  const order = [palette[1], palette[0], ...palette.slice(2)];
  return Object.fromEntries(vehicles.map((v, i) => [v, order[i % order.length]]));
}
