"use client";

/**
 * The public `/demo` playground: the product, working, with no signup and no
 * backend.
 *
 * Three deliberate choices are worth stating, because each is easy to undo by
 * accident later.
 *
 * 1. It reads fixtures, never `lib/api.ts`. `/demo` is a public route that has
 *    to render on a deployment pointed at a live backend, where every API call
 *    from an anonymous visitor is a 401. See `demo-data.ts`.
 * 2. It is a guided walkthrough, not a sandbox. The tabs run in the order an
 *    engagement does — the queue you work, the numbers it rolls up to, and
 *    then the honest account of which half of that a model produced.
 * 3. All the mutable state lives here. The dashboard's next-best actions jump
 *    into the queue and open a specific row, which only works if one component
 *    owns the items, the filter and the open row.
 *
 * The visitor's approvals move a value in React state and stop. That is not a
 * shortcut: a decision that is not written to an immutable trail is not a
 * decision this product recognises, so the page says "not saved" everywhere a
 * visitor might reasonably assume otherwise.
 */

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  ListChecks,
  RotateCcw,
  Scale,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import type { ReviewItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { demoDashboard, demoReviewItems } from "@/components/demo/demo-data";
import { DemoBoundary } from "@/components/demo/demo-boundary";
import { DemoDashboard } from "@/components/demo/demo-dashboard";
import { DemoReviewQueue, type QueueFilter } from "@/components/demo/demo-review-queue";

const TABS = [
  { key: "queue", label: "Review queue", icon: ListChecks },
  { key: "dashboard", label: "Dashboard", icon: BarChart3 },
  { key: "boundary", label: "What the AI did", icon: ShieldCheck },
] as const;

type TabKey = (typeof TABS)[number]["key"];

/**
 * Call-to-action links wear the Button look without being buttons: a real
 * `<button>` inside an `<a>` is nested interactive content, which screen
 * readers announce twice and keyboards stop at twice.
 */
const CTA_BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:outline-none";
const CTA_PRIMARY = `${CTA_BASE} bg-linear-to-b from-brand-700 to-brand-800 text-white shadow-sm hover:from-brand-800 hover:to-brand-900 focus-visible:ring-brand-600`;
const CTA_OUTLINE = `${CTA_BASE} border border-slate-300 bg-white text-ink-900 hover:border-brand-600 hover:bg-slate-50 focus-visible:ring-brand-600`;

export function DemoPlayground() {
  const [items, setItems] = React.useState<ReviewItem[]>(() => demoReviewItems());
  const [tab, setTab] = React.useState<TabKey>("queue");
  const [filter, setFilter] = React.useState<QueueFilter>("all");
  const [expandedId, setExpandedId] = React.useState<string | null>(null);
  const [jumpToken, setJumpToken] = React.useState(0);
  const [announcement, setAnnouncement] = React.useState("");

  const tabRefs = React.useRef<(HTMLButtonElement | null)[]>([]);

  /** Local only: no request, no audit record, nothing that outlives the tab. */
  const decide = React.useCallback(
    (id: string, decision: "approved" | "rejected", reason?: string) => {
      setItems((current) =>
        current.map((item) =>
          item.review_item_id === id
            ? {
                ...item,
                decision,
                decided_by: "you (demo)",
                decided_at: new Date().toISOString(),
                rejection_reason: decision === "rejected" ? (reason ?? null) : null,
              }
            : item,
        ),
      );
      setAnnouncement(
        `${id} marked ${decision} in this browser only. Nothing was saved.`,
      );
    },
    [],
  );

  /** From a next-best action: switch tabs, clear the filter, open that row. */
  const openItem = React.useCallback((reviewItemId: string) => {
    setTab("queue");
    setFilter("all");
    setExpandedId(reviewItemId);
    setJumpToken((token) => token + 1);
  }, []);

  const reset = () => {
    setItems(demoReviewItems());
    setExpandedId(null);
    setFilter("all");
    setAnnouncement("Demo reset to the seeded sample data.");
  };

  /** Arrow keys move between tabs, as a tablist is expected to. */
  const onTabKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = TABS.length - 1;
    let next: number | null = null;
    if (event.key === "ArrowRight") next = index === last ? 0 : index + 1;
    else if (event.key === "ArrowLeft") next = index === 0 ? last : index - 1;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = last;
    if (next === null) return;
    event.preventDefault();
    setTab(TABS[next].key);
    tabRefs.current[next]?.focus();
  };

  const decided = items.filter((item) => item.decision !== "pending").length;

  return (
    <div className="min-h-screen bg-surface">
      {/* `px-4! py-0!`: globals.css forces padding onto every `header` at
          ≤768px for the signed-in shell, and this public page sets its own. */}
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 px-4! py-0! backdrop-blur sm:px-6!">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-3">
          <Link
            href="/"
            className="flex shrink-0 items-center gap-1.5 text-lg font-bold tracking-tight text-ink-900"
          >
            <Scale className="h-5 w-5 text-brand-700" aria-hidden />
            <span>
              Tara<span className="text-brand-700">zu</span>
            </span>
          </Link>
          <div className="flex items-center gap-2 sm:gap-4">
            <Link
              href="/"
              className="hidden text-sm font-medium text-ink-600 transition-colors hover:text-ink-900 sm:block"
            >
              Back to home
            </Link>
            <Link
              href="/login"
              className="text-sm font-medium text-ink-600 transition-colors hover:text-ink-900"
            >
              Sign in
            </Link>
            {/* The full wording needs room the 390px header does not have,
                next to the logo and the sign-in link. */}
            <Link href="/signup" className={cn(CTA_PRIMARY, "h-8 px-3 text-xs sm:px-4")}>
              <span className="sm:hidden">Try it free</span>
              <span className="hidden sm:inline">Start with your own case</span>
            </Link>
          </div>
        </div>
      </header>

      {/* `p-0!` cancels the same shell rule for `main`. */}
      <main className="p-0!">
        {/* The banner a visitor cannot miss, above everything they might
            mistake for a real engagement. */}
        <div className="border-b border-amber-300 bg-amber-50">
          <div className="mx-auto flex max-w-6xl items-start gap-2.5 px-4 py-2.5 sm:px-6">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" aria-hidden />
            <p className="text-xs leading-relaxed text-amber-900 sm:text-sm">
              <span className="font-semibold">This is sample data.</span> A seeded
              engagement for a fictional client, Haroon Textiles, June 2026. No real books,
              no backend, no signup. Nothing you approve or reject here is saved.
            </p>
          </div>
        </div>

        <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
          {/* Intro */}
          <div className="mb-6 max-w-3xl">
            <p className="mb-2 text-[11px] font-semibold tracking-[0.12em] text-brand-700 uppercase">
              Interactive demo
            </p>
            <h1 className="text-2xl font-bold tracking-tight text-ink-900 sm:text-3xl">
              Work a real engagement, without signing up
            </h1>
            <p className="mt-3 text-sm leading-relaxed text-ink-600 sm:text-base">
              Ten ledger entries, one bank statement, two invoices. Everything below has
              already been through the pipeline: an AI read the documents, deterministic
              Python matched and flagged them, and the queue is waiting for the one thing
              only a human can do.
            </p>
            <p className="mt-3 text-sm leading-relaxed font-medium text-ink-900">
              Tarazu reconciles your books, flags what needs attention, and explains it in
              plain language. The AI assists, the human decides.
            </p>
          </div>

          {/* Tabs */}
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div
              role="tablist"
              aria-label="Demo walkthrough"
              className="flex flex-wrap gap-1 rounded-lg border border-slate-200 bg-white p-1 shadow-sm"
            >
              {TABS.map(({ key, label, icon: Icon }, index) => {
                const active = tab === key;
                return (
                  <button
                    key={key}
                    ref={(element) => {
                      tabRefs.current[index] = element;
                    }}
                    id={`demo-tab-${key}`}
                    role="tab"
                    type="button"
                    aria-selected={active}
                    aria-controls={`demo-tabpanel-${key}`}
                    tabIndex={active ? 0 : -1}
                    onClick={() => setTab(key)}
                    onKeyDown={(event) => onTabKeyDown(event, index)}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:outline-none sm:px-4 sm:text-sm",
                      active
                        ? "bg-brand-800 text-white"
                        : "text-ink-600 hover:bg-slate-100 hover:text-brand-700",
                    )}
                  >
                    <Icon className="h-4 w-4" aria-hidden />
                    {label}
                  </button>
                );
              })}
            </div>
            {decided > 0 && (
              <Button variant="outline" size="sm" onClick={reset}>
                <RotateCcw className="h-3.5 w-3.5" aria-hidden />
                Reset the demo
              </Button>
            )}
          </div>

          {/* Screen-reader confirmation of a local decision. */}
          <p role="status" aria-live="polite" className="sr-only">
            {announcement}
          </p>

          {/* Panels. Kept mounted-on-demand rather than hidden so the Benford
              chart measures a real width when its tab first opens. */}
          <div
            id="demo-tabpanel-queue"
            role="tabpanel"
            aria-labelledby="demo-tab-queue"
            tabIndex={-1}
            hidden={tab !== "queue"}
          >
            {tab === "queue" && (
              <DemoReviewQueue
                items={items}
                filter={filter}
                onFilterChange={setFilter}
                expandedId={expandedId}
                onExpandedChange={setExpandedId}
                onDecide={decide}
                jumpToken={jumpToken}
              />
            )}
          </div>
          <div
            id="demo-tabpanel-dashboard"
            role="tabpanel"
            aria-labelledby="demo-tab-dashboard"
            tabIndex={-1}
            hidden={tab !== "dashboard"}
          >
            {tab === "dashboard" && (
              <DemoDashboard
                summary={demoDashboard}
                items={items}
                onOpenItem={openItem}
              />
            )}
          </div>
          <div
            id="demo-tabpanel-boundary"
            role="tabpanel"
            aria-labelledby="demo-tab-boundary"
            tabIndex={-1}
            hidden={tab !== "boundary"}
          >
            {tab === "boundary" && <DemoBoundary />}
          </div>

          {/* Closing CTA */}
          <section className="mt-8 rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
            <div className="sm:flex sm:items-center sm:justify-between sm:gap-6">
              <div className="max-w-xl">
                <h2 className="text-lg font-bold text-ink-900 sm:text-xl">
                  Run this over your own books
                </h2>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-600">
                  Upload a bank statement, your invoices and a ledger. You get the same
                  queue over your own numbers, with the evidence, the confidence levels and
                  an audit trail that is written once and never edited.
                </p>
              </div>
              <div className="mt-4 flex shrink-0 flex-col gap-2 sm:mt-0 sm:w-52">
                <Link href="/signup" className={cn(CTA_PRIMARY, "h-11 px-6 text-sm")}>
                  Start with your own case
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </Link>
                <Link href="/" className={cn(CTA_OUTLINE, "h-11 px-6 text-sm")}>
                  Back to home
                </Link>
              </div>
            </div>
          </section>

          <p className="mt-6 text-center text-[11px] text-ink-400">
            Sample data only. Tarazu flags items that need review. It does not detect
            fraud and it does not audit anything on its own.
          </p>
        </div>
      </main>
    </div>
  );
}
