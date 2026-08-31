"use client";

/**
 * Upload — three required inputs and an optional fourth open a case, and the
 * analysis is visible while it runs.
 *
 * The progress on this screen is **real**. The upload is queued as a background
 * job (`?background=true`) and this page polls `GET /v1/jobs/{id}`: the bar and
 * the stage name are the pipeline's own `progress` and `step`, not a timer
 * pretending. That matters beyond honesty — extraction over a real bank
 * statement takes tens of seconds, and a request held open that long is one the
 * network will drop before the work finishes.
 *
 * Picking a client makes the case one *period* of a recurring engagement (ADR
 * 0005), and the red-flag thresholds become that client's own rather than the
 * firm-wide defaults.
 *
 * The optional fourth input, a sales-data export (Excel or CSV), feeds the
 * deterministic sales-analytics module — no AI on that path, same as the ledger.
 *
 * Nothing here computes: every count on the result screen is the backend's.
 */

import * as React from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Check,
  FileSearch,
  Files,
  FlaskConical,
  Loader2,
  ScanText,
  UploadCloud,
} from "lucide-react";
import {
  ApiError,
  FIXTURE_MODE,
  getJob,
  getReviewItems,
  listClients,
  setActiveCaseId,
  uploadDocuments,
} from "@/lib/api";
import type { ClientSummary, JobSummary, UploadResponse } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/states";
import { DropZone } from "@/components/upload/drop-zone";
import { cn } from "@/lib/utils";

type Phase = "idle" | "working" | "done";

/**
 * What the pipeline does, in order, with the progress percentage each stage is
 * reported at by `app/pipeline.py`. The percentages live here only so the list
 * can light up in step with the job; the bar itself uses the job's own number.
 */
const PIPELINE_STEPS = [
  {
    icon: UploadCloud,
    label: "Storing documents",
    detail:
      "Bank statement, ledger, invoices, and optionally sales data stored against the new case.",
    at: 5,
  },
  {
    icon: ScanText,
    label: "Reading documents",
    detail:
      "Spreadsheets are read by pandas with no model involved. Anything only on paper goes to the vision model, and every value it reads carries a confidence level and its page-and-position source.",
    at: 15,
  },
  {
    icon: FileSearch,
    label: "Matching transactions",
    detail:
      "Pure pandas, three tiers: exact amount and date, then a ±3-day window, then tolerance. No AI touches a number.",
    at: 70,
  },
  {
    icon: FlaskConical,
    label: "Rules and Benford",
    detail:
      "Round numbers · duplicates · weekend entries · near-limit amounts · structuring · sequence gaps, then the first-digit distribution.",
    at: 82,
  },
  {
    icon: BarChart3,
    label: "Sales analytics",
    detail:
      "Revenue by month, product, and region, top customers, and anomalies — deterministic pandas, run when a sales export was uploaded.",
    at: 90,
  },
  {
    icon: Check,
    label: "Review queue ready",
    detail: "Every row assembled with its evidence, waiting for your decision.",
    at: 95,
  },
] as const;

/** How often the job is polled. Fast enough to feel live, slow enough to be cheap. */
const POLL_MS = 1200;

function StepRow({
  icon: Icon,
  label,
  detail,
  state,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  detail: string;
  state: "pending" | "running" | "done";
}) {
  return (
    <li className="flex items-start gap-3">
      <span
        className={cn(
          "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
          state === "done" && "bg-emerald-50 text-emerald-600",
          state === "running" && "bg-brand-50 text-brand-700",
          state === "pending" && "bg-slate-100 text-ink-400",
        )}
      >
        {state === "done" ? (
          <Check className="h-3.5 w-3.5" aria-hidden />
        ) : state === "running" ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
        ) : (
          <Icon className="h-3.5 w-3.5" aria-hidden />
        )}
      </span>
      <span className="min-w-0">
        <span
          className={cn(
            "block text-sm font-medium",
            state === "pending" ? "text-ink-400" : "text-ink-900",
          )}
        >
          {label}
        </span>
        <span className="block text-xs leading-relaxed text-ink-400">{detail}</span>
      </span>
    </li>
  );
}

function ResultStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 sm:px-4 sm:py-3">
      <p className="text-xl font-bold text-ink-900 tabular-nums sm:text-2xl">{value}</p>
      <p className="text-[11px] leading-snug text-ink-400 sm:text-xs">{label}</p>
    </div>
  );
}

export default function UploadPage() {
  const [ledger, setLedger] = React.useState<File[]>([]);
  const [bankStatement, setBankStatement] = React.useState<File[]>([]);
  const [invoices, setInvoices] = React.useState<File[]>([]);
  const [salesData, setSalesData] = React.useState<File[]>([]);
  const [clients, setClients] = React.useState<ClientSummary[]>([]);
  const [clientId, setClientId] = React.useState("");
  const [phase, setPhase] = React.useState<Phase>("idle");
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<UploadResponse | null>(null);
  const [itemCount, setItemCount] = React.useState(0);
  const [job, setJob] = React.useState<JobSummary | null>(null);
  const cancelled = React.useRef(false);

  React.useEffect(() => {
    cancelled.current = false;
    return () => {
      cancelled.current = true;
    };
  }, []);

  // The client list is a convenience, not a requirement: a case with no client
  // is a one-off engagement and stays perfectly valid (ADR 0005).
  React.useEffect(() => {
    listClients()
      .then((response) => setClients(response.clients))
      .catch(() => setClients([]));
  }, []);

  const ready =
    ledger.length === 1 && bankStatement.length === 1 && invoices.length >= 1;

  /** Poll until the job stops, then hand back its final state. */
  const followJob = React.useCallback(async (jobId: string): Promise<JobSummary> => {
    for (;;) {
      const current = await getJob(jobId);
      if (!cancelled.current) setJob(current);
      if (current.finished) return current;
      await new Promise((resolve) => window.setTimeout(resolve, POLL_MS));
    }
  }, []);

  const submit = async () => {
    if (!ready || phase === "working") return;
    setPhase("working");
    setError(null);
    setJob(null);
    try {
      const response = await uploadDocuments({
        bankStatement: bankStatement[0],
        ledger: ledger[0],
        invoices,
        ...(salesData.length === 1 ? { salesData: salesData[0] } : {}),
        clientId: clientId || undefined,
      });

      // Fixture mode answers with the finished case and no job to follow.
      if (response.job_id) {
        const finished = await followJob(response.job_id);
        if (finished.status === "failed") {
          setError(
            finished.error ??
              "Processing failed. The case records why; check the case list.",
          );
          setPhase("idle");
          return;
        }
      }
      if (cancelled.current) return;
      setResult(response);
      // A queued upload answered before the queue existed, so its
      // `review_item_count` is zero by construction. The real figure is read
      // back from the case rather than guessed from the job's wording.
      if (response.job_id) {
        try {
          const queue = await getReviewItems({ case_id: response.case_id });
          if (!cancelled.current) setItemCount(queue.total);
        } catch {
          setItemCount(response.review_item_count);
        }
      } else {
        setItemCount(response.review_item_count);
      }
      // The new case becomes the one the whole workspace is about.
      setActiveCaseId(response.case_id);
      setPhase("done");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Upload failed. Check the files and try again.",
      );
      setPhase("idle");
    }
  };

  const progress = job?.progress ?? 0;

  return (
    <div className="pb-20 md:pb-0">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-ink-900">Upload documents</h1>
        <p className="mt-1 text-sm text-ink-600">
          Three required inputs open a case: the client&apos;s ledger, the bank
          statement, and the invoices. Optionally add a sales data export for
          revenue analytics. The AI reads the unstructured files; deterministic
          code does every match, sum, and anomaly; you decide every item.
        </p>
      </div>

      {phase === "done" && result ? (
        <Card>
          <CardHeader>
            <CardTitle>Case {result.case_id} is ready</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-ink-600">
              {job?.step ?? result.message}
            </p>

            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
              <ResultStat label="Documents received" value={result.documents.length} />
              <ResultStat label="Review items created" value={itemCount} />
              <ResultStat
                label="Escalated to you"
                value={result.needs_human_review_count}
              />
            </div>

            <ul className="mt-4 space-y-1 text-xs text-ink-600">
              {result.documents.map((doc) => (
                <li key={doc.document_id} className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-ink-600">
                    {doc.document_id}
                  </span>
                  <span className="min-w-0 break-all">{doc.filename}</span>
                </li>
              ))}
            </ul>
            {result.needs_human_review_count > 0 && (
              <p className="mt-3 flex items-start gap-1.5 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 ring-1 ring-amber-200">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                {result.needs_human_review_count} document
                {result.needs_human_review_count > 1 ? "s" : ""} had the two AI
                reading passes disagree, so those items are escalated to you.
              </p>
            )}
            <div className="mt-4 flex flex-wrap gap-3">
              <Link href="/review">
                <Button>
                  Go to review <ArrowRight className="h-4 w-4" aria-hidden />
                </Button>
              </Link>
              <Link href="/documents">
                <Button variant="outline">
                  <Files className="h-4 w-4" aria-hidden /> Audit the documents
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="min-w-0">
            {clients.length > 0 && (
              <div className="mb-4">
                <label
                  htmlFor="upload-client"
                  className="mb-1 block text-xs font-medium text-ink-600"
                >
                  Client (optional)
                </label>
                <select
                  id="upload-client"
                  value={clientId}
                  onChange={(event) => setClientId(event.target.value)}
                  disabled={phase === "working"}
                  className="h-10 w-full max-w-sm rounded-lg border border-slate-300 bg-white px-3 text-sm text-ink-900 focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                >
                  <option value="">One-off engagement (firm defaults)</option>
                  {clients.map((client) => (
                    <option key={client.client_id} value={client.client_id}>
                      {client.name}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-[11px] text-ink-400">
                  Picking a client makes this one period of a recurring
                  engagement, and runs it against that client&apos;s own approval
                  limits and thresholds instead of the firm-wide defaults.
                </p>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <DropZone
                label="Ledger"
                hint="Excel or CSV (.xlsx, .xls, .csv)"
                accept={[".xlsx", ".xls", ".csv"]}
                files={ledger}
                onFiles={setLedger}
                disabled={phase === "working"}
              />
              <DropZone
                label="Bank statement"
                hint="PDF, or the CSV/Excel export from internet banking"
                accept={[".pdf", ".csv", ".xlsx", ".xlsm", ".xls"]}
                files={bankStatement}
                onFiles={setBankStatement}
                disabled={phase === "working"}
              />
              <DropZone
                label="Invoices"
                hint="One or more PDFs or photos (.pdf, .png, .jpg, .jpeg, .webp)"
                accept={[".pdf", ".png", ".jpg", ".jpeg", ".webp"]}
                multiple
                files={invoices}
                onFiles={setInvoices}
                disabled={phase === "working"}
              />
              <DropZone
                label="Sales data"
                hint="Optional — Excel or CSV (.xlsx, .xls, .csv)"
                accept={[".xlsx", ".xls", ".csv"]}
                files={salesData}
                onFiles={setSalesData}
                disabled={phase === "working"}
              />
            </div>

            <p className="mt-2 text-[11px] leading-relaxed text-ink-400">
              Prefer the bank&apos;s CSV or Excel export where you have one: it is
              read by deterministic code rather than the vision model, so there
              is no reading uncertainty on the statement at all.
            </p>

            {error && (
              <div className="mt-4">
                <ErrorState title="Upload failed" message={error} onRetry={submit} />
              </div>
            )}

            <div className="mt-6 flex flex-wrap items-center gap-4">
              <Button size="lg" disabled={!ready || phase === "working"} onClick={submit}>
                {phase === "working" ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    Analyzing…
                  </>
                ) : (
                  "Start the audit"
                )}
              </Button>
              {!ready && phase === "idle" && (
                <p className="text-xs text-ink-400">
                  The button unlocks when the three required slots are filled. Sales data is optional.
                </p>
              )}
              {phase === "working" && (
                <p className="text-xs text-ink-400">
                  {FIXTURE_MODE
                    ? "Simulated pipeline (fixture mode)."
                    : "You can leave this page; the work continues on the server."}
                </p>
              )}
            </div>
          </div>

          {/* The analysis, as it actually happens */}
          <Card>
            <CardHeader>
              <CardTitle>
                {phase === "working" ? "Analyzing your data" : "What happens on upload"}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {phase === "working" && job && (
                <div className="mb-4">
                  <div className="mb-1 flex items-baseline justify-between text-xs">
                    <span className="min-w-0 truncate font-medium text-ink-900">
                      {job.step}
                    </span>
                    <span className="shrink-0 text-ink-400 tabular-nums">
                      {progress}%
                    </span>
                  </div>
                  <div
                    className="h-1.5 overflow-hidden rounded-full bg-slate-100"
                    role="progressbar"
                    aria-valuenow={progress}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label="Processing progress"
                  >
                    <div
                      className="h-full rounded-full bg-brand-700 transition-[width] duration-500"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>
              )}
              <ul className="space-y-4">
                {PIPELINE_STEPS.map((step) => (
                  <StepRow
                    key={step.label}
                    icon={step.icon}
                    label={step.label}
                    detail={step.detail}
                    state={
                      phase !== "working"
                        ? "pending"
                        : progress > step.at
                          ? "done"
                          : progress >= step.at
                            ? "running"
                            : "pending"
                    }
                  />
                ))}
              </ul>
              <p className="mt-4 border-t border-slate-100 pt-3 text-[11px] leading-relaxed text-ink-400">
                The AI only reads. Every match, sum, and flag comes from
                deterministic code, and every item still needs your explicit
                decision on the review screen.
              </p>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
