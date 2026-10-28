import { Suspense } from "react";
import type { Metadata } from "next";
import Studio from "@/components/Studio";

export const metadata: Metadata = { title: "3D delivery studio · mFSTSP" };

export default function StudioPage() {
  // Studio reads ?instance=&file= links from the results pages.
  return (
    <Suspense>
      <Studio />
    </Suspense>
  );
}
