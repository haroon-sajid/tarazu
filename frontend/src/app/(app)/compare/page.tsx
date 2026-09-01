"use client";

/**
 * Compare periods — one engagement read against another, which is how an
 * auditor actually forms an expectation. "Forty entries last month and a
 * hundred and ten this month" is a question worth asking before a single item
 * is opened.
 *
 * Both sides come from one backend route, not from two dashboards stitched
 * together in the browser: every measure, every difference, and the judgement
 * of which movements are worth stopping on is computed once, deterministically,
 * from stored results. This screen picks the two periods and lays the answer
 * out.
 *
 * Nothing here says what a movement *means*. A highlighted row says "look at
 * this"; the reading is the auditor's, and there is no wording on this page
 * that pretends otherwise.
 */

import * as React from "react";
import Link from "next/link";
import { ArrowLeftRight, MinusCircle, PlusCircle } from "lucide-react";
import { ApiError, comparePeriods, listCases } from "@/lib/api";
import type { CaseSummary, CompareResponse } from "@/lib/types";
import { formatDate, formatTimestamp } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";

/** One line in a picker: who it is and which period, so two months of the
 *  same client can be told apart at a glance. */
function caseLabel(summary: CaseSummary): string {
  const period =
    summary.period_start && summary.period_end
      ? `${formatDate(summary.period_start)} to ${formatDate(summary.period_end)}`
      : "period not set";
  return `${summary.client_name} · ${period}`;
}

/** The header card above each column. Counts are the case's, as the backend
 *  counted them for this comparison. */
function PeriodHeader({
  side,
  summary,
}: {
  side: "Earlier period" | "Later period";
  summary: CaseSummary;
}) {
  return (
    <Card>
      <CardContent className="px-4 py-3.5">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
          {side}
        </p>
        <p className="mt-1 truncate text-sm font-semibold text-ink-900">
          {summary.client_name}
        </p>
        <p className="mt-0.5 text-xs text-ink-600">
          {summary.period_start && summary.period_end
            ? `${formatDate(summary.period_start)} to ${formatDate(summary.period_end)}`
            : "Period not set"}
        </p>
        <p className="mt-1 font-mono text-[10px] text-ink-400">{summary.case_id}</p>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink-600">
          <span className="capitalize">{summary.status.replace(/_/g, " ")}</span>
          <span className="tabular-nums">{summary.total_review_items} items</span>
          <span className="tabular-nums">{summary.pending_items} pending</span>
          <span className="tabular-nums">{summary.flagged_items} flagged</span>
        </div>
        <p className="mt-1.5 text-[10px] text-ink-400">
          Created {formatTimestamp(summary.created_at)}
        </p>
      </CardContent>
    </Card>
  );
}

/** A list of parties that appear on one side only. */
function PartyList({
  title,
  explanation,
  parties,
  icon: Icon,
  tone,
}: {
  title: string;
  explanation: string;
  parties: string[];
  icon: React.ComponentType<{ className?: string }>;
  tone: "new" | "dropped";
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <Icon
            className={cn(
              "h-4 w-4",
              tone === "new" ? "text-brand-700" : "text-amber-600",
            )}
            aria-hidden
          />
          {title}
          <span className="ml-1 text-xs font-normal text-ink-400 tabular-nums">
            {parties.length}
          </span>
        </CardTitle>
        <p className="mt-1 text-xs leading-relaxed text-ink-600">{explanation}</p>
      </CardHeader>
      <CardContent>
        {parties.length === 0 ? (
          <p className="rounded-md border border-dashed border-slate-300 px-4 py-6 text-center text-xs text-ink-600">
            None.
          </p>
        ) : (
          <ul className="max-h-64 space-y-1 overflow-y-auto">
            {parties.map((party) => (
              <li
                key={party}
                className="truncate rounded-md bg-slate-50 px-3 py-1.5 text-sm text-ink-900 ring-1 ring-slate-200"
              >
                {party}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export default function ComparePage() {
  const [cases, setCases] = React.useState<CaseSummary[] | null>(null);
  const [casesError, setCasesError] = React.useState<string | null>(null);

  const [leftId, setLeftId] = React.useState("");
  const [rightId, setRightId] = React.useState("");

  const [comparison, setComparison] = React.useState<CompareResponse | null>(null);
  const [compareError, setCompareError] = React.useState<string | null>(null);
  const [unavailable, setUnavailable] = React.useState<string | null>(null);
  const [comparing, setComparing] = React.useState(false);

  const loadCases = React.useCallback(() => {
    setCasesError(null);
    setCases(null);
    listCases()
      .then((response) => {
        setCases(response.cases);
        // `GET /v1/cases` comes back newest first, so the two most recent are
        // the first two rows — the later one on the right, where a reader
        // expects "now" to sit.
        if (response.cases.length >= 2) {
          setRightId(response.cases[0].case_id);
          setLeftId(response.cases[1].case_id);
        }
      })
      .catch((caught) =>
        setCasesError(
          caught instanceof ApiError ? caught.message : "Could not load the cases.",
        ),
      );
  }, []);

  React.useEffect(loadCases, [loadCases]);

  const runComparison = React.useCallback(() => {
    if (!leftId || !rightId || leftId === rightId) return;
    setComparing(true);
    setCompareError(null);
    setUnavailable(null);
    setComparison(null);
    comparePeriods(leftId, rightId)
      .then(setComparison)
      .catch((caught) => {
        if (caught instanceof ApiError && caught.status === 501) {
          setUnavailable(caught.message);
          return;
        }
        setCompareError(
          caught instanceof ApiError
            ? caught.message
            : "Could not compare the two periods.",
        );
      })
      .finally(() => setComparing(false));
  }, [leftId, rightId]);

  React.useEffect(runComparison, [runComparison]);

  const header = (
    <div className="mb-5">
      <h1 className="text-xl font-bold text-ink-900">Compare periods</h1>
      <p className="mt-1 text-sm text-ink-600">
        Two engagements side by side, measure by measure, plus the parties who
        arrived and the ones who stopped appearing. Every figure is counted by
        the backend from stored results.
      </p>
    </div>
  );

  if (casesError) {
    return (
      <div>
        {header}
        <ErrorState message={casesError} onRetry={loadCases} />
      </div>
    );
  }

  if (cases === null) {
    return (
      <div>
        {header}
        <Skeleton className="h-20 w-full" />
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
        <Skeleton className="mt-4 h-64 w-full" />
      </div>
    );
  }

  if (cases.length < 2) {
    return (
      <div>
        {header}
        <EmptyState
          title="Two periods are needed"
          message={
            cases.length === 0
              ? "There is nothing to compare yet. Upload a bank statement, invoices, and a ledger to run the first period."
              : "There is one period so far. Run a second and it will appear here. The same client's next month is the comparison this screen was built for."
          }
          action={
            <Link href="/upload">
              <Button size="sm">Go to upload</Button>
            </Link>
          }
        />
      </div>
    );
  }

  const sameCase = leftId !== "" && leftId === rightId;

  return (
    <div>
      {header}

      {/* The two pickers */}
      <Card>
        <CardContent className="px-4 py-4">
          <div className="grid grid-cols-1 items-end gap-3 md:grid-cols-[1fr_auto_1fr]">
            <Select
              label="Earlier period"
              value={leftId}
              onChange={(event) => setLeftId(event.target.value)}
              hint="The period you are reading the other one against."
            >
              {cases.map((summary) => (
                <option key={summary.case_id} value={summary.case_id}>
                  {caseLabel(summary)}
                </option>
              ))}
            </Select>
            <div className="flex justify-center pb-6 md:pb-8">
              <button
                type="button"
                onClick={() => {
                  const previous = leftId;
                  setLeftId(rightId);
                  setRightId(previous);
                }}
                title="Swap the two periods"
                aria-label="Swap the two periods"
                className="rounded-md border border-slate-300 p-2 text-ink-600 transition-colors hover:border-brand-600 hover:text-brand-700"
              >
                <ArrowLeftRight className="h-4 w-4" aria-hidden />
              </button>
            </div>
            <Select
              label="Later period"
              value={rightId}
              onChange={(event) => setRightId(event.target.value)}
              hint="The period under review."
            >
              {cases.map((summary) => (
                <option key={summary.case_id} value={summary.case_id}>
                  {caseLabel(summary)}
                </option>
              ))}
            </Select>
          </div>
        </CardContent>
      </Card>

      {sameCase ? (
        <div className="mt-4">
          <EmptyState
            title="Pick two different periods"
            message="Both pickers are on the same engagement. Choose another period on either side and the comparison appears."
          />
        </div>
      ) : unavailable ? (
        <div className="mt-4">
          <EmptyState
            title="Comparison needs the live backend"
            message={`${unavailable} Both periods are read and counted server-side; there is nothing to compare, and nothing worth inventing, while the app is running on sample fixtures.`}
          />
        </div>
      ) : compareError ? (
        <div className="mt-4">
          <ErrorState message={compareError} onRetry={runComparison} />
        </div>
      ) : comparing || !comparison ? (
        <div className="mt-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
          <Skeleton className="mt-4 h-64 w-full" />
        </div>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <PeriodHeader side="Earlier period" summary={comparison.left} />
            <PeriodHeader side="Later period" summary={comparison.right} />
          </div>

          <Card className="mt-4">
            <CardHeader>
              <CardTitle>Measure by measure</CardTitle>
              <p className="mt-1 text-xs leading-relaxed text-ink-600">
                Highlighted rows are the movements the backend marks as worth
                stopping on: a large swing either way, or any rise in a count
                where a rise is itself the news. What the difference means is
                yours to decide.
              </p>
            </CardHeader>
            <CardContent>
              {comparison.deltas.length === 0 ? (
                <p className="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-ink-600">
                  There is nothing measurable in these two periods yet.
                </p>
              ) : (
                <>
                  {/* Below md the table's columns stack: one block per measure,
                      the earlier and later readings and the change under its
                      label, so a row reads without scrolling sideways. Same
                      rows, same values, same tones as the table. */}
                  <ul className="space-y-2 md:hidden">
                    {comparison.deltas.map((delta) => (
                      <li
                        key={delta.label}
                        className={cn(
                          "rounded-lg border border-slate-200 px-3 py-2.5",
                          delta.notable && "border-amber-200 bg-amber-50/60",
                        )}
                      >
                        <span className="flex flex-wrap items-center gap-2 text-sm text-ink-900">
                          {delta.label}
                          {delta.notable && (
                            <span
                              className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800 ring-1 ring-amber-300"
                              title="The backend marked this movement as worth a look"
                            >
                              Notable
                            </span>
                          )}
                        </span>
                        <dl className="mt-1.5 space-y-1 text-sm">
                          <div className="flex items-baseline justify-between gap-3">
                            <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                              Earlier
                            </dt>
                            <dd className="min-w-0 break-words text-right tabular-nums text-ink-600">
                              {delta.left}
                            </dd>
                          </div>
                          <div className="flex items-baseline justify-between gap-3">
                            <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                              Later
                            </dt>
                            <dd className="min-w-0 break-words text-right tabular-nums text-ink-900">
                              {delta.right}
                            </dd>
                          </div>
                          <div className="flex items-baseline justify-between gap-3">
                            <dt className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                              Change
                            </dt>
                            <dd
                              className={cn(
                                "min-w-0 break-words text-right tabular-nums",
                                delta.notable
                                  ? "font-semibold text-amber-800"
                                  : "text-ink-600",
                              )}
                            >
                              {delta.change || "-"}
                            </dd>
                          </div>
                        </dl>
                      </li>
                    ))}
                  </ul>
                  <div className="hidden overflow-x-auto rounded-lg border border-slate-200 md:block">
                    <table className="w-full min-w-[560px] text-left">
                      <thead>
                        <tr className="border-b border-slate-200 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                          <th className="px-4 py-2.5">Measure</th>
                          <th className="px-4 py-2.5 text-right">Earlier</th>
                          <th className="px-4 py-2.5 text-right">Later</th>
                          <th className="px-4 py-2.5 text-right">Change</th>
                        </tr>
                      </thead>
                      <tbody>
                        {comparison.deltas.map((delta) => (
                          <tr
                            key={delta.label}
                            className={cn(
                              "border-b border-slate-100 text-sm last:border-0",
                              delta.notable && "bg-amber-50/60",
                            )}
                          >
                            <td className="px-4 py-3 text-ink-900">
                              <span className="flex items-center gap-2">
                                {delta.label}
                                {delta.notable && (
                                  <span
                                    className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800 ring-1 ring-amber-300"
                                    title="The backend marked this movement as worth a look"
                                  >
                                    Notable
                                  </span>
                                )}
                              </span>
                            </td>
                            <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-600">
                              {delta.left}
                            </td>
                            <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                              {delta.right}
                            </td>
                            <td
                              className={cn(
                                "whitespace-nowrap px-4 py-3 text-right tabular-nums",
                                delta.notable
                                  ? "font-semibold text-amber-800"
                                  : "text-ink-600",
                              )}
                            >
                              {delta.change || "-"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
            <PartyList
              title="New parties"
              explanation="In the later period and not the earlier one. A supplier who arrived this period is worth a question, and appears in no count."
              parties={comparison.new_parties}
              icon={PlusCircle}
              tone="new"
            />
            <PartyList
              title="Parties that dropped out"
              explanation="In the earlier period and not the later one. A supplier who stopped being paid is worth the same question, the other way round."
              parties={comparison.dropped_parties}
              icon={MinusCircle}
              tone="dropped"
            />
          </div>

          <p className="mt-4 text-[11px] leading-relaxed text-ink-400">
            Parties are matched on a normalised name and shown as the ledger
            spells them. Comparing two periods reads stored results and changes
            nothing: no item is decided, and no entry is written to either
            case&apos;s audit trail.
          </p>
        </>
      )}
    </div>
  );
}
