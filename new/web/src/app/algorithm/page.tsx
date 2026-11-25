import type { Metadata } from "next";
import { AlgorithmOverview } from "@/components/Algorithm";

export const metadata: Metadata = { title: "Our algorithm · mFSTSP" };

export default function Page() {
  return <AlgorithmOverview />;
}
