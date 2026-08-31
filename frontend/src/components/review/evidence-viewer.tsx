"use client";

/**
 * The evidence viewer: the trust moment of the product. Left panel — the
 * ledger entry beside what the documents say, differing fields highlighted.
 * Right panel — where each value physically sits on its source page, drawn
 * from the provenance the extraction produced (page + normalised bbox, or a
 * text snippet when the model returned no usable box), over the real page
 * image the backend renders (`GET /v1/documents/{id}/pages/{page}`), or over
 * a schematic outline when it cannot serve one.
 *
 * Nothing here computes anything: every value, match, and flag on screen came
 * from the backend. Highlighting which displayed values differ is presentation
 * only — the mismatch itself was found by the deterministic matcher and is
 * stated in `match.reason`.
 */

import * as React from "react";
import Link from "next/link";
import { ExternalLink, FileText, History, Loader2, X } from "lucide-react";
import { getReviewItemAudit } from "@/lib/api";
import type { AuditRecord, ExtractedField, Provenance, ReviewItem } from "@/lib/types";
import { formatDate, formatMoney, formatTimestamp } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ConfidenceBadge, SeverityBadge, StatusBadge, MatchStrengthBadge } from "@/components/ui/badge";
import { DocumentPage } from "@/components/documents/schematic-page";

// ---------------------------------------------------------------------------
// Right panel: the source page with the provenance highlight
// ---------------------------------------------------------------------------

function DocumentPane({ provenance }: { provenance: Provenance }) {
  const { bbox, text_snippet, page, row_number, document_id } = provenance;
  const [mode, setMode] = React.useState<"image" | "schematic" | null>(null);

  if (row_number != null) {
    // Spreadsheet provenance: the ledger, read by pandas with no AI involved.
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 rounded-md border border-slate-200 bg-slate-50 p-6 text-center">
        <FileText className="h-8 w-8 text-ink-400" aria-hidden />
        <p className="text-sm font-medium text-ink-900">
          {document_id} · spreadsheet row {row_number}
        </p>
        <p className="max-w-xs text-xs text-ink-400">
          Read directly by pandas from the ledger file. No AI touched this value,
          so there is no page region to highlight.
        </p>
      </div>
    );
  }

  const pageNumber = page ?? 1;
  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-ink-600">
          {document_id} · page {pageNumber}
        </p>
        <Link
          href={`/documents?doc=${encodeURIComponent(document_id)}&page=${pageNumber}`}
          className="flex items-center gap-1 text-[11px] font-medium text-brand-700 hover:underline"
        >
          Open in Documents <ExternalLink className="h-3 w-3" aria-hidden />
        </Link>
      </div>
      {/* bbox is [x0,y0,x1,y1] normalised 0..1, origin top-left, on the real page. */}
      <DocumentPage
        documentId={document_id}
        page={pageNumber}
        highlights={[{ id: "evidence", bbox, snippet: text_snippet, label: "evidence" }]}
        activeId="evidence"
        onRendered={setMode}
      />
      {text_snippet && bbox && (
        <p className="mt-2 text-xs text-ink-600">
          Highlighted text: <span className="rounded bg-amber-100 px-1 py-0.5 font-medium">{text_snippet}</span>
        </p>
      )}
      {mode === "schematic" && (
        <p className="mt-1 text-[11px] text-ink-400">
          Schematic render: the page image is not available from the backend for
          this document, so the highlight is drawn at its coordinates on an outline.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Left panel helpers
// ---------------------------------------------------------------------------

function ComparisonRow({
  label,
  values,
  highlight,
}: {
  label: string;
  values: (string | null)[];
  /** Presentation only: marks values that read differently across sources. */
  highlight: boolean;
}) {
  return (
    <tr className="border-b border-slate-100 last:border-0">
      <td className="py-1.5 pr-3 text-xs font-medium text-ink-400">{label}</td>
      {values.map((value, index) => (
        <td
          key={index}
          className={cn(
            "py-1.5 pr-3 text-xs text-ink-900 tabular-nums",
            highlight && value != null && "rounded bg-amber-100 font-semibold",
          )}
        >
          {value ?? <span className="text-ink-400">-</span>}
        </td>
      ))}
    </tr>
  );
}

// ---------------------------------------------------------------------------
// The slide-over
// ---------------------------------------------------------------------------

export function EvidenceViewer({
  item,
  onClose,
}: {
  item: ReviewItem;
  onClose: () => void;
}) {
  const [selectedEvidence, setSelectedEvidence] = React.useState<ExtractedField | null>(
    item.evidence.find((e) => e.source.page != null) ?? item.evidence[0] ?? null,
  );
  const [audit, setAudit] = React.useState<AuditRecord[] | null>(null);
  const [auditError, setAuditError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    getReviewItemAudit(item.review_item_id)
      .then((records) => !cancelled && setAudit(records))
      .catch(() => !cancelled && setAuditError("Could not load the audit history."));
    return () => {
      cancelled = true;
    };
  }, [item.review_item_id]);

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const { ledger_entry: ledger, bank_transaction: bank, invoice, match } = item;

  const sourceHeaders = ["Ledger", bank ? "Bank statement" : null, invoice ? "Invoice" : null]
    .filter(Boolean) as string[];

  // Presentation-only difference marks; the matcher already found and worded
  // any real mismatch in match.reason.
  const dates = [ledger.date, bank?.date ?? null, invoice?.date ?? null].filter(
    (_, i) => i === 0 || (i === 1 ? !!bank : !!invoice),
  );
  const amounts = [ledger.amount, bank?.amount ?? null, invoice?.amount ?? null].filter(
    (_, i) => i === 0 || (i === 1 ? !!bank : !!invoice),
  );
  const datesDiffer = new Set(dates.filter((d) => d != null)).size > 1;
  const amountsDiffer = new Set(amounts.filter((a) => a != null)).size > 1;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-900/40"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="flex h-full w-[880px] max-w-[92vw] flex-col overflow-y-auto border-l border-slate-200 bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <h2 className="text-sm font-bold text-ink-900">
              Evidence: {ledger.party_name}
            </h2>
            <p className="mt-0.5 text-xs text-ink-400">
              {item.review_item_id} · {formatDate(ledger.date)} ·{" "}
              {formatMoney(ledger.amount, ledger.currency)}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={match.status} />
            <button
              onClick={onClose}
              className="rounded p-1.5 text-ink-400 hover:bg-slate-100 hover:text-ink-600"
              aria-label="Close evidence viewer"
            >
              <X className="h-4.5 w-4.5" />
            </button>
          </div>
        </div>

        <div className="grid flex-1 grid-cols-2 gap-6 p-6">
          {/* Left: the comparison */}
          <div className="space-y-5">
            <section>
              <h3 className="mb-2 text-xs font-semibold tracking-wide text-ink-600 uppercase">
                Ledger vs documents
              </h3>
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="w-24" />
                    {sourceHeaders.map((header) => (
                      <th
                        key={header}
                        className="pb-1.5 pr-3 text-left text-[10px] font-semibold tracking-wide text-ink-400 uppercase"
                      >
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <ComparisonRow
                    label="Date"
                    highlight={datesDiffer}
                    values={[
                      formatDate(ledger.date),
                      ...(bank ? [formatDate(bank.date)] : []),
                      ...(invoice ? [formatDate(invoice.date)] : []),
                    ]}
                  />
                  <ComparisonRow
                    label="Amount"
                    highlight={amountsDiffer}
                    values={[
                      formatMoney(ledger.amount, ledger.currency),
                      ...(bank ? [formatMoney(bank.amount, bank.currency)] : []),
                      ...(invoice ? [formatMoney(invoice.amount, invoice.currency)] : []),
                    ]}
                  />
                  <ComparisonRow
                    label="Party"
                    highlight={false}
                    values={[
                      ledger.party_name,
                      ...(bank ? [bank.description] : []),
                      ...(invoice ? [invoice.party_name] : []),
                    ]}
                  />
                  {invoice && (
                    <ComparisonRow
                      label="Invoice #"
                      highlight={false}
                      values={[ledger.description ?? null, null, invoice.invoice_number].slice(
                        0,
                        sourceHeaders.length + 1,
                      )}
                    />
                  )}
                </tbody>
              </table>
            </section>

            <section className="rounded-md border border-slate-200 bg-slate-50 p-3">
              <div className="mb-1.5 flex items-center justify-between">
                <p className="text-[10px] font-semibold tracking-wide text-ink-400 uppercase">
                  Why the matcher says this
                </p>
                <MatchStrengthBadge strength={match.match_strength} />
              </div>
              <p className="text-xs leading-relaxed text-ink-900">{match.reason}</p>
              <p className="mt-1.5 font-mono text-[10px] text-ink-400">
                rule: {match.rule_id} (deterministic, no AI involved)
              </p>
            </section>

            {item.flags.length > 0 && (
              <section>
                <h3 className="mb-2 text-xs font-semibold tracking-wide text-ink-600 uppercase">
                  Red flags ({item.flags.length})
                </h3>
                <ul className="space-y-2">
                  {item.flags.map((flag) => (
                    <li
                      key={flag.flag_id}
                      className="rounded-md border border-purple-200 bg-purple-50/60 p-3"
                    >
                      <div className="mb-1 flex items-center gap-2">
                        <SeverityBadge severity={flag.severity} />
                        <span className="font-mono text-[10px] text-ink-400">
                          {flag.rule_id}
                        </span>
                      </div>
                      <p className="text-xs leading-relaxed text-ink-900">
                        {flag.explanation}
                      </p>
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

            <section>
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-ink-600 uppercase">
                <History className="h-3.5 w-3.5" aria-hidden /> History
              </h3>
              {auditError ? (
                <p className="text-xs text-rose-600">{auditError}</p>
              ) : audit === null ? (
                <p className="flex items-center gap-1.5 text-xs text-ink-400">
                  <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> Loading…
                </p>
              ) : audit.length === 0 ? (
                <p className="text-xs text-ink-400">
                  No recorded actions on this item yet.
                </p>
              ) : (
                <ul className="space-y-1.5">
                  {audit.map((record) => (
                    <li key={record.audit_id} className="text-xs text-ink-600">
                      <span className="font-medium text-ink-900">
                        {record.action.replace(/_/g, " ")}
                      </span>{" "}
                      by {record.actor_id} · {formatTimestamp(record.occurred_at)}
                      {record.detail && (
                        <span className="block text-ink-400">“{record.detail}”</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          {/* Right: the source document */}
          <div className="flex flex-col">
            <h3 className="mb-2 text-xs font-semibold tracking-wide text-ink-600 uppercase">
              Source document
            </h3>
            {item.evidence.length > 1 && (
              <div className="mb-3 flex flex-wrap gap-1.5">
                {item.evidence.map((field, index) => (
                  <button
                    key={index}
                    onClick={() => setSelectedEvidence(field)}
                    className={cn(
                      "rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
                      selectedEvidence === field
                        ? "border-brand-800 bg-brand-800 text-white"
                        : "border-slate-300 bg-white text-ink-600 hover:border-brand-600",
                    )}
                  >
                    {field.field} · {field.source.document_id}
                  </button>
                ))}
              </div>
            )}
            {selectedEvidence ? (
              <>
                <div className="mb-2 flex items-center gap-2">
                  <span className="text-xs text-ink-600">
                    Read as{" "}
                    <span className="font-semibold text-ink-900 tabular-nums">
                      {String(selectedEvidence.value)}
                    </span>
                  </span>
                  <ConfidenceBadge confidence={selectedEvidence.extraction_confidence} />
                </div>
                <div className="min-h-0 flex-1">
                  <DocumentPane provenance={selectedEvidence.source} />
                </div>
              </>
            ) : (
              <p className="text-xs text-ink-400">No extracted evidence on this item.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
