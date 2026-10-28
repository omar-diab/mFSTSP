import type { Metadata } from "next";
import AlgorithmsExplorer from "@/components/AlgorithmsExplorer";

export const metadata: Metadata = { title: "Algorithms explained · mFSTSP" };

export default function AlgorithmsPage() {
  return <AlgorithmsExplorer />;
}
