"use client";

/**
 * The evidence behind one demo row — the same trust moment the signed-in
 * evidence viewer gives an auditor, flattened into an expandable panel because
 * a public walkthrough has no slide-over chrome to hang it on.
 *
 * It shows the three sources side by side, what the deterministic matcher
 * concluded and why, the rules that flagged the row, and every value the AI
 * read with its confidence and the document, page or spreadsheet row it came
 * from. Nothing here is computed: each number was produced by the backend and
 * is displayed verbatim.
 *
 * The approve and reject controls are real in shape and fake in effect — they
 * move a value in React state and stop there. The panel says so out loud,
 * because "the human decides" is a promise about a recorded decision, and a
 * demo records nothing.
 */

import * as React from "react";
import { Check, FileSpreadsheet, FileText, Landmark, Receipt, X } from "lucide-react";
import type { ExtractedField, Provenance, ReviewItem } from "@/lib/types";
import { formatDate, formatMoney } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  ConfidenceBadge,
  DecisionBadge,
  MatchStrengthBadge,
  SeverityBadge,
} from "@/components/ui/badge";

/** "DOC-BNK-001 · page 2" or "DOC-LED-001 · row 14" — rule 3, made visible. */
function sourceLabel(source: Provenance): string {
  if (source.row_number != null) return `${source.document_id} · row ${source.row_number}`;
  if (source.page != null) return `${source.document_id} · page ${source.page}`;
  return source.document_id;
}

function SourceCard({
  title,
  icon: Icon,
  provenance,
  rows,
  missing,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  provenance?: Provenance;
  rows?: { label: string; value: string }[];
  /** Shown instead of the rows when the matcher found no such source. */
  missing?: string;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <p className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold tracking-wide text-ink-400 uppercase">
        <Icon className="h-3.5 w-3.5" aria-hidden />
        {title}
      </p>
      {missing ? (
        <p className="text-xs leading-relaxed text-ink-400">{missing}</p>
      ) : (
        <dl className="space-y-1">
          {rows?.map(({ label, value }) => (
            <div key={label} className="flex items-baseline justify-between gap-3">
              <dt className="text-[11px] text-ink-400">{label}</dt>
              <dd className="min-w-0 truncate text-right text-xs font-medium text-ink-900 tabular-nums">
                {value}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {provenance && (
        <p className="mt-2 border-t border-slate-100 pt-1.5 font-mono text-[10px] break-all text-ink-400">
          {sourceLabel(provenance)}
        </p>
      )}
    </div>
  );
}

function ReadingRow({ field }: { field: ExtractedField }) {
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-slate-200 bg-white px-3 py-2">
      <span className="text-[11px] font-medium text-ink-400">{field.field}</span>
      <span className="text-xs font-semibold text-ink-900 tabular-nums">
        {String(field.value)}
      </span>
      <ConfidenceBadge confidence={field.extraction_confidence} />
      <span className="ml-auto font-mono text-[10px] break-all text-ink-400">
        {sourceLabel(field.source)}
        {field.source.text_snippet ? ` · “${field.source.text_snippet}”` : ""}
      </span>
    </li>
  );
}

export function EvidencePanel({
  item,
  idPrefix,
  onDecide,
}: {
  item: ReviewItem;
  /**
   * The queue keeps a table and a card list in the DOM at once and hides one
   * with CSS, so an element id built from the item alone would appear twice.
   * The caller passes the layout it is rendering for.
   */
  idPrefix: string;
  /** Local-only. The caller moves the row in React state and nothing else. */
  onDecide: (decision: "approved" | "rejected", reason?: string) => void;
}) {
  const [rejecting, setRejecting] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const { ledger_entry: ledger, bank_transaction: bank, invoice, match } = item;

  return (
    <div className="space-y-4 border-t border-slate-200 bg-slate-50/70 px-3 py-4 sm:px-5">
      {/* 1. The three sources, side by side. */}
      <section>
        <h4 className="mb-2 text-[10px] font-semibold tracking-wide text-ink-600 uppercase">
          Where the numbers came from
        </h4>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <SourceCard
            title="Ledger row"
            icon={FileSpreadsheet}
            provenance={ledger.source}
            rows={[
              { label: "Date", value: formatDate(ledger.date) },
              { label: "Amount", value: formatMoney(ledger.amount, ledger.currency) },
              { label: "Party", value: ledger.party_name },
              ...(ledger.description
                ? [{ label: "Description", value: ledger.description }]
                : []),
              ...(ledger.account_code
                ? [{ label: "Account", value: ledger.account_code }]
                : []),
            ]}
          />
          <SourceCard
            title="Bank line"
            icon={Landmark}
            provenance={bank?.source}
            missing={
              bank
                ? undefined
                : "No bank payment lines up with this ledger entry anywhere in the uploaded statement."
            }
            rows={
              bank
                ? [
                    { label: "Date", value: formatDate(bank.date) },
                    { label: "Amount", value: formatMoney(bank.amount, bank.currency) },
                    { label: "Narration", value: bank.description },
                    ...(bank.balance != null
                      ? [
                          {
                            label: "Balance",
                            value: formatMoney(bank.balance, bank.currency),
                          },
                        ]
                      : []),
                  ]
                : undefined
            }
          />
          <SourceCard
            title="Invoice"
            icon={Receipt}
            provenance={invoice?.source}
            missing={
              invoice
                ? undefined
                : "No invoice was uploaded for this entry, so there is nothing to compare the ledger against."
            }
            rows={
              invoice
                ? [
                    { label: "Number", value: invoice.invoice_number },
                    { label: "Date", value: formatDate(invoice.date) },
                    {
                      label: "Amount",
                      value: formatMoney(invoice.amount, invoice.currency),
                    },
                    { label: "Party", value: invoice.party_name },
                  ]
                : undefined
            }
          />
        </div>
      </section>

      {/* 2. The matcher's verdict, worded by the backend. */}
      <section className="rounded-md border border-slate-200 bg-white p-3">
        <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
          <p className="text-[10px] font-semibold tracking-wide text-ink-400 uppercase">
            Why the matcher says this
          </p>
          <MatchStrengthBadge strength={match.match_strength} />
        </div>
        <p className="text-xs leading-relaxed text-ink-900">{match.reason}</p>
        <p className="mt-1.5 font-mono text-[10px] break-all text-ink-400">
          rule: {match.rule_id} (deterministic Python, no AI involved)
        </p>
      </section>

      {/* 3. What the rules engine flagged. */}
      {item.flags.length > 0 && (
        <section>
          <h4 className="mb-2 text-[10px] font-semibold tracking-wide text-ink-600 uppercase">
            Flagged for review ({item.flags.length})
          </h4>
          <ul className="space-y-2">
            {item.flags.map((flag) => (
              <li
                key={flag.flag_id}
                className="rounded-md border border-purple-200 bg-purple-50/60 p-3"
              >
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <SeverityBadge severity={flag.severity} />
                  <span className="font-mono text-[10px] text-ink-400">{flag.rule_id}</span>
                </div>
                <p className="text-xs leading-relaxed text-ink-900">{flag.explanation}</p>
                {flag.related_row_ids.length > 0 && (
                  <p className="mt-1 text-[10px] text-ink-400">
                    Also involves: {flag.related_row_ids.join(", ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* 4. The AI's own readings, each with a confidence and a location. */}
      <section>
        <h4 className="mb-2 text-[10px] font-semibold tracking-wide text-ink-600 uppercase">
          What the AI read, and how sure it was
        </h4>
        <ul className="space-y-1.5">
          {item.evidence.map((field, index) => (
            <ReadingRow key={`${field.field}-${index}`} field={field} />
          ))}
        </ul>
        <p className="mt-1.5 text-[11px] text-ink-400">
          In the product these coordinates draw a highlight on the real page image, so you
          can see the figure the model read before you accept it.
        </p>
      </section>

      {/* 5. The decision. Local only, and the panel says so. */}
      <section className="rounded-md border border-slate-200 bg-white p-3">
        {item.decision === "pending" ? (
          rejecting ? (
            <div>
              <label
                htmlFor={`${idPrefix}-reject-reason-${item.review_item_id}`}
                className="text-xs font-medium text-ink-900"
              >
                Why is this item rejected?
              </label>
              <p className="mt-0.5 mb-2 text-[11px] text-ink-400">
                The product requires a reason and records it verbatim in the immutable
                audit trail. In this demo it is only kept in the page.
              </p>
              <textarea
                id={`${idPrefix}-reject-reason-${item.review_item_id}`}
                autoFocus
                rows={2}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-ink-900 focus:border-brand-600 focus:ring-1 focus:ring-brand-600 focus:outline-none"
              />
              <div className="mt-2 flex flex-wrap justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setRejecting(false)}>
                  Cancel
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  disabled={!reason.trim()}
                  onClick={() => {
                    onDecide("rejected", reason.trim());
                    setRejecting(false);
                    setReason("");
                  }}
                >
                  Reject item
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="success"
                onClick={() => onDecide("approved")}
                aria-label={`Approve ${item.review_item_id} in the demo`}
              >
                <Check className="h-3.5 w-3.5" aria-hidden />
                Approve
              </Button>
              <Button
                size="sm"
                variant="danger"
                onClick={() => setRejecting(true)}
                aria-label={`Reject ${item.review_item_id} in the demo`}
              >
                <X className="h-3.5 w-3.5" aria-hidden />
                Reject
              </Button>
              <p className="text-[11px] text-ink-400">
                Demo only: decisions stay in this page and are never saved.
              </p>
            </div>
          )
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <DecisionBadge decision={item.decision} />
            <p className="text-[11px] text-ink-400">
              {item.rejection_reason
                ? `Reason recorded: “${item.rejection_reason}”`
                : "Recorded against the auditor who clicked it, with a timestamp."}
            </p>
            <span className="ml-auto flex items-center gap-1.5 text-[11px] text-ink-400">
              <FileText className="h-3 w-3" aria-hidden />
              Nothing was saved — this is sample data.
            </span>
          </div>
        )}
      </section>
    </div>
  );
}
