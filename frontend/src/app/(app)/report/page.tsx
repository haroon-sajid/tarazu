"use client";

/**
 * Reports — the final deliverable, and the append-only history of producing
 * it. Generating renders both the PDF and the Excel workbook from the case as
 * it stands and records the generation; every generation is a new, immutable
 * report with its own digests, so a file handed to a client can always be
 * shown to be the one that was made.
 *
 * Only items with an explicit human decision are reported as findings.
 * Pending items are counted and named as pending in the report, never listed
 * as if decided.
 */

import * as React from "react";
import { Download, FileSpreadsheet, FileText, Loader2, ShieldCheck } from "lucide-react";
import {
  ApiError,
  createSignOff,
  downloadEvidenceBundle,
  downloadReport,
  FIXTURE_MODE,
  generateReport,
  getDashboard,
  listReports,
  listSignOffs,
} from "@/lib/api";
import type {
  DashboardSummary,
  ReportFormat,
  ReportSummary,
  SignOffListResponse,
} from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { formatDate, formatTimestamp } from "@/lib/format";

export default function ReportPage() {
  const [summary, setSummary] = React.useState<DashboardSummary | null>(null);
  const [history, setHistory] = React.useState<ReportSummary[] | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [noCases, setNoCases] = React.useState(false);
  const [busy, setBusy] = React.useState<ReportFormat | null>(null);
  const [downloading, setDownloading] = React.useState<string | null>(null);
  const [reportError, setReportError] = React.useState<string | null>(null);
  const [latest, setLatest] = React.useState<ReportSummary | null>(null);
  const [signOffs, setSignOffs] = React.useState<SignOffListResponse | null>(null);
  const [signingOff, setSigningOff] = React.useState(false);
  const [signOffError, setSignOffError] = React.useState<string | null>(null);
  const [bundling, setBundling] = React.useState(false);
  const [bundleError, setBundleError] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    setLoadError(null);
    setSummary(null);
    setHistory(null);
    setNoCases(false);
    Promise.all([
      getDashboard(),
      listReports().catch(() => null),
      listSignOffs().catch(() => null),
    ])
      .then(([dashboard, reports, signatures]) => {
        setSummary(dashboard);
        setHistory(reports?.reports ?? []);
        setSignOffs(
          signatures ?? {
            case_id: dashboard.case_id,
            total: 0,
            sign_offs: [],
            required: false,
            satisfied: false,
          },
        );
      })
      .catch((caught) => {
        // "No cases yet" is a state, not a failure: show the upload CTA.
        if (caught instanceof ApiError && caught.status === 404) {
          setNoCases(true);
          return;
        }
        setLoadError(
          caught instanceof ApiError
            ? caught.message
            : "Could not load the case summary.",
        );
      });
  }, []);

  React.useEffect(load, [load]);

  /** Generate a fresh report, then hand the requested file to the browser. */
  const generate = async (format: ReportFormat) => {
    setBusy(format);
    setReportError(null);
    try {
      const report = await generateReport();
      setLatest(report);
      setHistory((current) => [report, ...(current ?? [])]);
      await downloadReport(report, format);
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

  /**
   * Record a sign-off. The backend refuses if anything is still pending, or if
   * the signer decided the items themselves — both are `409`s worth showing
   * verbatim, because each one names the thing to go and do about it.
   */
  const signOff = async () => {
    setSigningOff(true);
    setSignOffError(null);
    try {
      const response = await createSignOff();
      setSignOffs((current) =>
        current
          ? {
              ...current,
              total: current.total + 1,
              satisfied: true,
              sign_offs: [response.sign_off, ...current.sign_offs],
            }
          : current,
      );
    } catch (caught) {
      setSignOffError(
        caught instanceof ApiError ? caught.message : "Could not record the sign-off.",
      );
    } finally {
      setSigningOff(false);
    }
  };

  const exportBundle = async () => {
    setBundling(true);
    setBundleError(null);
    try {
      await downloadEvidenceBundle();
    } catch (caught) {
      setBundleError(
        caught instanceof ApiError ? caught.message : "Could not build the bundle.",
      );
    } finally {
      setBundling(false);
    }
  };

  const download = async (report: ReportSummary, format: ReportFormat) => {
    setDownloading(`${report.report_id}:${format}`);
    setReportError(null);
    try {
      await downloadReport(report, format);
    } catch (caught) {
      setReportError(
        caught instanceof ApiError ? caught.message : "Download failed. Try again.",
      );
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-ink-900">Reports</h1>
        <p className="mt-1 text-sm text-ink-600">
          The final report carries every decided item, every flag on it, the
          provenance of every figure, the Benford analysis, and the full
          immutable audit trail. Each generation is kept for good.
        </p>
      </div>

      {noCases ? (
        <EmptyState
          title="Nothing to report yet"
          message="A report needs a case. Upload a bank statement, invoices, and a ledger first."
        />
      ) : loadError ? (
        <ErrorState message={loadError} onRetry={load} />
      ) : summary === null ? (
        <div className="space-y-4">
          <Skeleton className="h-36" />
          <Skeleton className="h-28" />
        </div>
      ) : (
        <div className="space-y-5">
          <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <Card>
              <CardHeader>
                <CardTitle>What goes into the report</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="grid grid-cols-1 gap-x-8 gap-y-2 text-sm md:grid-cols-2">
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
                        ? `${formatDate(summary.period_start)} to ${formatDate(summary.period_end)}`
                        : "-"}
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-ink-400">Review items</dt>
                    <dd className="font-medium text-ink-900 tabular-nums">
                      {summary.total_review_items}
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-ink-400">Decided</dt>
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
                    The report counts them as pending and does not list them as
                    findings; every verdict in it is a human&apos;s. Generate again after
                    deciding them and the new report is kept alongside this one.
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Generate</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col gap-3">
                  <Button size="lg" disabled={busy !== null} onClick={() => generate("pdf")}>
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
                    onClick={() => generate("excel")}
                  >
                    {busy === "excel" ? (
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    ) : (
                      <FileSpreadsheet className="h-4 w-4" aria-hidden />
                    )}
                    Excel workbook
                  </Button>
                </div>
                <p className="mt-3 text-[11px] leading-relaxed text-ink-400">
                  Both files are produced together on every generation; the
                  button picks which one to download first. The other stays
                  available in the history below.
                </p>
                {FIXTURE_MODE && (
                  <p className="mt-2 text-[11px] text-ink-400">
                    Fixture mode: generation needs the live backend.
                  </p>
                )}
                {reportError && (
                  <p className="mt-3 rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
                    {reportError}
                  </p>
                )}
                {latest && (
                  <p className="mt-3 flex items-start gap-1.5 rounded-md bg-emerald-50 px-3 py-2 text-xs text-emerald-800 ring-1 ring-emerald-200">
                    <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                    <span>
                      Report <span className="font-mono">{latest.report_id}</span> generated
                      and recorded in the audit trail.
                    </span>
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Sign-off</CardTitle>
              </CardHeader>
              <CardContent>
                {signOffs === null ? (
                  <Skeleton className="h-16" />
                ) : (
                  <>
                    <p className="text-sm text-ink-600">
                      A sign-off is the second pair of eyes: whoever decided the
                      items on a case cannot be the one who signs it off.
                      {signOffs.required
                        ? " This client requires one before a report can be generated."
                        : " This client does not require one, so it is optional here."}
                    </p>
                    {signOffs.sign_offs.length > 0 ? (
                      <ul className="mt-3 space-y-2">
                        {signOffs.sign_offs.map((entry) => (
                          <li
                            key={entry.sign_off_id}
                            className="break-words rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs"
                          >
                            <span className="block font-medium text-ink-900">
                              Signed by {entry.signed_by}
                            </span>
                            <span className="block text-ink-400">
                              {formatTimestamp(entry.signed_at)} ·{" "}
                              {entry.approved_count} approved, {entry.rejected_count}{" "}
                              rejected
                            </span>
                            {entry.note && (
                              <span className="mt-1 block text-ink-600">{entry.note}</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-3 text-xs text-ink-400">
                        Not signed off yet.
                      </p>
                    )}
                    <div className="mt-4">
                      <Button
                        variant="outline"
                        disabled={signingOff}
                        onClick={signOff}
                      >
                        {signingOff ? (
                          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                        ) : (
                          <ShieldCheck className="h-4 w-4" aria-hidden />
                        )}
                        Sign this engagement off
                      </Button>
                    </div>
                    {signOffError && (
                      <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 ring-1 ring-amber-200">
                        {signOffError}
                      </p>
                    )}
                  </>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Evidence bundle</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-ink-600">
                  Everything needed to defend this engagement in one zip: the
                  source documents, every generated report, the decided queue,
                  the corrections, the sign-offs, and the complete audit trail,
                  with a <span className="font-mono text-xs">MANIFEST.txt</span>{" "}
                  giving a SHA-256 for every file in it.
                </p>
                <p className="mt-2 text-[11px] leading-relaxed text-ink-400">
                  Hand this to a reviewer, a client, or a regulator: each file in
                  it can be shown to be the file that was made. Taking it out of
                  the building is itself recorded in the trail.
                </p>
                <div className="mt-4">
                  <Button
                    variant="outline"
                    disabled={bundling}
                    onClick={exportBundle}
                  >
                    {bundling ? (
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    ) : (
                      <Download className="h-4 w-4" aria-hidden />
                    )}
                    Download the bundle
                  </Button>
                </div>
                {bundleError && (
                  <p className="mt-3 rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
                    {bundleError}
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Report history</CardTitle>
            </CardHeader>
            <CardContent>
              {history === null ? (
                <Skeleton className="h-16" />
              ) : history.length === 0 ? (
                <p className="text-sm text-ink-400">
                  No report has been generated for this case yet. Every generation
                  is recorded here and can never be edited or removed.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[720px] text-left text-sm">
                    <thead>
                      <tr className="border-b border-slate-200 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                        <th className="py-2 pr-4">Generated</th>
                        <th className="py-2 pr-4">Report</th>
                        <th className="py-2 pr-4 text-right">Items</th>
                        <th className="py-2 pr-4 text-right">Approved</th>
                        <th className="py-2 pr-4 text-right">Rejected</th>
                        <th className="py-2 pr-4 text-right">Pending</th>
                        <th className="py-2 pr-4 text-right">Flags</th>
                        <th className="py-2 pr-4 text-right">Trail entries</th>
                        <th className="py-2 text-right">Files</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.map((report) => (
                        <tr
                          key={report.report_id}
                          className="border-b border-slate-100 last:border-0"
                        >
                          <td className="whitespace-nowrap py-2.5 pr-4 text-ink-600">
                            {formatTimestamp(report.generated_at)}
                          </td>
                          <td className="py-2.5 pr-4">
                            <span className="font-mono text-xs text-ink-900">
                              {report.report_id}
                            </span>
                            <span
                              className="block truncate font-mono text-[10px] text-ink-400"
                              title={`PDF sha256 ${report.pdf_sha256}`}
                            >
                              sha256 {report.pdf_sha256.slice(0, 16)}…
                            </span>
                          </td>
                          <td className="py-2.5 pr-4 text-right tabular-nums">{report.item_count}</td>
                          <td className="py-2.5 pr-4 text-right tabular-nums">{report.approved_count}</td>
                          <td className="py-2.5 pr-4 text-right tabular-nums">{report.rejected_count}</td>
                          <td className="py-2.5 pr-4 text-right tabular-nums">{report.pending_count}</td>
                          <td className="py-2.5 pr-4 text-right tabular-nums">{report.flag_count}</td>
                          <td className="py-2.5 pr-4 text-right tabular-nums">{report.audit_record_count}</td>
                          <td className="py-2.5">
                            <div className="flex justify-end gap-1.5">
                              {(["pdf", "excel"] as ReportFormat[]).map((format) => {
                                const key = `${report.report_id}:${format}`;
                                return (
                                  <Button
                                    key={format}
                                    size="sm"
                                    variant="outline"
                                    disabled={downloading !== null}
                                    onClick={() => download(report, format)}
                                    aria-label={`Download ${format} for ${report.report_id}`}
                                  >
                                    {downloading === key ? (
                                      <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                                    ) : (
                                      <Download className="h-3.5 w-3.5" aria-hidden />
                                    )}
                                    {format === "pdf" ? "PDF" : "Excel"}
                                  </Button>
                                );
                              })}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
