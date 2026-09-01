"use client";

/**
 * "What the AI did, and what it did not" — the panel that makes the product
 * boundary concrete while the visitor still has the review queue fresh in mind.
 *
 * It exists because the honest version of this product is also the sellable
 * one: an auditor who is told the machine decides will not trust it, and one
 * who is told the machine only reads and the arithmetic is deterministic code
 * will. Each line below maps to one of the seven reliability rules in
 * CLAUDE.md, and to something the visitor has just seen on the other two tabs.
 *
 * Never soften this into "automatic auditing" or "fraud detection". The
 * product flags items that need review.
 */

import * as React from "react";
import { Ban, Check, Scale } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

/** The positioning line, verbatim from CLAUDE.md. Do not paraphrase it. */
const POSITIONING =
  "Tarazu reconciles your books, flags what needs attention, and explains it in plain language. The AI assists, the human decides.";

const DID: { title: string; body: string }[] = [
  {
    title: "Read the documents",
    body: "A vision model read the bank statement PDF and the invoice images and turned them into structured rows. That is the whole of its job on this case.",
  },
  {
    title: "Scored its own certainty",
    body: "Every value it read carries high, medium or low confidence. The blurred invoice total on Sialkot Metal Works came back low, and the queue says so in its own column.",
  },
  {
    title: "Recorded where each number sits",
    body: "Document, page and position for a PDF; the row number for a spreadsheet. In the product the evidence viewer draws that box on the real page.",
  },
  {
    title: "Explained the case in plain language",
    body: "The assistant words answers in English or Urdu, but only over figures the deterministic code already computed, and only from your uploaded files.",
  },
];

const DID_NOT: { title: string; body: string }[] = [
  {
    title: "Compute a single number",
    body: "Every sum, comparison, match and percentage on these two tabs came from deterministic Python (pandas). No model output can move a figure.",
  },
  {
    title: "Match anything",
    body: "Ledger to bank line to invoice is rule-based code you can read and re-run. The reason string under each row names the rule that produced it.",
  },
  {
    title: "Decide anything",
    body: "There is no auto-approval path anywhere in the product. Ten rows in this sample, ten explicit human decisions, each written to an append-only audit trail.",
  },
  {
    title: "Learn from the client data",
    body: "Documents go to the model for that one inference call and nowhere else. No training, no fine-tuning, no feedback loop.",
  },
];

function Column({
  heading,
  tone,
  entries,
}: {
  heading: string;
  tone: "did" | "did-not";
  entries: { title: string; body: string }[];
}) {
  const did = tone === "did";
  const Icon = did ? Check : Ban;
  return (
    <Card className={did ? "border-emerald-200" : "border-slate-300"}>
      <CardContent className="px-4 py-4 sm:px-5">
        <h4
          className={
            did
              ? "mb-3 flex items-center gap-2 text-sm font-bold text-emerald-800"
              : "mb-3 flex items-center gap-2 text-sm font-bold text-ink-900"
          }
        >
          <span
            className={
              did
                ? "flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-700"
                : "flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-200 text-ink-600"
            }
          >
            <Icon className="h-3.5 w-3.5" aria-hidden />
          </span>
          {heading}
        </h4>
        <ul className="space-y-3">
          {entries.map((entry) => (
            <li key={entry.title}>
              <p className="text-sm font-semibold text-ink-900">{entry.title}</p>
              <p className="mt-0.5 text-xs leading-relaxed text-ink-600">{entry.body}</p>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export function DemoBoundary() {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-bold text-ink-900">
          What the AI did, and what it did not
        </h3>
        <p className="mt-1 max-w-3xl text-sm text-ink-600">
          Everything on the other two tabs was produced by one of two things, and it
          matters enormously which. Here is the split, for this exact sample case.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Column heading="The AI did" tone="did" entries={DID} />
        <Column heading="The AI did not" tone="did-not" entries={DID_NOT} />
      </div>

      <Card className="border-brand-200 bg-brand-50/60">
        <CardContent className="flex items-start gap-3 px-4 py-4 sm:px-5">
          <Scale className="mt-0.5 h-5 w-5 shrink-0 text-brand-700" aria-hidden />
          <div>
            <p className="text-sm leading-relaxed font-semibold text-brand-900">
              {POSITIONING}
            </p>
            <p className="mt-1.5 text-xs leading-relaxed text-ink-600">
              Tarazu is an audit layer over the records a client already keeps: never a
              book-keeping system, never a verdict. It flags items that need review and
              hands you the evidence to judge them by.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
