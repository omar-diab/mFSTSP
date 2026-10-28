import type { Metadata } from "next";
import Comparison from "@/components/Comparison";

export const metadata: Metadata = { title: "Comparison dashboard · mFSTSP" };

export default function ComparisonPage() {
  return <Comparison />;
}
