/**
 * `/demo` — the public playground. Deliberately outside the `(app)` route
 * group: it has no sidebar, no active-case selection and no session, because
 * the whole point is that a visitor can see the product work before they have
 * any of those. It renders from the sample fixtures and never calls the API.
 *
 * This file stays a server component so the page keeps its own metadata; all
 * the interactive work lives in `<DemoPlayground />`.
 */

import type { Metadata } from "next";
import { DemoPlayground } from "@/components/demo/demo-playground";

export const metadata: Metadata = {
  title: "Live demo — Tarazu",
  description:
    "Work a sample audit engagement in your browser: the review queue, the evidence behind every row, and an honest account of which half of it an AI produced. No signup.",
};

export default function DemoPage() {
  return <DemoPlayground />;
}
