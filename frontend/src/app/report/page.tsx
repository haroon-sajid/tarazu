"use client";

/**
 * The report page: the final deliverable. `POST /v1/reports` is still "to be
 * defined" in docs/api-contracts.md, so the buttons call the client honestly
 * and render the error state rather than faking a download.
 */

import * as React from "react";
import { FileSpreadsheet, FileText, Loader2 } from "lucide-react";
import { ApiError, generateReport, getDashboard } from "@/lib/api";
import type { DashboardSummary } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";
import { formatDate } from "@/lib/format";

export default function ReportPage() {
  const [summary, setSummary] = React.useState<DashboardSummary | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<"pdf" | "excel" | null>(null);
  const [reportError, setReportError] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    setLoadError(null);
    setSummary(null);
    getDashboard()
      .then(setSummary)
      .catch((caught) =>
        setLoadError(
          caught instanceof ApiError
            ? caught.message
            : "Could not load the case summary.",
        ),
      );
  }, []);

  React.useEffect(load, [load]);

  const download = async (kind: "pdf" | "excel") => {
    setBusy(kind);
    setReportError(null);
    try {
      await generateReport(kind);
    } catch (caught) {
      setReportError(
        caught instanceof ApiError
          ? caught.message
          : "Report generation failed. Try again.",
      );
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-ink-900">Reports</h1>
        <p className="mt-1 text-sm text-ink-600">
          The final report carries every match, every flag, every human decision,
          and the full immutable audit trail behind them.
        </p>
      </div>

      {loadError ? (
        <ErrorState message={loadError} onRetry={load} />
      ) : summary === null ? (
        <div className="space-y-4">
          <Skeleton className="h-36" />
          <Skeleton className="h-28" />
        </div>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>What goes into the report</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-ink-400">Client</dt>
                  <dd className="font-medium text-ink-900">{summary.client_name}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-400">Case</dt>
                  <dd className="font-mono text-xs text-ink-900">{summary.case_id}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-400">Period</dt>
                  <dd className="font-medium text-ink-900">
                    {summary.period_start && summary.period_end
                      ? `${formatDate(summary.period_start)} – ${formatDate(summary.period_end)}`
                      : "—"}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-400">Review items</dt>
                  <dd className="font-medium text-ink-900 tabular-nums">
                    {summary.total_review_items}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-400">Decisions made</dt>
                  <dd className="font-medium text-ink-900 tabular-nums">
                    {summary.decisions.approved + summary.decisions.rejected} of{" "}
                    {summary.total_review_items}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-400">Flags raised</dt>
                  <dd className="font-medium text-ink-900 tabular-nums">
                    {summary.total_flags}
                  </dd>
                </div>
              </dl>
              {summary.decisions.pending > 0 && (
                <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 ring-1 ring-amber-200">
                  {summary.decisions.pending} item
                  {summary.decisions.pending > 1 ? "s are" : " is"} still pending.
                  The report will mark them as undecided — every verdict in it is
                  a human&apos;s.
                </p>
              )}
            </CardContent>
          </Card>

          <Card className="mt-4">
            <CardHeader>
              <CardTitle>Download</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex gap-3">
                <Button
                  size="lg"
                  disabled={busy !== null}
                  onClick={() => download("pdf")}
                >
                  {busy === "pdf" ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                  ) : (
                    <FileText className="h-4 w-4" aria-hidden />
                  )}
                  PDF report
                </Button>
                <Button
                  size="lg"
                  variant="outline"
                  disabled={busy !== null}
                  onClick={() => download("excel")}
                >
                  {busy === "excel" ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                  ) : (
                    <FileSpreadsheet className="h-4 w-4" aria-hidden />
                  )}
                  Excel workbook
                </Button>
              </div>
              {reportError && (
                <p className="mt-3 rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
                  {reportError}
                </p>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
