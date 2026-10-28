"use client";

import { useRef, useState } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

// Scene is authored in a 1080x1920 (9:16) coordinate space.
const HORIZON = 1160;
const TRUCK_X = 540;
const TRUCK_Y = 1700;
// Drones rest just below the roof line, hidden behind the cargo box.
const DRONE_HOME_Y = 1265;
const DRONE_LANES = [450, 540, 630];
const DRONE_HOVER_Y = [1030, 975, 1030];
// Delivery exits, far enough out to clear the edges of a wide screen.
const DRONE_EXIT = [
  [-1900, 350],
  [540, -900],
  [3000, 350],
];
const CAMERA_ORIGIN = "540 900";

// Deterministic noise so server and client render the same markup.
function rand(i: number) {
  const x = Math.sin(i * 127.1 + 311.7) * 43758.5453;
  // Rounded because Math.sin differs in the last bits between Node and browsers.
  return Math.round((x - Math.floor(x)) * 1000) / 1000;
}

// The tower's lit face has a slanted roof from (360,330) to (600,250).
const facadeTop = (x: number) => 330 - ((x - 360) / 240) * 80;

const WINDOWS = (() => {
  const out: { x: number; y: number; o: number }[] = [];
  let i = 0;
  for (let y = 300; y < 1140; y += 26) {
    for (let c = 0; c < 8; c++) {
      const x = 368 + c * 28;
      if (y > facadeTop(x + 20) + 12) out.push({ x, y, o: 0.08 + rand(i) * 0.4 });
      i++;
    }
  }
  return out;
})();

const SKYLINE = [
  { x: 0, w: 110, h: 360 },
  { x: 95, w: 140, h: 520 },
  { x: 225, w: 90, h: 300 },
  { x: 300, w: 80, h: 430 },
  { x: 720, w: 100, h: 470 },
  { x: 810, w: 130, h: 340 },
  { x: 930, w: 80, h: 560 },
  { x: 1000, w: 80, h: 400 },
  // Extra blocks beyond the 9:16 frame so wide screens stay filled.
  ...Array.from({ length: 34 }, (_, i) => {
    const side = i % 2 ? 1 : -1;
    const step = Math.floor(i / 2);
    return {
      x: side < 0 ? -110 - step * 105 : 1080 + step * 105,
      w: 80 + rand(i + 200) * 60,
      h: 260 + rand(i + 300) * 320,
    };
  }),
];

type Props = {
  onFinish?: () => void;
};

export default function SplashScreen({ onFinish }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const tl = useRef<gsap.core.Timeline | null>(null);
  const [done, setDone] = useState(false);

  useGSAP(
    () => {
      const el = root.current!;
      const finish = () => {
        gsap.to(el, {
          opacity: 0,
          duration: 0.6,
          ease: "power2.out",
          onComplete: () => {
            setDone(true);
            onFinish?.();
          },
        });
      };

      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        finish();
        return;
      }

      const camera = el.querySelector(".camera")!;
      const truck = el.querySelector(".truck")!;
      const droneEls = gsap.utils.toArray<SVGGElement>(".drone", el);
      const trailEls = gsap.utils.toArray<SVGPolylineElement>(".trail", el);
      const canvas = el.querySelector<HTMLCanvasElement>(".grain")!;

      // Drones are driven through plain objects; the ticker writes their
      // transforms so banking and trails can follow actual velocity.
      const drones = DRONE_LANES.map((x) => ({
        x,
        y: DRONE_HOME_Y,
        s: 1,
        r: 0,
        px: x,
        hist: [] as number[],
      }));

      const ctx = canvas.getContext("2d")!;
      const grain = ctx.createImageData(canvas.width, canvas.height);
      const pixels = new Uint32Array(grain.data.buffer);
      let frame = 0;

      const render = () => {
        drones.forEach((d, i) => {
          const bank = gsap.utils.clamp(-18, 18, (d.x - d.px) * 2.4);
          d.r += (bank - d.r) * 0.2;
          d.px = d.x;
          droneEls[i].setAttribute(
            "transform",
            `translate(${d.x} ${d.y}) rotate(${d.r}) scale(${d.s})`,
          );
          d.hist.unshift(d.x, d.y);
          d.hist.length = Math.min(d.hist.length, 32);
          trailEls[i].setAttribute("points", d.hist.join(" "));
          trailEls[i].setAttribute("stroke-width", String(5 * d.s));
        });

        if (frame++ % 2 === 0) {
          for (let p = 0; p < pixels.length; p++) {
            const v = (Math.random() * 255) | 0;
            pixels[p] = (40 << 24) | (v << 16) | (v << 8) | v;
          }
          ctx.putImageData(grain, 0, 0);
        }
      };
      gsap.ticker.add(render);

      // Ambient loops that run underneath every shot.
      gsap.to(".fog", {
        x: (i) => (i % 2 ? -70 : 70),
        duration: 4,
        ease: "sine.inOut",
        yoyo: true,
        repeat: -1,
      });
      gsap.to(".ray", {
        opacity: (i) => 0.25 + (i % 3) * 0.15,
        duration: 1.6,
        ease: "sine.inOut",
        yoyo: true,
        repeat: -1,
        stagger: 0.3,
      });
      gsap.to(".rotor", {
        scaleX: 0.12,
        transformOrigin: "50% 50%",
        duration: 0.035,
        ease: "none",
        yoyo: true,
        repeat: -1,
      });
      gsap.to(".blink", { opacity: 0.1, duration: 0.5, yoyo: true, repeat: -1 });

      gsap.set(camera, { svgOrigin: CAMERA_ORIGIN, scale: 1.12 });
      gsap.set(truck, { svgOrigin: "0 0", x: TRUCK_X, y: 2380, scale: 0.85 });

      const t = gsap.timeline({ onComplete: finish });
      tl.current = t;

      // Shot 1 (0–1.5s): truck rises out of the fog toward a low camera.
      t.to(camera, { scale: 1, duration: 1.5, ease: "power2.out" }, 0)
        .to(truck, { y: TRUCK_Y, scale: 1, duration: 1.4, ease: "power3.out" }, 0)
        .fromTo(
          ".headlight",
          { opacity: 0 },
          { opacity: 1, duration: 0.25, ease: "steps(4)" },
          0.1,
        )
        .fromTo(
          ".flare",
          { scaleX: 0.2, opacity: 0, transformOrigin: "50% 50%" },
          { scaleX: 1, opacity: 1, duration: 0.6, ease: "power2.out" },
          0.25,
        )
        .to(".road-dash", { strokeDashoffset: -540, duration: 1.4, ease: "power3.out" }, 0)
        .fromTo(
          ".dust",
          { x: (i) => (i % 2 ? 215 : -215), y: -10, scale: 0.4, opacity: 0.55 },
          {
            x: (i) => (i % 2 ? 1 : -1) * (260 + rand(i) * 260),
            y: (i) => -30 - rand(i + 50) * 160,
            scale: (i) => 1.5 + rand(i + 9) * 2,
            opacity: 0,
            duration: 0.9,
            ease: "power2.out",
            stagger: 0.05,
          },
          0.05,
        );

      // Shot 2 (1.5–2.5s): truck settles, hatch opens, drones launch.
      t.to(truck, { y: TRUCK_Y + 8, duration: 0.12, yoyo: true, repeat: 1, ease: "sine.inOut" }, 1.4)
        .to(".flare", { opacity: 0.55, duration: 0.4 }, 1.5)
        .to(".hatch-left", { rotation: -80, svgOrigin: "-200 -470", duration: 0.4, ease: "power2.inOut" }, 1.5)
        .to(".hatch-right", { rotation: 80, svgOrigin: "200 -470", duration: 0.4, ease: "power2.inOut" }, 1.5)
        .to(".led", { opacity: 1, duration: 0.2, ease: "steps(3)" }, 1.6);
      // Drones stay stowed inside the truck until the hatch is open.
      t.set([".drone", ".trail"], { opacity: 1 }, 1.6);
      drones.forEach((d, i) => {
        t.to(d, { y: DRONE_HOVER_Y[i], duration: 0.9, ease: "sine.inOut" }, 1.8 + i * 0.3);
      });

      // Shot 3 (3.4–5.5s): drones fly out of frame to deliver their parcels.
      t.to(camera, { scale: 1.15, y: 60, duration: 2, ease: "sine.inOut" }, 3.4);
      drones.forEach((d, i) => {
        const [x, y] = DRONE_EXIT[i];
        t.to(d, { x, y, s: 0.5, duration: 1.8, ease: "sine.in" }, 3.4 + i * 0.15);
      });
      // Parcels are dropped off while the drones are out of sight.
      t.set(".parcel", { opacity: 0 }, 5.7);

      // Shot 4 (5.9–9.8s): drones fly back empty and land; hatch seals.
      t.to(camera, { scale: 1, y: 0, duration: 2, ease: "sine.inOut" }, 5.9);
      drones.forEach((d, i) => {
        t.to(d, { x: DRONE_LANES[i], y: 1080, s: 1, duration: 1.8, ease: "sine.out" }, 5.9 + i * 0.15)
          .to(d, { y: DRONE_HOME_Y, duration: 0.8, ease: "sine.inOut" }, 8.1 + i * 0.25);
      });
      t.to(".hatch-left", { rotation: 0, duration: 0.3, ease: "power2.in" }, 9.4)
        .to(".hatch-right", { rotation: 0, duration: 0.3, ease: "power2.in" }, 9.4)
        .to(".led", { opacity: 0, duration: 0.15 }, 9.7);

      // Shot 5 (9.8–11s): truck drives into the lens until its cab fills
      // the screen, then the headlights flash out into the home page.
      t.to(truck, { y: 2360, scale: 7, duration: 1.1, ease: "power3.in" }, 9.8)
        .to(".road-dash", { strokeDashoffset: -1400, duration: 1.1, ease: "power3.in" }, 9.8)
        .to(".flash", { opacity: 1, duration: 0.2, ease: "power2.in" }, 10.75)
        .set({}, {}, 11);

      return () => gsap.ticker.remove(render);
    },
    { scope: root },
  );

  if (done) return null;

  return (
    <div
      ref={root}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black"
      onClick={() => tl.current?.progress(1)}
    >
      <div className="relative h-full w-full overflow-hidden">
        {/* "meet" keeps the whole 9:16 action visible; the scenery extends past the viewBox to fill any screen. */}
        <svg
          viewBox="0 0 1080 1920"
          preserveAspectRatio="xMidYMid meet"
          className="absolute inset-0 h-full w-full"
          aria-hidden="true"
        >
          <defs>
            <linearGradient id="sp-sky" x1="0" y1="-1500" x2="0" y2={HORIZON} gradientUnits="userSpaceOnUse">
              <stop offset="0" stopColor="#02050d" />
              <stop offset="0.5" stopColor="#06122a" />
              <stop offset="0.74" stopColor="#11264a" />
              <stop offset="0.88" stopColor="#373a57" />
              <stop offset="0.96" stopColor="#b2532a" />
              <stop offset="1" stopColor="#f08a3c" />
            </linearGradient>
            <radialGradient id="sp-horizon">
              <stop offset="0" stopColor="#ff8a3d" stopOpacity="0.6" />
              <stop offset="1" stopColor="#ff8a3d" stopOpacity="0" />
            </radialGradient>
            <linearGradient id="sp-ray" x1="0" y1="1" x2="0" y2="0">
              <stop offset="0" stopColor="#ffb070" stopOpacity="0.35" />
              <stop offset="1" stopColor="#ffb070" stopOpacity="0" />
            </linearGradient>
            <linearGradient id="sp-ground" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#101a2c" />
              <stop offset="1" stopColor="#03050a" />
            </linearGradient>
            <linearGradient id="sp-glass-l" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#1b3253" />
              <stop offset="0.6" stopColor="#264467" />
              <stop offset="0.88" stopColor="#7d5248" />
              <stop offset="1" stopColor="#d9743c" />
            </linearGradient>
            <linearGradient id="sp-glass-r" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#0a1426" />
              <stop offset="1" stopColor="#1a2236" />
            </linearGradient>
            <linearGradient id="sp-reflect" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#fff" stopOpacity="0" />
              <stop offset="0.5" stopColor="#fff" stopOpacity="0.16" />
              <stop offset="1" stopColor="#fff" stopOpacity="0" />
            </linearGradient>
            <radialGradient id="sp-fog">
              <stop offset="0" stopColor="#7d93b5" stopOpacity="0.45" />
              <stop offset="1" stopColor="#7d93b5" stopOpacity="0" />
            </radialGradient>
            <linearGradient id="sp-box" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#2c3440" />
              <stop offset="1" stopColor="#11151c" />
            </linearGradient>
            <linearGradient id="sp-cab" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#343d4b" />
              <stop offset="1" stopColor="#12161d" />
            </linearGradient>
            <linearGradient id="sp-windshield" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#f2a25c" stopOpacity="0.85" />
              <stop offset="0.45" stopColor="#3a4a66" />
              <stop offset="1" stopColor="#0c1424" />
            </linearGradient>
            <radialGradient id="sp-headglow">
              <stop offset="0" stopColor="#fffdf2" />
              <stop offset="0.25" stopColor="#ffe2b0" stopOpacity="0.6" />
              <stop offset="1" stopColor="#ffd08a" stopOpacity="0" />
            </radialGradient>
            <linearGradient id="sp-beam" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#fff3d6" stopOpacity="0.28" />
              <stop offset="1" stopColor="#fff3d6" stopOpacity="0" />
            </linearGradient>
            <linearGradient id="sp-streak" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="#9fd8ff" stopOpacity="0" />
              <stop offset="0.5" stopColor="#e6f6ff" stopOpacity="0.95" />
              <stop offset="1" stopColor="#9fd8ff" stopOpacity="0" />
            </linearGradient>
            <radialGradient id="sp-led">
              <stop offset="0" stopColor="#5ff3ff" stopOpacity="0.9" />
              <stop offset="1" stopColor="#5ff3ff" stopOpacity="0" />
            </radialGradient>
            <radialGradient id="sp-dust">
              <stop offset="0" stopColor="#a8957f" stopOpacity="0.6" />
              <stop offset="1" stopColor="#a8957f" stopOpacity="0" />
            </radialGradient>
            <clipPath id="sp-facade">
              <polygon points="360,330 600,250 600,1160 360,1160" />
            </clipPath>
          </defs>

          <g className="camera">
            {/* Sky, sunset glow and light shafts */}
            <rect x="-2600" y="-2000" width="6280" height={HORIZON + 2000} fill="url(#sp-sky)" />
            <ellipse cx="540" cy={HORIZON} rx="2200" ry="340" fill="url(#sp-horizon)" />
            {[
              "540,1160 120,-300 330,-300",
              "540,1160 420,-300 560,-300",
              "540,1160 700,-300 900,-300",
              "540,1160 980,-100 1200,0",
            ].map((points) => (
              <polygon key={points} className="ray" points={points} fill="url(#sp-ray)" opacity="0.3" />
            ))}

            {/* Distant skyline */}
            {SKYLINE.map((b, i) => (
              <g key={i}>
                <rect x={b.x} y={HORIZON - b.h} width={b.w} height={b.h} fill="#0a1222" />
                {[0, 1, 2].map((k) => (
                  <rect
                    key={k}
                    x={b.x + 14 + k * 26}
                    y={HORIZON - b.h + 40 + rand(i * 7 + k) * (b.h - 80)}
                    width="8"
                    height="10"
                    fill="#ffb878"
                    opacity={0.25 + rand(i + k) * 0.4}
                  />
                ))}
              </g>
            ))}

            {/* Glass tower */}
            <line x1="600" y1="250" x2="600" y2="170" stroke="#1a2438" strokeWidth="6" />
            <circle className="blink" cx="600" cy="168" r="7" fill="#ff4040" />
            <polygon points="360,330 600,250 600,1160 360,1160" fill="url(#sp-glass-l)" />
            <polygon points="600,250 720,300 720,1160 600,1160" fill="url(#sp-glass-r)" />
            {[630, 660, 690].map((x) => (
              <line key={x} x1={x} y1="290" x2={x} y2="1160" stroke="#24304a" strokeWidth="2" />
            ))}
            <line x1="600" y1="250" x2="600" y2="1160" stroke="#ff9a52" strokeWidth="2" opacity="0.7" />
            <g clipPath="url(#sp-facade)">
              {WINDOWS.map((w, i) => (
                <rect key={i} x={w.x} y={w.y} width="20" height="16" fill="#ffd9a8" opacity={w.o} />
              ))}
              <polygon points="360,700 600,380 600,520 360,840" fill="url(#sp-reflect)" />
            </g>

            {/* Ground, road and fog */}
            <rect x="-2600" y={HORIZON} width="6280" height="2000" fill="url(#sp-ground)" />
            <polygon points="505,1160 575,1160 1040,2400 40,2400" fill="#0b0f17" />
            <line
              className="road-dash"
              x1="540"
              y1="1160"
              x2="540"
              y2="2400"
              stroke="#c9b48c"
              strokeWidth="10"
              strokeDasharray="50 70"
              opacity="0.35"
            />
            <ellipse className="fog" cx="300" cy="1190" rx="520" ry="110" fill="url(#sp-fog)" />
            <ellipse className="fog" cx="820" cy="1230" rx="560" ry="120" fill="url(#sp-fog)" />
            <ellipse className="fog" cx="-700" cy="1210" rx="900" ry="130" fill="url(#sp-fog)" />
            <ellipse className="fog" cx="1800" cy="1220" rx="900" ry="130" fill="url(#sp-fog)" />

            {/* Drone trails and drones sit behind the truck so they can hide in the hatch */}
            {DRONE_LANES.map((x) => (
              <polyline
                key={x}
                className="trail"
                opacity="0"
                fill="none"
                stroke="#5ff3ff"
                strokeOpacity="0.35"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            ))}
            {DRONE_LANES.map((x) => (
              <g key={x} className="drone" opacity="0" transform={`translate(${x} ${DRONE_HOME_Y})`}>
                <g className="parcel">
                  <line x1="0" y1="10" x2="0" y2="28" stroke="#3f4a5e" strokeWidth="2" />
                  <rect x="-20" y="28" width="40" height="30" rx="3" fill="#b5793f" />
                  <rect x="-3" y="28" width="6" height="30" fill="#e2c08d" opacity="0.8" />
                </g>
                <ellipse cx="0" cy="24" rx="70" ry="22" fill="url(#sp-led)" opacity="0.5" />
                <rect x="-58" y="-3" width="116" height="6" rx="3" fill="#1e2430" />
                <line x1="-14" y1="8" x2="-24" y2="24" stroke="#1e2430" strokeWidth="4" />
                <line x1="14" y1="8" x2="24" y2="24" stroke="#1e2430" strokeWidth="4" />
                <ellipse cx="0" cy="0" rx="24" ry="12" fill="#252c39" stroke="#3f4a5e" strokeWidth="2" />
                <circle cx="0" cy="10" r="5" fill="#0b0f16" stroke="#5ff3ff" strokeWidth="1.5" />
                {[-58, 58].map((mx) => (
                  <g key={mx}>
                    <rect x={mx - 6} y="-10" width="12" height="10" rx="3" fill="#2f3747" />
                    <ellipse className="rotor" cx={mx} cy="-12" rx="34" ry="4" fill="#dfe8f5" opacity="0.45" />
                    <circle className="blink" cx={mx} cy="4" r="3.5" fill={mx < 0 ? "#5ff3ff" : "#ff4d4d"} />
                  </g>
                ))}
              </g>
            ))}

            {/* Truck, authored with its ground contact at (0,0) */}
            <g className="truck">
              <polygon className="headlight" points="-230,-150 -140,-150 240,700 -820,700" fill="url(#sp-beam)" />
              <polygon className="headlight" points="140,-150 230,-150 820,700 -240,700" fill="url(#sp-beam)" />
              <ellipse cx="0" cy="0" rx="340" ry="32" fill="#000" opacity="0.65" />
              {Array.from({ length: 16 }, (_, i) => (
                <circle key={i} className="dust" cx="0" cy="0" r="22" fill="url(#sp-dust)" opacity="0" />
              ))}
              <rect x="-250" y="-92" width="82" height="92" rx="14" fill="#090b0f" />
              <rect x="168" y="-92" width="82" height="92" rx="14" fill="#090b0f" />

              <ellipse className="led" cx="0" cy="-500" rx="230" ry="70" fill="url(#sp-led)" opacity="0" />
              <rect x="-270" y="-470" width="540" height="300" rx="10" fill="url(#sp-box)" />
              <rect x="-270" y="-470" width="540" height="4" fill="#ff9a4d" opacity="0.8" />
              <rect x="-210" y="-478" width="420" height="10" fill="#0d1016" />
              <rect className="led" x="-200" y="-476" width="400" height="4" fill="#5ff3ff" opacity="0" />
              <rect className="hatch-left" x="-200" y="-484" width="200" height="14" rx="2" fill="#3a4352" />
              <rect className="hatch-right" x="0" y="-484" width="200" height="14" rx="2" fill="#3a4352" />
              <circle cx="-255" cy="-455" r="5" fill="#ffae42" />
              <circle cx="255" cy="-455" r="5" fill="#ffae42" />

              <rect x="-255" y="-300" width="510" height="230" rx="18" fill="url(#sp-cab)" />
              <path d="M-215 -285 L215 -285 L200 -190 L-200 -190 Z" fill="url(#sp-windshield)" />
              <rect x="-292" y="-268" width="28" height="56" rx="6" fill="#1c222c" />
              <rect x="264" y="-268" width="28" height="56" rx="6" fill="#1c222c" />
              <rect x="-120" y="-172" width="240" height="62" rx="6" fill="#0b0d12" />
              {[-160, -146, -132, -118].map((y) => (
                <line key={y} x1="-110" y1={y} x2="110" y2={y} stroke="#2a313d" strokeWidth="3" />
              ))}
              <rect x="-232" y="-168" width="92" height="34" rx="10" fill="#fff6e0" />
              <rect x="140" y="-168" width="92" height="34" rx="10" fill="#fff6e0" />
              <rect x="-265" y="-102" width="530" height="36" rx="8" fill="#161a21" />

              <circle className="headlight" cx="-186" cy="-151" r="95" fill="url(#sp-headglow)" />
              <circle className="headlight" cx="186" cy="-151" r="95" fill="url(#sp-headglow)" />
              <g className="flare">
                <ellipse cx="0" cy="-151" rx="620" ry="5" fill="url(#sp-streak)" />
                <circle cx="-60" cy="-260" r="16" fill="#9fd8ff" opacity="0.12" />
                <circle cx="80" cy="-420" r="30" fill="#ffb878" opacity="0.08" />
              </g>
            </g>
          </g>
        </svg>

        {/* Lens finishing: vignette, grain and the closing flash */}
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_45%,rgba(0,0,0,0.75)_100%)]" />
        <canvas
          className="grain pointer-events-none absolute inset-0 h-full w-full opacity-40 mix-blend-overlay"
          width={216}
          height={384}
        />
        <div className="flash pointer-events-none absolute inset-0 bg-white opacity-0" />
      </div>
    </div>
  );
}
