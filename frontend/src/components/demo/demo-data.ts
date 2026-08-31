/**
 * The sample engagement behind the public `/demo` playground.
 *
 * `/demo` has no session and may be visited while the app is pointed at a live
 * backend, so it must never go through `lib/api.ts`: every call there would
 * either 401 or hit a case this visitor has no right to see. It reads the
 * fixture JSON directly instead. Those fixtures are copies of
 * `sample-data/fixtures/`, which the backend validates against the real
 * Pydantic schemas — so the shapes on screen are the product's real shapes,
 * not a marketing mock-up.
 */

import dashboardFixture from "@/lib/fixtures/dashboard.json";
import reviewItemsFixture from "@/lib/fixtures/review-items.json";
import type { DashboardSummary, ReviewItem } from "@/lib/types";

/** The seeded engagement: client "Haroon Textiles", June 2026. */
export const DEMO_CASE_ID: string = reviewItemsFixture.case_id;

/**
 * A fresh deep copy per call. The imported JSON module is one shared object for
 * the life of the tab; the playground lets a visitor approve and reject rows,
 * so handing out the module itself would let one visit's clicks leak into the
 * next mount (and into fixture mode elsewhere in the app).
 */
export function demoReviewItems(): ReviewItem[] {
  return JSON.parse(JSON.stringify(reviewItemsFixture.items)) as ReviewItem[];
}

/**
 * The dashboard the backend computed for the same case. Read-only here: the
 * demo dashboard recounts nothing except the decision tally, which is display
 * bookkeeping over the visitor's own clicks, never audit math.
 */
export const demoDashboard = dashboardFixture as unknown as DashboardSummary;
