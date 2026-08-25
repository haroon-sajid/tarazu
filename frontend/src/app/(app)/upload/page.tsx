"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, Loader2 } from "lucide-react";
import { uploadDocuments, ApiError, FIXTURE_MODE } from "@/lib/api";
import type { UploadResponse } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/states";
import { DropZone } from "@/components/upload/drop-zone";

type Phase = "idle" | "uploading" | "done";

export default function UploadPage() {
  const [ledger, setLedger] = React.useState<File[]>([]);
  const [bankStatement, setBankStatement] = React.useState<File[]>([]);
  const [invoices, setInvoices] = React.useState<File[]>([]);
  const [phase, setPhase] = React.useState<Phase>("idle");
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<UploadResponse | null>(null);

  const ready =
    ledger.length === 1 && bankStatement.length === 1 && invoices.length >= 1;

  const submit = async () => {
    if (!ready || phase === "uploading") return;
    setPhase("uploading");
    setError(null);
    try {
      const response = await uploadDocuments({
        bankStatement: bankStatement[0],
        ledger: ledger[0],
        invoices,
      });
      setResult(response);
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

  return (
    <div className="mx-auto max-w-5xl">
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
            <ul className="mt-3 space-y-1 text-xs text-ink-600">
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
              <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 ring-1 ring-amber-200">
                {result.needs_human_review_count} document
                {result.needs_human_review_count > 1 ? "s" : ""} had the two AI
                reading passes disagree — those items are escalated to you.
              </p>
            )}
            <div className="mt-4">
              <Link href="/review">
                <Button>
                  Go to review <ArrowRight className="h-4 w-4" aria-hidden />
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      ) : (
        <>
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
                  Extracting, matching, flagging…
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
                  ? "Simulated pipeline — fixture mode."
                  : "The pipeline runs synchronously; a real statement takes tens of seconds."}
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
