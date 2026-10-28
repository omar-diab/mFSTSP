"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import type { Coord, Segment, Snapshot } from "@/lib/types";
import { at, position, project, timelines, type Position } from "@/lib/playback";
import { useTokens } from "@/lib/theme";

type Camera = { yaw: number; tilt: number; zoom: number; px: number; py: number };
const DEFAULT: Camera = { yaw: -0.5, tilt: 0.95, zoom: 1, px: 0, py: 0 };
// Arc height is illustrative, as a share of the scene radius.
const ARC = 0.16;

export type VehicleState = Position & { vehicle: string; onTruck: boolean; xy: [number, number] };

// Where each vehicle is at time t; UAVs between recorded activities ride the truck.
export function vehicleStates(snap: Snapshot, coords: Coord[], t: number): VehicleState[] {
  const xy = project(coords);
  const lines = timelines(snap);
  const truckLine = [...lines.entries()].find(([v]) => v.startsWith("Truck"))?.[1];
  const truck = truckLine ? at(xy, position(truckLine, t)) : xy.get(0)!;
  return [...lines.entries()].map(([vehicle, line]) => {
    const p = position(line, t);
    const onTruck = vehicle.startsWith("UAV") && !p.recorded && Boolean(truckLine);
    return {
      ...p,
      status: onTruck ? "Carried by truck (inferred between recorded activities)" : p.status,
      vehicle,
      onTruck,
      xy: onTruck ? truck : at(xy, p),
    };
  });
}

export default function Scene3D({
  coords,
  snap,
  time,
  colors,
  visible,
  selected,
  height = 560,
  showTrails = true,
}: {
  coords: Coord[];
  snap: Snapshot;
  time: number;
  colors: Record<string, string>;
  visible: Set<string>;
  selected?: string | null;
  height?: number;
  showTrails?: boolean;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const cam = useRef<Camera>({ ...DEFAULT });
  const frame = useRef(0);
  const tk = useTokens();

  const geo = useMemo(() => {
    const xy = project(coords);
    const extent = Math.max(1, ...[...xy.values()].map(([x, y]) => Math.hypot(x, y)));
    const norm = new Map([...xy.entries()].map(([k, [x, y]]) => [k, [x / extent, y / extent] as [number, number]]));
    return { xy, extent, norm };
  }, [coords]);

  const draw = useCallback(() => {
    const c = canvas.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth;
    const h = c.clientHeight;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
      c.width = Math.round(w * dpr);
      c.height = Math.round(h * dpr);
    }
    const ctx = c.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const { yaw, tilt, zoom, px, py } = cam.current;
    const scale = Math.min(w, h) * 0.42 * zoom;
    const cy0 = h * 0.52 + py;
    const cx0 = w / 2 + px;
    const cosY = Math.cos(yaw);
    const sinY = Math.sin(yaw);
    const cosT = Math.cos(tilt);
    const sinT = Math.sin(tilt);

    const P = (x: number, y: number, z = 0): [number, number, number] => {
      const rx = x * cosY - y * sinY;
      const ry = x * sinY + y * cosY;
      const sy = -(ry * cosT + z * sinT);
      const depth = ry * sinT - z * cosT;
      const p = 3.2 / (3.2 + depth);
      return [cx0 + rx * scale * p, cy0 + sy * scale * p, p];
    };
    const N = (id: number) => geo.norm.get(id) ?? geo.norm.get(0)!;

    // Backdrop
    ctx.clearRect(0, 0, w, h);
    const bg = ctx.createRadialGradient(w / 2, h * 0.35, 0, w / 2, h * 0.5, Math.max(w, h) * 0.8);
    bg.addColorStop(0, tk["scene-1"]);
    bg.addColorStop(1, tk["scene-2"]);
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);

    // Ground grid
    ctx.lineWidth = 1;
    for (let i = -6; i <= 6; i++) {
      const g = i / 5;
      ctx.strokeStyle = tk["scene-grid"];
      ctx.lineWidth = i === 0 ? 1.6 : 1;
      for (const [a, b] of [
        [P(g, -1.2), P(g, 1.2)],
        [P(-1.2, g), P(1.2, g)],
      ]) {
        ctx.beginPath();
        ctx.moveTo(a[0], a[1]);
        ctx.lineTo(b[0], b[1]);
        ctx.stroke();
      }
    }
    // North marker
    const [nx, ny] = P(0, 1.3);
    ctx.fillStyle = tk.axis;
    ctx.font = "600 11px var(--font-geist-sans), sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("N", nx, ny);

    const lines = timelines(snap);
    const dim = (v: string) => (selected && selected !== v ? 0.25 : 1);

    // Routes: full path faint, completed portion bright.
    const path = (s: Segment, upTo: number) => {
      const [v, start, end, a, b] = s;
      if (a === b) return;
      const A = N(a);
      const B = N(b);
      const uav = v.startsWith("UAV");
      const steps = uav ? 18 : 1;
      const frac = Math.max(0, Math.min(1, (upTo - start) / Math.max(end - start, 1e-9)));
      ctx.beginPath();
      for (let k = 0; k <= steps; k++) {
        const f = (k / steps) * frac;
        const [sx, sy] = P(A[0] + (B[0] - A[0]) * f, A[1] + (B[1] - A[1]) * f, uav ? ARC * Math.sin(Math.PI * f) : 0);
        if (k) ctx.lineTo(sx, sy);
        else ctx.moveTo(sx, sy);
      }
      ctx.stroke();
    };
    for (const [v, line] of lines) {
      if (!visible.has(v)) continue;
      const uav = v.startsWith("UAV");
      ctx.strokeStyle = colors[v];
      ctx.setLineDash(uav ? [5, 5] : []);
      ctx.globalAlpha = 0.18 * dim(v);
      ctx.lineWidth = selected === v ? 2.5 : 1.5;
      line.forEach((s) => path(s, Infinity));
      if (showTrails) {
        ctx.globalAlpha = 0.95 * dim(v);
        ctx.lineWidth = selected === v ? 3.5 : uav ? 2 : 3;
        line.forEach((s) => s[1] <= time && path(s, time));
      }
    }
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;

    // Nodes
    const delivered = new Set(snap.deliveries.filter(([, t]) => t <= time).map(([n]) => n));
    const many = coords.length > 40;
    for (const [id] of coords) {
      const [x, y] = N(id);
      const [sx, sy, p] = P(x, y);
      if (id === 0) {
        ctx.globalAlpha = 0.12;
        ctx.fillStyle = tk.depot;
        ctx.beginPath();
        ctx.arc(sx, sy, 18 * p, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.fillRect(sx - 6 * p, sy - 6 * p, 12 * p, 12 * p);
        ctx.fillStyle = tk.foreground;
        ctx.font = "700 11px var(--font-geist-sans), sans-serif";
        ctx.fillText("Depot", sx, sy - 14 * p);
        continue;
      }
      const done = delivered.has(id);
      const r = (many ? 3 : 4.5) * p;
      if (done) {
        ctx.globalAlpha = 0.2;
        ctx.fillStyle = tk.mint;
        ctx.beginPath();
        ctx.arc(sx, sy, r * 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;
      }
      ctx.fillStyle = done ? tk.mint : tk.node;
      ctx.beginPath();
      ctx.arc(sx, sy, r, 0, Math.PI * 2);
      ctx.fill();
      if (!many || cam.current.zoom > 1.8) {
        ctx.fillStyle = done ? tk.mint : tk.axis;
        ctx.font = "500 10px var(--font-geist-mono), monospace";
        ctx.fillText(String(id), sx, sy - r - 4);
      }
    }

    // Vehicles
    const states = vehicleStates(snap, coords, time);
    const extent = geo.extent;
    const onboard = states.filter((s) => s.onTruck && visible.has(s.vehicle));
    for (const s of states) {
      if (!visible.has(s.vehicle)) continue;
      const x = s.xy[0] / extent;
      const y = s.xy[1] / extent;
      const uav = s.vehicle.startsWith("UAV");
      const color = colors[s.vehicle];
      ctx.globalAlpha = dim(s.vehicle);
      if (uav && s.onTruck) {
        // Small pips stacked above the truck.
        const k = onboard.indexOf(s);
        const [sx, sy, p] = P(x, y, 0.035 + k * 0.022);
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(sx, sy, 3 * p, 0, Math.PI * 2);
        ctx.fill();
        continue;
      }
      const z = uav && s.a !== s.b ? ARC * Math.sin(Math.PI * s.f) : 0;
      const [gx, gy] = P(x, y, 0);
      const [sx, sy, p] = P(x, y, z);
      if (uav) {
        ctx.strokeStyle = tk["line-strong"];
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(gx, gy);
        ctx.lineTo(sx, sy);
        ctx.stroke();
        ctx.fillStyle = tk.foreground;
        ctx.globalAlpha = 0.18 * dim(s.vehicle);
        ctx.beginPath();
        ctx.ellipse(gx, gy, 7 * p, 3 * p, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = dim(s.vehicle);
      }
      ctx.fillStyle = color;
      ctx.strokeStyle = tk.panel;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      if (uav) {
        const r = (selected === s.vehicle ? 9 : 7) * p;
        ctx.moveTo(sx, sy - r);
        ctx.lineTo(sx + r, sy);
        ctx.lineTo(sx, sy + r);
        ctx.lineTo(sx - r, sy);
        ctx.closePath();
      } else {
        const r = (selected === s.vehicle ? 11 : 9) * p;
        ctx.roundRect(sx - r, sy - r * 0.7, r * 2, r * 1.4, 3);
      }
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = tk.foreground;
      ctx.font = "600 10px var(--font-geist-sans), sans-serif";
      ctx.fillText(s.vehicle, sx, sy - 14 * p);
    }
    ctx.globalAlpha = 1;
  }, [coords, snap, time, colors, visible, selected, geo, showTrails, tk]);

  const schedule = useCallback(() => {
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(draw);
  }, [draw]);

  useEffect(() => {
    schedule();
  }, [schedule]);

  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const ro = new ResizeObserver(schedule);
    ro.observe(c);
    let drag: { x: number; y: number; pan: boolean } | null = null;
    const down = (e: PointerEvent) => {
      drag = { x: e.clientX, y: e.clientY, pan: e.button === 2 || e.shiftKey };
      c.setPointerCapture(e.pointerId);
    };
    const move = (e: PointerEvent) => {
      if (!drag) return;
      const dx = e.clientX - drag.x;
      const dy = e.clientY - drag.y;
      drag.x = e.clientX;
      drag.y = e.clientY;
      if (drag.pan) {
        cam.current.px += dx;
        cam.current.py += dy;
      } else {
        cam.current.yaw += dx * 0.008;
        cam.current.tilt = Math.max(0, Math.min(1.35, cam.current.tilt + dy * 0.006));
      }
      schedule();
    };
    const up = () => (drag = null);
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      cam.current.zoom = Math.max(0.4, Math.min(6, cam.current.zoom * Math.exp(-e.deltaY * 0.0015)));
      schedule();
    };
    const reset = () => {
      cam.current = { ...DEFAULT };
      schedule();
    };
    const menu = (e: Event) => e.preventDefault();
    c.addEventListener("pointerdown", down);
    c.addEventListener("pointermove", move);
    c.addEventListener("pointerup", up);
    c.addEventListener("pointercancel", up);
    c.addEventListener("wheel", wheel, { passive: false });
    c.addEventListener("dblclick", reset);
    c.addEventListener("contextmenu", menu);
    return () => {
      ro.disconnect();
      c.removeEventListener("pointerdown", down);
      c.removeEventListener("pointermove", move);
      c.removeEventListener("pointerup", up);
      c.removeEventListener("pointercancel", up);
      c.removeEventListener("wheel", wheel);
      c.removeEventListener("dblclick", reset);
      c.removeEventListener("contextmenu", menu);
    };
  }, [schedule]);

  const view = (v: Partial<Camera>) => {
    cam.current = { ...cam.current, ...v };
    schedule();
  };

  return (
    <div className="relative overflow-hidden rounded-xl border border-line">
      <canvas ref={canvas} className="block w-full cursor-grab touch-none active:cursor-grabbing" style={{ height }} aria-label="3D route scene. Drag to rotate, scroll to zoom, shift-drag to pan, double-click to reset." role="img" />
      <div className="absolute top-3 right-3 flex gap-1.5">
        {(
          [
            ["Top", { tilt: 0, yaw: 0 }],
            ["Oblique", { tilt: 0.95, yaw: -0.5 }],
            ["Low", { tilt: 1.3 }],
            ["Reset", { ...DEFAULT }],
          ] as const
        ).map(([label, v]) => (
          <button key={label} onClick={() => view(v)} className="rounded-md border border-line bg-panel/90 px-2.5 py-1 text-xs text-muted shadow-sm hover:border-cyan/40 hover:text-cyan">
            {label}
          </button>
        ))}
      </div>
      <div className="pointer-events-none absolute bottom-3 left-3 rounded-md bg-panel/85 px-2.5 py-1 text-[0.68rem] text-muted">Drag rotate · scroll zoom · shift-drag pan · double-click reset</div>
    </div>
  );
}
