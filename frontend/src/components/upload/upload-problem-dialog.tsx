"use client";

/**
 * The guide shown when an upload cannot be used.
 *
 * The backend refuses a file with a `ReadProblem`: which document, what it
 * held, what it lacked, and what to do. This dialog lays that out in the order
 * a person needs it — what happened, what you gave us, what is missing, how to
 * fix it — and hands them straight to the slot to replace. It shows nothing
 * the backend did not say: no column list is inferred here, and no number is
 * computed.
 *
 * A failure with no guide (a job that broke for an internal reason) still gets
 * the same dialog, with the message alone and the general advice.
 */

import * as React from "react";
import { AlertTriangle, FileWarning, ListChecks, Replace, Wrench } from "lucide-react";
import type { ReadProblem, UploadSlot } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";

/** How each slot is named in a sentence and on a button. */
export const SLOT_LABELS: Record<UploadSlot, string> = {
  ledger: "ledger",
  bank_statement: "bank statement",
  invoice: "invoice",
  sales_data: "sales export",
};

export interface UploadFailure {
  /** The problem as the backend gave it, when it gave one. */
  problem: ReadProblem | null;
  /** Always present: the sentence to show when there is no problem. */
  message: string;
  /** The heading when there is no problem. */
  title?: string;
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-4">
      <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-600">
        <Icon className="h-3.5 w-3.5 text-ink-400" aria-hidden />
        {title}
      </h3>
      <div className="mt-2">{children}</div>
    </section>
  );
}

export function UploadProblemDialog({
  open,
  failure,
  onClose,
  onReplace,
}: {
  open: boolean;
  failure: UploadFailure | null;
  onClose: () => void;
  /** Clears the offending slot so a new file can be chosen. Optional. */
  onReplace?: (slot: UploadSlot) => void;
}) {
  if (!failure) return null;
  const problem = failure.problem;
  const title = problem?.title ?? failure.title ?? "Upload failed";
  const message = problem?.message ?? failure.message;
  const slot = problem?.document ?? null;
  const slotLabel = slot ? SLOT_LABELS[slot] : null;
  const guidance = problem?.guidance?.length
    ? problem.guidance
    : [
        "Check the files you chose, then try the upload again.",
        "If the same message comes back, tell your administrator what you uploaded and when.",
      ];

  return (
    <Dialog open={open} onClose={onClose} title={title} className="max-w-xl">
      <div className="flex items-start gap-3 rounded-lg border border-rose-200 bg-rose-50/70 px-3 py-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" aria-hidden />
        <p className="text-sm leading-relaxed text-rose-900">{message}</p>
      </div>

      {(problem?.filename || (problem?.found_columns?.length ?? 0) > 0) && (
        <Section icon={FileWarning} title="What you uploaded">
          {problem?.filename && (
            <p className="text-sm text-ink-900">
              <span className="font-medium">{problem.filename}</span>
              {slotLabel && <span className="text-ink-600"> as the {slotLabel}</span>}
            </p>
          )}
          {problem && problem.found_columns.length > 0 && (
            <div className="mt-2">
              <p className="text-xs text-ink-600">Columns Tarazu found in its header row:</p>
              <ul className="mt-1 flex flex-wrap gap-1.5">
                {problem.found_columns.map((column, index) => (
                  <li
                    key={`${column}-${index}`}
                    className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-[11px] text-ink-900"
                  >
                    {column}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Section>
      )}

      {problem && problem.missing.length > 0 && (
        <Section icon={ListChecks} title="What is missing">
          <ul className="space-y-2.5">
            {problem.missing.map((field) => (
              <li
                key={field.name}
                className="rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2"
              >
                <p className="text-sm font-semibold text-ink-900">{field.label}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-ink-600">{field.why}</p>
                {field.accepted_headers.length > 0 && (
                  <p className="mt-1.5 text-xs text-ink-600">
                    <span className="font-medium text-ink-900">Header names that work: </span>
                    {field.accepted_headers.join(" · ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section icon={Wrench} title="How to fix it">
        <ol className="list-decimal space-y-1.5 pl-5 text-sm leading-relaxed text-ink-900">
          {guidance.map((step, index) => (
            <li key={index}>{step}</li>
          ))}
        </ol>
      </Section>

      <div className="mt-5 flex flex-col-reverse gap-2 border-t border-slate-100 pt-4 sm:flex-row sm:justify-end">
        <Button variant="outline" onClick={onClose}>
          Close
        </Button>
        {slot && onReplace && (
          <Button onClick={() => onReplace(slot)}>
            <Replace className="h-4 w-4" aria-hidden />
            Replace the {slotLabel}
          </Button>
        )}
      </div>
    </Dialog>
  );
}

/**
 * The one-line summary kept on screen after the dialog closes, so the person
 * still sees what went wrong while they pick a new file.
 */
export function UploadFailureNotice({
  failure,
  onDetails,
}: {
  failure: UploadFailure;
  onDetails: () => void;
}) {
  const title = failure.problem?.title ?? failure.title ?? "Upload failed";
  return (
    <div
      role="alert"
      className="flex flex-col gap-2 rounded-lg border border-rose-200 bg-rose-50/70 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex min-w-0 items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" aria-hidden />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-rose-900">{title}</p>
          <p className="line-clamp-2 text-xs text-rose-800">
            {failure.problem?.message ?? failure.message}
          </p>
        </div>
      </div>
      <Button variant="outline" size="sm" className="shrink-0 self-start sm:self-auto" onClick={onDetails}>
        Show the guide
      </Button>
    </div>
  );
}
