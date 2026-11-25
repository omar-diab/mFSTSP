import type { Metadata } from "next";
import { AlgorithmResults } from "@/components/Algorithm";

export const metadata: Metadata = { title: "Our algorithm results · mFSTSP" };

export default function Page() {
  return <AlgorithmResults />;
}
