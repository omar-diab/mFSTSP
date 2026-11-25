import type { Metadata } from "next";
import { AlgorithmCompare } from "@/components/Algorithm";

export const metadata: Metadata = { title: "Algorithm vs paper · mFSTSP" };

export default function Page() {
  return <AlgorithmCompare />;
}
