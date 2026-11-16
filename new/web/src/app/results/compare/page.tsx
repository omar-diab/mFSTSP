import type { Metadata } from "next";
import { Compare } from "@/components/Reproduction";

export const metadata: Metadata = { title: "Compare · mFSTSP" };

export default function Page() {
  return <Compare />;
}
