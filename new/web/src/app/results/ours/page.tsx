import type { Metadata } from "next";
import { OurResults } from "@/components/Reproduction";

export const metadata: Metadata = { title: "Our results · mFSTSP" };

export default function Page() {
  return <OurResults />;
}
