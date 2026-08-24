"use client";

/**
 * The review table: the main working screen. Every item requires an explicit
 * human approve or reject — there is no auto-approval path anywhere in this
 * file, and the two quality signals stay in two columns: Match Strength
 * (deterministic matcher) and Extraction Confidence (AI reading step).
 */

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Check, Eye, Loader2, X } from "lucide-react";
import {
  ApiError,
  approveReviewItem,
  getReviewItems,
  rejectReviewItem,
} from "@/lib/api";
import type { MatchStatus, ReviewItem } from "@/lib/types";
import { formatDate, formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { EmptyState, ErrorState } from "@/components/ui/states";
import {
  ConfidenceBadge,
  DecisionBadge,
  MatchStrengthBadge,
  StatusBadge,
} from "@/components/ui/badge";
import { EvidenceViewer } from "@/components/review/evidence-viewer";

type Tab = "all" | MatchStatus | "flagged";

const TABS: { key: Tab; label: string }[] = [
  { key: "all", label: "All" },
  { key: "matched", label: "Matched" },
  { key: "partial", label: "Partial" },
  { key: "unmatched", label: "Unmatched" },
  { key: "flagged", label: "Flagged" },
];

function tabFilter(items: ReviewItem[], tab: Tab): ReviewItem[] {
  if (tab === "all") return items;
  if (tab === "flagged") return items.filter((item) => item.flags.length > 0);
  return items.filter((item) => item.match.status === tab);
}

export default function ReviewPage() {
  return (
    <React.Suspense>
      <ReviewScreen />
    </React.Suspense>
  );
}

function ReviewScreen() {
  const searchParams = useSearchParams();
  const [items, setItems] = React.useState<ReviewItem[] | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [tab, setTab] = React.useState<Tab>("all");
  const [busyIds, setBusyIds] = React.useState<Set<string>>(new Set());
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [rejecting, setRejecting] = React.useState<ReviewItem | null>(null);
  const [rejectReason, setRejectReason] = React.useState("");
  const [rejectSubmitting, setRejectSubmitting] = React.useState(false);
  const [viewing, setViewing] = React.useState<ReviewItem | null>(null);

  const load = React.useCallback(() => {
    setLoadError(null);
    setItems(null);
    getReviewItems()
      .then((response) => setItems(response.items))
      .catch((caught) =>
        setLoadError(
          caught instanceof ApiError
            ? caught.message
            : "Could not load the review queue.",
        ),
      );
  }, []);

  React.useEffect(load, [load]);

  // Deep link from the dashboard's next-best actions: ?item=RI-0002
  const focusItemId = searchParams.get("item");
  React.useEffect(() => {
    if (!focusItemId || !items) return;
    const target = items.find((item) => item.review_item_id === focusItemId);
    if (target) setViewing(target);
    // Open once when the data arrives; navigating tabs later must not re-open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items === null]);

  const replaceItem = (updated: ReviewItem) =>
    setItems((current) =>
      current
        ? current.map((item) =>
            item.review_item_id === updated.review_item_id ? updated : item,
          )
        : current,
    );

  const markBusy = (id: string, busy: boolean) =>
    setBusyIds((current) => {
      const next = new Set(current);
      if (busy) next.add(id);
      else next.delete(id);
      return next;
    });

  /** Optimistic approve: flip the row immediately, roll back on failure. */
  const approve = async (item: ReviewItem) => {
    if (item.decision !== "pending" || busyIds.has(item.review_item_id)) return;
    setActionError(null);
    markBusy(item.review_item_id, true);
    replaceItem({
      ...item,
      decision: "approved",
      decided_by: "you",
      decided_at: new Date().toISOString(),
    });
    try {
      const response = await approveReviewItem(item.review_item_id);
      replaceItem(response.review_item);
    } catch (caught) {
      replaceItem(item); // roll back
      setActionError(
        caught instanceof ApiError ? caught.message : "Approve failed. Try again.",
      );
    } finally {
      markBusy(item.review_item_id, false);
    }
  };

  /** Reject requires a reason — by the API contract, not just the UI. */
  const submitReject = async () => {
    if (!rejecting || !rejectReason.trim() || rejectSubmitting) return;
    const item = rejecting;
    setRejectSubmitting(true);
    setActionError(null);
    markBusy(item.review_item_id, true);
    replaceItem({
      ...item,
      decision: "rejected",
      decided_by: "you",
      decided_at: new Date().toISOString(),
      rejection_reason: rejectReason.trim(),
    });
    setRejecting(null);
    try {
      const response = await rejectReviewItem(item.review_item_id, rejectReason.trim());
      replaceItem(response.review_item);
    } catch (caught) {
      replaceItem(item); // roll back
      setActionError(
        caught instanceof ApiError ? caught.message : "Reject failed. Try again.",
      );
    } finally {
      markBusy(item.review_item_id, false);
      setRejectSubmitting(false);
      setRejectReason("");
    }
  };

  const visible = items ? tabFilter(items, tab) : [];

  return (
    <div>
      <div className="mb-5 flex items-end justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink-900">Review queue</h1>
          <p className="mt-1 text-sm text-ink-600">
            The AI suggests, you decide. Every row needs your explicit approve or
            reject, and each decision lands in the immutable audit trail.
          </p>
        </div>
        {items && (
          <p className="text-xs text-ink-400">
            {items.filter((item) => item.decision === "pending").length} of{" "}
            {items.length} pending
          </p>
        )}
      </div>

      {/* Filter tabs */}
      <div className="mb-4 flex gap-1 border-b border-slate-200">
        {TABS.map(({ key, label }) => {
          const count = items ? tabFilter(items, key).length : null;
          return (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={cn(
                "-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors",
                tab === key
                  ? "border-brand-800 text-brand-900"
                  : "border-transparent text-ink-400 hover:text-ink-600",
              )}
            >
              {label}
              {count !== null && (
                <span className="ml-1.5 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] text-ink-600">
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {actionError && (
        <p className="mb-3 rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
          {actionError}
        </p>
      )}

      {loadError ? (
        <ErrorState message={loadError} onRetry={load} />
      ) : items === null ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-14 w-full" />
          ))}
        </div>
      ) : visible.length === 0 ? (
        <EmptyState
          title={items.length === 0 ? "No review items yet" : "Nothing in this filter"}
          message={
            items.length === 0
              ? "Upload a ledger, bank statement, and invoices to open a case."
              : "No items match the selected tab. Switch tabs to keep reviewing."
          }
          action={
            items.length === 0 ? (
              <Link href="/upload">
                <Button size="sm">Go to upload</Button>
              </Link>
            ) : undefined
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
          <table className="w-full min-w-[1080px] text-left">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-[10px] font-semibold tracking-wide text-ink-400 uppercase">
                <th className="px-4 py-2.5">Date</th>
                <th className="px-4 py-2.5 text-right">Amount</th>
                <th className="px-4 py-2.5">Party</th>
                <th className="px-4 py-2.5">Status</th>
                <th className="px-4 py-2.5">
                  <Tooltip content="How well the rows line up — computed by the deterministic matcher, never by AI.">
                    <span className="cursor-help underline decoration-dotted">Match strength</span>
                  </Tooltip>
                </th>
                <th className="px-4 py-2.5">
                  <Tooltip content="How sure the AI is that it read the source values correctly. Independent of match strength.">
                    <span className="cursor-help underline decoration-dotted">Extraction confidence</span>
                  </Tooltip>
                </th>
                <th className="px-4 py-2.5">Reason</th>
                <th className="px-4 py-2.5">Decision</th>
                <th className="px-4 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => {
                const busy = busyIds.has(item.review_item_id);
                return (
                  <tr
                    key={item.review_item_id}
                    className="border-b border-slate-100 text-sm last:border-0 hover:bg-slate-50/60"
                  >
                    <td className="whitespace-nowrap px-4 py-3 text-ink-600">
                      {formatDate(item.ledger_entry.date)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right font-medium text-ink-900 tabular-nums">
                      {formatMoney(item.ledger_entry.amount, item.ledger_entry.currency)}
                    </td>
                    <td className="max-w-52 truncate px-4 py-3 font-medium text-ink-900">
                      {item.ledger_entry.party_name}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <span className="inline-flex items-center gap-1.5">
                        <StatusBadge status={item.match.status} />
                        {item.flags.length > 0 && <StatusBadge status="flagged" />}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <MatchStrengthBadge strength={item.match.match_strength} />
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <ConfidenceBadge confidence={item.extraction_confidence} />
                    </td>
                    <td className="max-w-72 px-4 py-3">
                      <Tooltip content={item.match.reason} className="block max-w-full">
                        <span className="block truncate text-xs text-ink-600">
                          {item.match.reason}
                        </span>
                      </Tooltip>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      {item.decision === "rejected" && item.rejection_reason ? (
                        <Tooltip content={item.rejection_reason}>
                          <span className="cursor-help">
                            <DecisionBadge decision={item.decision} />
                          </span>
                        </Tooltip>
                      ) : (
                        <DecisionBadge decision={item.decision} />
                      )}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <div className="flex items-center justify-end gap-1.5">
                        {item.decision === "pending" && (
                          <>
                            <Button
                              size="sm"
                              variant="success"
                              disabled={busy}
                              onClick={() => approve(item)}
                              aria-label={`Approve ${item.review_item_id}`}
                            >
                              {busy ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                              ) : (
                                <Check className="h-3.5 w-3.5" aria-hidden />
                              )}
                              Approve
                            </Button>
                            <Button
                              size="sm"
                              variant="danger"
                              disabled={busy}
                              onClick={() => {
                                setRejectReason("");
                                setRejecting(item);
                              }}
                              aria-label={`Reject ${item.review_item_id}`}
                            >
                              <X className="h-3.5 w-3.5" aria-hidden />
                              Reject
                            </Button>
                          </>
                        )}
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setViewing(item)}
                          aria-label={`View evidence for ${item.review_item_id}`}
                        >
                          <Eye className="h-3.5 w-3.5" aria-hidden />
                          Evidence
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Reject reason prompt — a reason is required by the API contract. */}
      <Dialog
        open={rejecting !== null}
        onClose={() => setRejecting(null)}
        title={`Reject ${rejecting?.review_item_id ?? ""} — ${rejecting?.ledger_entry.party_name ?? ""}`}
      >
        <p className="mb-2 text-xs text-ink-600">
          The reason is recorded verbatim in the immutable audit trail.
        </p>
        <textarea
          autoFocus
          value={rejectReason}
          onChange={(event) => setRejectReason(event.target.value)}
          rows={3}
          placeholder="Why is this item rejected?"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-ink-900 focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
        />
        <div className="mt-3 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={() => setRejecting(null)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            size="sm"
            disabled={!rejectReason.trim() || rejectSubmitting}
            onClick={submitReject}
          >
            {rejectSubmitting && (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            )}
            Reject item
          </Button>
        </div>
      </Dialog>

      {viewing && <EvidenceViewer item={viewing} onClose={() => setViewing(null)} />}
    </div>
  );
}
