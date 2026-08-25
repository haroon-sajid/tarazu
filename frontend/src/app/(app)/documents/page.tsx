"use client";

/**
 * Documents — the side-by-side audit workspace. Left: the case's source
 * documents. Middle: the selected document rendered with every extracted
 * value highlighted at its provenance coordinates. Right: what the AI read
 * from that document, field by field, each with its extraction confidence
 * and the review item it feeds.
 *
 * Everything on this screen is derived from the review items the backend
 * already serves — the provenance attached to each extracted value is the
 * contract's rule 3 (every number traces to its source) made visible.
 */

import * as React from "react";
import Link from "next/link";
import { ArrowRight, FileSpreadsheet, FileText, Files } from "lucide-react";
import { ApiError, getReviewItems } from "@/lib/api";
import type { Confidence, Provenance, ReviewDecision, ReviewItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { ConfidenceBadge, DecisionBadge } from "@/components/ui/badge";
import {
  SchematicPage,
  SchematicSheet,
  type PageHighlight,
} from "@/components/documents/schematic-page";

type DocumentKind = "bank_statement" | "invoice" | "ledger";

interface DocField {
  id: string;
  field: string;
  value: string;
  /** null when pandas read the value directly — no AI, no confidence. */
  confidence: Confidence | null;
  source: Provenance;
  reviewItemId: string;
  party: string;
  decision: ReviewDecision;
}

interface CaseDocument {
  id: string;
  kind: DocumentKind;
  fields: DocField[];
  pages: number[];
}

const KIND_LABEL: Record<DocumentKind, string> = {
  bank_statement: "Bank statement",
  invoice: "Invoice",
  ledger: "Ledger",
};

function formatValue(value: unknown): string {
  if (typeof value === "number") return value.toLocaleString("en-PK");
  if (value == null) return "-";
  return String(value);
}

/** Group every provenance in the queue by the document it points into. */
function collectDocuments(items: ReviewItem[]): CaseDocument[] {
  const kinds = new Map<string, DocumentKind>();
  const fields = new Map<string, DocField[]>();

  const push = (entry: DocField) => {
    const list = fields.get(entry.source.document_id) ?? [];
    // The same value can be referenced from several items; keep one per
    // (field, review item) so the table stays readable.
    if (!list.some((f) => f.field === entry.field && f.reviewItemId === entry.reviewItemId)) {
      list.push(entry);
    }
    fields.set(entry.source.document_id, list);
  };

  for (const item of items) {
    kinds.set(item.ledger_entry.source.document_id, "ledger");
    if (item.bank_transaction) {
      kinds.set(item.bank_transaction.source.document_id, "bank_statement");
    }
    if (item.invoice) kinds.set(item.invoice.source.document_id, "invoice");

    push({
      id: `${item.review_item_id}-ledger`,
      field: "ledger entry",
      value: `${item.ledger_entry.party_name} · ${formatValue(item.ledger_entry.amount)}`,
      confidence: null,
      source: item.ledger_entry.source,
      reviewItemId: item.review_item_id,
      party: item.ledger_entry.party_name,
      decision: item.decision,
    });
    item.evidence.forEach((evidence, index) => {
      push({
        id: `${item.review_item_id}-ev-${index}`,
        field: evidence.field,
        value: formatValue(evidence.value),
        confidence: evidence.extraction_confidence,
        source: evidence.source,
        reviewItemId: item.review_item_id,
        party: item.ledger_entry.party_name,
        decision: item.decision,
      });
    });
  }

  return Array.from(fields.entries())
    .map(([id, docFields]) => ({
      id,
      kind: kinds.get(id) ?? ("invoice" as DocumentKind),
      fields: docFields,
      pages: Array.from(
        new Set(docFields.map((f) => f.source.page).filter((p): p is number => p != null)),
      ).sort((a, b) => a - b),
    }))
    .sort((a, b) => a.id.localeCompare(b.id));
}

export default function DocumentsPage() {
  const [items, setItems] = React.useState<ReviewItem[] | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [selectedDocId, setSelectedDocId] = React.useState<string | null>(null);
  const [selectedFieldId, setSelectedFieldId] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    setLoadError(null);
    setItems(null);
    getReviewItems()
      .then((response) => setItems(response.items))
      .catch((caught) => {
        if (caught instanceof ApiError && caught.status === 404) {
          setItems([]);
          return;
        }
        setLoadError(
          caught instanceof ApiError ? caught.message : "Could not load the documents.",
        );
      });
  }, []);

  React.useEffect(load, [load]);

  const documents = React.useMemo(() => (items ? collectDocuments(items) : []), [items]);
  const selected =
    documents.find((doc) => doc.id === selectedDocId) ?? documents[0] ?? null;
  const selectedField =
    selected?.fields.find((f) => f.id === selectedFieldId) ?? selected?.fields[0] ?? null;
  const currentPage = selectedField?.source.page ?? selected?.pages[0] ?? 1;

  const pageHighlights: PageHighlight[] = selected
    ? selected.fields
        .filter((f) => f.source.page === currentPage && f.source.row_number == null)
        .map((f) => ({
          id: f.id,
          bbox: f.source.bbox,
          snippet: f.source.text_snippet,
          label: `${f.field}: ${f.value}`,
        }))
    : [];

  return (
    <div>
      <div className="mb-5 flex items-end justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink-900">Documents</h1>
          <p className="mt-1 text-sm text-ink-600">
            Audit each source side by side: the document on the left, what the
            AI read from it on the right. Every value sits exactly where the
            extraction found it.
          </p>
        </div>
        {items && items.length > 0 && (
          <p className="text-xs text-ink-400">
            {documents.length} documents ·{" "}
            {documents.reduce((sum, doc) => sum + doc.fields.length, 0)} traced values
          </p>
        )}
      </div>

      {loadError ? (
        <ErrorState message={loadError} onRetry={load} />
      ) : items === null ? (
        <div className="grid grid-cols-[15rem_minmax(0,1fr)_minmax(0,1fr)] gap-5">
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          title="No documents yet"
          message="Upload a bank statement, invoices, and a ledger to open a case."
          action={
            <Link href="/upload" className="text-sm font-medium text-brand-700 hover:underline">
              Go to upload →
            </Link>
          }
        />
      ) : (
        <div className="grid grid-cols-[15rem_minmax(0,1fr)_minmax(0,1fr)] items-start gap-5">
          {/* Document list */}
          <nav className="space-y-1.5" aria-label="Case documents">
            {documents.map((doc) => {
              const Icon = doc.kind === "ledger" ? FileSpreadsheet : FileText;
              const active = doc.id === selected?.id;
              return (
                <button
                  key={doc.id}
                  onClick={() => {
                    setSelectedDocId(doc.id);
                    setSelectedFieldId(null);
                  }}
                  className={cn(
                    "flex w-full items-start gap-2.5 rounded-lg border px-3 py-2.5 text-left transition-colors",
                    active
                      ? "border-brand-800 bg-brand-50/60"
                      : "border-slate-200 bg-white hover:border-brand-600",
                  )}
                >
                  <Icon
                    className={cn(
                      "mt-0.5 h-4 w-4 shrink-0",
                      active ? "text-brand-800" : "text-ink-400",
                    )}
                    aria-hidden
                  />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-ink-900">
                      {doc.id}
                    </span>
                    <span className="block text-[11px] text-ink-400">
                      {KIND_LABEL[doc.kind]} · {doc.fields.length} value
                      {doc.fields.length === 1 ? "" : "s"}
                      {doc.pages.length > 0 &&
                        ` · ${doc.pages.length} page${doc.pages.length === 1 ? "" : "s"}`}
                    </span>
                  </span>
                </button>
              );
            })}
          </nav>

          {/* Source document */}
          {selected && (
            <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-600">
                  <Files className="h-3.5 w-3.5" aria-hidden /> Source document
                </h2>
                {selected.kind !== "ledger" && selected.pages.length > 1 && (
                  <span className="text-[11px] text-ink-400">Page {currentPage}</span>
                )}
              </div>
              {selected.kind === "ledger" ? (
                <SchematicSheet
                  rows={selected.fields
                    .filter((f) => f.source.row_number != null)
                    .map((f) => ({ row: f.source.row_number as number, label: f.value }))}
                  activeRow={selectedField?.source.row_number ?? null}
                  onSelect={(row) => {
                    const target = selected.fields.find((f) => f.source.row_number === row);
                    if (target) setSelectedFieldId(target.id);
                  }}
                />
              ) : (
                <SchematicPage
                  highlights={pageHighlights}
                  activeId={selectedField?.id ?? null}
                  onSelect={setSelectedFieldId}
                />
              )}
              <p className="mt-3 text-[11px] leading-relaxed text-ink-400">
                {selected.kind === "ledger"
                  ? "Read directly by pandas. No AI touched these values, so provenance is a row number."
                  : "Schematic render at true page proportions. When the backend serves document files, the real page appears here with the same highlights."}
              </p>
            </section>
          )}

          {/* What the AI read */}
          {selected && (
            <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-200 px-4 py-3">
                <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-600">
                  {selected.kind === "ledger" ? "What pandas read" : "What the AI read"}
                </h2>
              </div>
              <ul className="divide-y divide-slate-100">
                {selected.fields.map((field) => {
                  const active = field.id === selectedField?.id;
                  return (
                    <li key={field.id}>
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={() => setSelectedFieldId(field.id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            setSelectedFieldId(field.id);
                          }
                        }}
                        className={cn(
                          "block w-full cursor-pointer px-4 py-2.5 text-left transition-colors",
                          active ? "bg-amber-50" : "hover:bg-slate-50",
                        )}
                      >
                        <span className="flex items-center justify-between gap-3">
                          <span className="min-w-0">
                            <span className="block text-xs font-medium text-ink-400">
                              {field.field}
                              {field.source.page != null && ` · page ${field.source.page}`}
                              {field.source.row_number != null &&
                                ` · row ${field.source.row_number}`}
                            </span>
                            <span className="block truncate text-sm font-medium text-ink-900 tabular-nums">
                              {field.value}
                            </span>
                          </span>
                          {field.confidence ? (
                            <ConfidenceBadge confidence={field.confidence} />
                          ) : (
                            <span className="shrink-0 text-[10px] font-medium text-ink-400">
                              deterministic
                            </span>
                          )}
                        </span>
                        <span className="mt-1.5 flex items-center justify-between gap-2">
                          <span className="flex min-w-0 items-center gap-1.5">
                            <span className="truncate text-[11px] text-ink-400">
                              {field.party}
                            </span>
                            <DecisionBadge decision={field.decision} />
                          </span>
                          <Link
                            href={`/review?item=${encodeURIComponent(field.reviewItemId)}`}
                            onClick={(event) => event.stopPropagation()}
                            className="flex shrink-0 items-center gap-0.5 font-mono text-[10px] text-brand-700 hover:underline"
                          >
                            {field.reviewItemId}
                            <ArrowRight className="h-3 w-3" aria-hidden />
                          </Link>
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
