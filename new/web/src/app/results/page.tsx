import type { Metadata } from "next";
import ResultsExplorer from "@/components/ResultsExplorer";

export const metadata: Metadata = { title: "Our experimental results · mFSTSP" };

export default function ResultsPage() {
  return <ResultsExplorer mode="ours" />;
}
