"use client";

/**
 * The first-run checklist: four steps from an empty account to a finished
 * report, on the dashboard, for as long as they are useful.
 *
 * A new auditor lands on a dashboard full of words they have not earned yet —
 * readiness score, Benford, next best actions — and the one thing they need to
 * know is that the product is a short pipeline: upload, look, decide, report.
 * Each step carries a line of plain English about *why* it exists rather than
 * what to click, because "decide every item" is a promise about the product,
 * not a chore: the AI never approves anything, so nothing is finished until a
 * person says so.
 *
 * It disappears on its own when the work is done, so it never becomes
 * furniture. The dismiss control is for the auditor who has done this fifty
 * times and does not need step one explained again.
 */

import * as React from "react";
import Link from "next/link";
import { ArrowRight, Check, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";

/**
 * Namespaced like the app's other browser keys (`tarazu.session`,
 * `tarazu.active-case`, `tarazu.sidebar`). Presentation state only — nothing
 * about the case, the org or the trail is ever kept here.
 */
const DISMISSED_KEY = "tarazu.first-run-checklist";
const DISMISSED_VALUE = "dismissed";

export interface FirstRunChecklistProps {
  /** A case exists, so the pipeline has run and there is a queue to work. */
  hasCase: boolean;
  /** At least one item carries an explicit human approve or reject. */
  hasDecisions: boolean;
  /** A report has been generated for the case. */
  hasReport: boolean;
  /** Called after the visitor dismisses it, in case the page wants to react. */
  onDismiss?: () => void;
}

interface Step {
  title: string;
  href: string;
  why: string;
  done: boolean;
}

export function FirstRunChecklist({
  hasCase,
  hasDecisions,
  hasReport,
  onDismiss,
}: FirstRunChecklistProps) {
  // Three states, not two: `null` means localStorage has not been read yet.
  // Rendering the card during that first pass would flash it at every auditor
  // who has already dismissed it, and seeding the state from localStorage
  // directly would mismatch the server-rendered markup.
  const [dismissed, setDismissed] = React.useState<boolean | null>(null);

  React.useEffect(() => {
    try {
      setDismissed(window.localStorage.getItem(DISMISSED_KEY) === DISMISSED_VALUE);
    } catch {
      // Private windows and blocked storage throw on access. Showing the
      // checklist is the safe failure: it is guidance, not a secret.
      setDismissed(false);
    }
  }, []);

  const dismiss = () => {
    setDismissed(true);
    try {
      window.localStorage.setItem(DISMISSED_KEY, DISMISSED_VALUE);
    } catch {
      // Nothing to do: it stays hidden for this visit and returns on the next.
    }
    onDismiss?.();
  };

  const steps: Step[] = [
    {
      title: "Upload documents",
      href: "/upload",
      why: "A bank statement, the invoices and a ledger. Tarazu audits records you already keep. It never asks you to type them in again.",
      done: hasCase,
    },
    {
      title: "Review the queue",
      href: "/review",
      why: "Matching, the red-flag rules and Benford have already run in deterministic code. The queue is where you see what they found.",
      done: hasCase,
    },
    {
      title: "Decide every item",
      href: "/review",
      why: "Nothing is approved for you. Each row waits for your explicit approve or reject, and each decision is written to the immutable trail.",
      done: hasDecisions,
    },
    {
      title: "Generate the report",
      href: "/report",
      why: "PDF and Excel built from the items you decided, with the provenance behind every figure and the trail attached.",
      done: hasReport,
    },
  ];

  const activeIndex = steps.findIndex((step) => !step.done);

  // Nothing left to guide, or the auditor asked it to go. Also covers the
  // first pass, before localStorage has answered.
  if (dismissed !== false || activeIndex === -1) return null;

  const doneCount = steps.filter((step) => step.done).length;

  const progress = Math.round((doneCount / steps.length) * 100);

  return (
    <Card className="overflow-hidden border-slate-200 bg-white shadow-sm">
      <CardContent className="px-4 py-4 sm:px-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-ink-900">Finish your first case</h2>
            <p className="mt-0.5 text-xs text-ink-500">
              {doneCount === steps.length
                ? "All set. Your first case is complete."
                : `Four steps from an upload to a signed report. ${doneCount} of ${steps.length} complete.`}
            </p>
          </div>
          <button
            type="button"
            onClick={dismiss}
            aria-label="Dismiss the first-run checklist"
            className="-mt-1 -mr-1 shrink-0 rounded-md p-1.5 text-ink-400 transition-colors hover:bg-slate-100 hover:text-ink-600 focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:outline-none"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        {/* Progress bar */}
        <div className="mt-3 flex items-center gap-2">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-emerald-500 transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="text-[10px] font-medium tabular-nums text-ink-500">
            {progress}%
          </span>
        </div>

        <ol className="relative mt-4 space-y-1">
          {steps.map((step, index) => {
            const active = index === activeIndex;
            const last = index === steps.length - 1;
            return (
              <li key={step.title} className="relative">
                {!last && (
                  <span
                    aria-hidden
                    className="absolute left-[9px] top-6 h-[calc(100%+4px)] w-px bg-slate-100"
                  />
                )}
                <Link
                  href={step.href}
                  className={cn(
                    "group flex items-start gap-3 rounded-lg px-2 py-2 transition-colors",
                    active
                      ? "bg-brand-50 ring-1 ring-brand-200"
                      : "hover:bg-slate-50",
                  )}
                  aria-current={active ? "step" : undefined}
                >
                  <span
                    className={cn(
                      "relative z-10 mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold tabular-nums",
                      step.done
                        ? "bg-emerald-100 text-emerald-700"
                        : active
                          ? "bg-brand-800 text-white"
                          : "bg-slate-100 text-ink-400",
                    )}
                  >
                    {step.done ? (
                      <>
                        <Check className="h-3 w-3" aria-hidden />
                        <span className="sr-only">Done:</span>
                      </>
                    ) : (
                      index + 1
                    )}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center justify-between gap-2">
                      <span
                        className={cn(
                          "text-sm font-medium",
                          step.done
                            ? "text-ink-500"
                            : active
                              ? "text-ink-900"
                              : "text-ink-400",
                        )}
                      >
                        {step.title}
                      </span>
                      {active && (
                        <ArrowRight className="h-4 w-4 shrink-0 text-brand-700" aria-hidden />
                      )}
                      {step.done && !active && (
                        <Check className="h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
                      )}
                    </span>
                    <span
                      className={cn(
                        "mt-0.5 block text-[11px] leading-relaxed",
                        step.done
                          ? "text-ink-400"
                          : active
                            ? "text-ink-600"
                            : "text-ink-400",
                      )}
                    >
                      {step.why}
                    </span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}
