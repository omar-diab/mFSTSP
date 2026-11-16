import type { Metadata } from "next";
import { PaperResults } from "@/components/Reproduction";

export const metadata: Metadata = { title: "Paper results · mFSTSP" };

export default function Page() {
  return <PaperResults />;
}
