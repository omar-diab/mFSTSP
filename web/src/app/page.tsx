"use client";

import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

export default function Home() {
  const container = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      gsap.from(".hello", { y: 40, opacity: 0, duration: 1, ease: "power3.out" });
    },
    { scope: container },
  );

  return (
    <div ref={container} className="flex flex-1 items-center justify-center">
      <h1 className="hello text-5xl font-bold tracking-tight">Hello World</h1>
    </div>
  );
}
