"use client";

/**
 * Upload — three inputs open a case, and the analysis is visible while it
 * runs: upload → AI extraction → deterministic matching → red-flag rules →
 * Benford. The step panel is presentation (the backend pipeline runs all five
 * synchronously inside one request); the counts on the result screen are the
 * backend's own numbers.
 */

import * as React from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  FileSearch,
  Files,
  FlaskConical,
  GitCompareArrows,
  Loader2,
  ScanText,
  UploadCloud,
} from "lucide-react";
import { uploadDocuments, setActiveCaseId, ApiError, FIXTURE_MODE } from "@/lib/api";
import type { UploadResponse } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/states";
import { DropZone } from "@/components/upload/drop-zone";
import { cn } from "@/lib/utils";

type Phase = "idle" | "uploading" | "done";

const PIPELINE_STEPS = [
  {
    icon: UploadCloud,
    label: "Uploading documents",
    detail: "Bank statement, ledger, and invoices stored against the new case.",
  },
  {
    icon: ScanText,
    label: "AI extraction",
    detail:
      "The vision model reads every page. Each value carries a confidence level and its page-and-position source: no provenance, no value.",
  },
  {
    icon: GitCompareArrows,
    label: "Deterministic matching",
    detail:
      "Pure pandas, three tiers: exact amount and date, then a ±3-day window, then tolerance. No AI touches a number.",
  },
  {
    icon: FileSearch,
    label: "Red-flag rules",
    detail:
      "Round numbers · duplicates · weekend entries · near-limit amounts · structuring · sequence gaps.",
  },
  {
    icon: FlaskConical,
    label: "Benford analysis",
    detail: "First-digit distribution of the amounts against the expected curve.",
  },
];

/** Cadence of the step display while the request is in flight. */
const STEP_ADVANCE_MS = 1100;

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
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
      <p className="text-2xl font-bold text-ink-900 tabular-nums">{value}</p>
      <p className="text-xs text-ink-400">{label}</p>
    </div>
  );
}

export default function UploadPage() {
  const [ledger, setLedger] = React.useState<File[]>([]);
  const [bankStatement, setBankStatement] = React.useState<File[]>([]);
  const [invoices, setInvoices] = React.useState<File[]>([]);
  const [phase, setPhase] = React.useState<Phase>("idle");
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<UploadResponse | null>(null);
  const [activeStep, setActiveStep] = React.useState(0);
  const timerRef = React.useRef<number | null>(null);

  React.useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
    },
    [],
  );

  const ready =
    ledger.length === 1 && bankStatement.length === 1 && invoices.length >= 1;

  const submit = async () => {
    if (!ready || phase === "uploading") return;
    setPhase("uploading");
    setError(null);
    setActiveStep(0);
    // Walk the steps forward while the request runs; hold on the last one
    // until the backend answers, then mark everything complete.
    timerRef.current = window.setInterval(() => {
      setActiveStep((current) => Math.min(current + 1, PIPELINE_STEPS.length - 1));
    }, STEP_ADVANCE_MS);
    try {
      const response = await uploadDocuments({
        bankStatement: bankStatement[0],
        ledger: ledger[0],
        invoices,
      });
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
      setActiveStep(PIPELINE_STEPS.length);
      setResult(response);
      // The new case becomes the one the whole workspace is about.
      setActiveCaseId(response.case_id);
      window.setTimeout(() => setPhase("done"), 500);
    } catch (caught) {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Upload failed. Check the files and try again.",
      );
      setPhase("idle");
    }
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-ink-900">Upload documents</h1>
        <p className="mt-1 text-sm text-ink-600">
          Three inputs open a case: the client&apos;s ledger, the bank statement,
          and the invoices. The AI reads them; deterministic code does every
          match and every sum; you decide every item.
        </p>
      </div>

      {phase === "done" && result ? (
        <Card>
          <CardHeader>
            <CardTitle>Case {result.case_id} is ready</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-ink-600">{result.message}</p>

            <div className="mt-4 grid grid-cols-3 gap-3">
              <ResultStat label="Documents received" value={result.documents.length} />
              <ResultStat label="Review items created" value={result.review_item_count} />
              <ResultStat
                label="Escalated to you"
                value={result.needs_human_review_count}
              />
            </div>

            <ul className="mt-4 space-y-1 text-xs text-ink-600">
              {result.documents.map((doc) => (
                <li key={doc.document_id} className="flex items-center gap-2">
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-ink-600">
                    {doc.document_id}
                  </span>
                  {doc.filename}
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
            <div className="mt-4 flex gap-3">
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
        <div className="grid grid-cols-[minmax(0,1fr)_22rem] items-start gap-5">
          <div>
            <div className="grid grid-cols-3 gap-4">
              <DropZone
                label="Ledger"
                hint="Excel or CSV (.xlsx, .xls, .csv)"
                accept={[".xlsx", ".xls", ".csv"]}
                files={ledger}
                onFiles={setLedger}
                disabled={phase === "uploading"}
              />
              <DropZone
                label="Bank statement"
                hint="PDF only (.pdf)"
                accept={[".pdf"]}
                files={bankStatement}
                onFiles={setBankStatement}
                disabled={phase === "uploading"}
              />
              <DropZone
                label="Invoices"
                hint="One or more PDFs or photos (.pdf, .png, .jpg, .jpeg, .webp)"
                accept={[".pdf", ".png", ".jpg", ".jpeg", ".webp"]}
                multiple
                files={invoices}
                onFiles={setInvoices}
                disabled={phase === "uploading"}
              />
            </div>

            {error && (
              <div className="mt-4">
                <ErrorState title="Upload failed" message={error} onRetry={submit} />
              </div>
            )}

            <div className="mt-6 flex items-center gap-4">
              <Button size="lg" disabled={!ready || phase === "uploading"} onClick={submit}>
                {phase === "uploading" ? (
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
                  The button unlocks when all three slots are filled.
                </p>
              )}
              {phase === "uploading" && (
                <p className="text-xs text-ink-400">
                  {FIXTURE_MODE
                    ? "Simulated pipeline (fixture mode)."
                    : "The pipeline runs synchronously; a real statement takes tens of seconds."}
                </p>
              )}
            </div>
          </div>

          {/* The analysis, visible while it happens */}
          <Card>
            <CardHeader>
              <CardTitle>{phase === "uploading" ? "Analyzing your data" : "What happens on upload"}</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-4">
                {PIPELINE_STEPS.map((step, index) => (
                  <StepRow
                    key={step.label}
                    icon={step.icon}
                    label={step.label}
                    detail={step.detail}
                    state={
                      phase !== "uploading"
                        ? "pending"
                        : index < activeStep
                          ? "done"
                          : index === activeStep
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
