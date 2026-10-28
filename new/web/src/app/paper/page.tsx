import type { Metadata } from "next";
import ResultsExplorer from "@/components/ResultsExplorer";

export const metadata: Metadata = { title: "Original paper results · mFSTSP" };

export default function PaperPage() {
  return <ResultsExplorer mode="paper" />;
}
