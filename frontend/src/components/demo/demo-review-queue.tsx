"use client";

/**
 * The demo review queue: the working screen, in public.
 *
 * It keeps the real screen's shape — date, party, amount, match status, match
 * strength, extraction confidence, flags, decision — because the point of the
 * playground is to show the product rather than a picture of it. The two
 * quality signals stay in two columns for the same reason they do in
 * `(app)/review`: match strength comes from the deterministic matcher,
 * extraction confidence from the AI reading step, and conflating them would be
 * a lie about how the product works.
 *
 * Two layouts, one data set: a table from `md` up, and a card list below it. A
 * nine-column table on a 390px phone is a horizontal-scroll maze, and the
 * expandable evidence panel — the whole reason to click a row — would open off
 * screen. Both layouts are in the DOM at once, so every element id is prefixed
 * per layout to keep ids unique.
 *
 * This component holds no state. The playground owns the items, the filter and
 * the open row so the dashboard tab can jump straight to an item.
 */

import * as React from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { ReviewItem } from "@/lib/types";
import { formatDate, formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";
import { EmptyState } from "@/components/ui/states";
import {
  ConfidenceBadge,
  DecisionBadge,
  MatchStrengthBadge,
  StatusBadge,
} from "@/components/ui/badge";
import { EvidencePanel } from "@/components/demo/demo-evidence";

export type QueueFilter = "all" | "matched" | "partial" | "unmatched" | "flagged" | "attention";

export const QUEUE_FILTERS: { key: QueueFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "matched", label: "Matched" },
  { key: "partial", label: "Partial" },
  { key: "unmatched", label: "Unmatched" },
  { key: "flagged", label: "Flagged" },
  { key: "attention", label: "Attention" },
];

/** Mirrors `tabFilter` in the signed-in review screen, filter for filter. */
export function filterQueue(items: ReviewItem[], filter: QueueFilter): ReviewItem[] {
  if (filter === "all") return items;
  if (filter === "flagged") return items.filter((item) => item.flags.length > 0);
  // Attention: the AI's own reading is uncertain — check the source closely
  // before deciding, whatever the match result says.
  if (filter === "attention")
    return items.filter((item) => item.extraction_confidence !== "high");
  return items.filter((item) => item.match.status === filter);
}

const TABLE_COLUMNS = 9;

interface QueueProps {
  items: ReviewItem[];
  filter: QueueFilter;
  onFilterChange: (filter: QueueFilter) => void;
  expandedId: string | null;
  onExpandedChange: (id: string | null) => void;
  onDecide: (id: string, decision: "approved" | "rejected", reason?: string) => void;
  /** Bumped by the dashboard when it sends the visitor to a specific row. */
  jumpToken: number;
}

export function DemoReviewQueue({
  items,
  filter,
  onFilterChange,
  expandedId,
  onExpandedChange,
  onDecide,
  jumpToken,
}: QueueProps) {
  const visible = filterQueue(items, filter);
  const pending = items.filter((item) => item.decision === "pending").length;

  // Arriving from a next-best action: bring the row the visitor asked for into
  // view. Keyed on the token, not on `expandedId`, so opening a row by clicking
  // it never yanks the page around under the pointer.
  React.useEffect(() => {
    if (!jumpToken || !expandedId) return;
    const target =
      document.getElementById(`demo-row-${expandedId}`) ??
      document.getElementById(`demo-card-${expandedId}`);
    if (!target) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "center" });
  }, [jumpToken, expandedId]);

  const toggle = (id: string) => onExpandedChange(expandedId === id ? null : id);

  return (
    <div>
      <div className="mb-3 sm:flex sm:items-end sm:justify-between sm:gap-4">
        <div>
          <h3 className="text-base font-bold text-ink-900">Review queue</h3>
          <p className="mt-1 max-w-2xl text-sm text-ink-600">
            The AI suggests, you decide. Every row needs an explicit approve or reject.
            In the product each one lands in the immutable audit trail. Open a row to see
            the evidence behind it.
          </p>
        </div>
        <p className="mt-2 shrink-0 text-xs text-ink-400 sm:mt-0">
          {pending} of {items.length} pending
        </p>
      </div>

      {/* Filters. Deliberately buttons with `aria-pressed`, not a second tablist:
          the playground's own tabs already own the tab semantics on this page. */}
      <div className="mb-3 -mx-1 flex gap-1 overflow-x-auto border-b border-slate-200 px-1">
        {QUEUE_FILTERS.map(({ key, label }) => {
          const count = filterQueue(items, key).length;
          return (
            <button
              key={key}
              type="button"
              aria-pressed={filter === key}
              onClick={() => onFilterChange(key)}
              className={cn(
                "-mb-px shrink-0 border-b-2 px-3 py-2 text-sm font-medium transition-colors sm:px-4",
                filter === key
                  ? "border-brand-800 text-brand-900"
                  : "border-transparent text-ink-400 hover:text-ink-600",
              )}
            >
              {label}
              <span className="ml-1.5 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] text-ink-600">
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {visible.length === 0 ? (
        <EmptyState
          title="Nothing in this filter"
          message="No items match the selected filter. Switch back to All to keep looking around."
        />
      ) : (
        <>
          {/* ---------- Table: md and up ---------- */}
          <div className="hidden overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm md:block">
            <table className="w-full min-w-[1000px] text-left">
              <caption className="sr-only">
                Sample review queue for the demo engagement. Each row expands to show its
                evidence.
              </caption>
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-[10px] font-semibold tracking-wide text-ink-400 uppercase">
                  <th scope="col" className="px-4 py-2.5">
                    Date
                  </th>
                  <th scope="col" className="px-4 py-2.5 text-right">
                    Amount
                  </th>
                  <th scope="col" className="px-4 py-2.5">
                    Party
                  </th>
                  <th scope="col" className="px-4 py-2.5">
                    Status
                  </th>
                  <th scope="col" className="px-4 py-2.5">
                    Match strength
                  </th>
                  <th scope="col" className="px-4 py-2.5">
                    Extraction confidence
                  </th>
                  <th scope="col" className="px-4 py-2.5">
                    Flags
                  </th>
                  <th scope="col" className="px-4 py-2.5">
                    Decision
                  </th>
                  <th scope="col" className="px-4 py-2.5 text-right">
                    Evidence
                  </th>
                </tr>
              </thead>
              <tbody>
                {visible.map((item) => {
                  const open = expandedId === item.review_item_id;
                  const panelId = `demo-panel-${item.review_item_id}`;
                  return (
                    <React.Fragment key={item.review_item_id}>
                      <tr
                        id={`demo-row-${item.review_item_id}`}
                        // Mouse users get the whole row; keyboard users get the
                        // button in the last cell, which carries the semantics.
                        // The guard stops a click on that button toggling twice.
                        onClick={(event) => {
                          if ((event.target as HTMLElement).closest("button")) return;
                          toggle(item.review_item_id);
                        }}
                        className={cn(
                          "cursor-pointer border-b border-slate-100 text-sm transition-colors last:border-0",
                          open ? "bg-brand-50/60" : "hover:bg-slate-50/60",
                        )}
                      >
                        <td className="px-4 py-3 whitespace-nowrap text-ink-600">
                          {formatDate(item.ledger_entry.date)}
                        </td>
                        <td className="px-4 py-3 text-right font-medium whitespace-nowrap text-ink-900 tabular-nums">
                          {formatMoney(item.ledger_entry.amount, item.ledger_entry.currency)}
                        </td>
                        <td className="max-w-52 truncate px-4 py-3 font-medium text-ink-900">
                          {item.ledger_entry.party_name}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <StatusBadge status={item.match.status} />
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <MatchStrengthBadge strength={item.match.match_strength} />
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <ConfidenceBadge confidence={item.extraction_confidence} />
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          {item.flags.length === 0 ? (
                            <span className="text-xs text-ink-400">None</span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5">
                              <StatusBadge status="flagged" />
                              <span className="text-xs text-ink-600 tabular-nums">
                                {item.flags.length}
                              </span>
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <DecisionBadge decision={item.decision} />
                        </td>
                        <td className="px-4 py-3 text-right whitespace-nowrap">
                          <button
                            type="button"
                            aria-expanded={open}
                            aria-controls={panelId}
                            onClick={() => toggle(item.review_item_id)}
                            className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-ink-600 transition-colors hover:border-brand-600 hover:text-brand-700 focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:outline-none"
                          >
                            {open ? "Hide" : "Show"}
                            {open ? (
                              <ChevronUp className="h-3.5 w-3.5" aria-hidden />
                            ) : (
                              <ChevronDown className="h-3.5 w-3.5" aria-hidden />
                            )}
                            <span className="sr-only">
                              evidence for {item.review_item_id}
                            </span>
                          </button>
                        </td>
                      </tr>
                      {open && (
                        <tr id={panelId}>
                          <td colSpan={TABLE_COLUMNS} className="p-0">
                            <EvidencePanel
                              item={item}
                              idPrefix="demo-table"
                              onDecide={(decision, reason) =>
                                onDecide(item.review_item_id, decision, reason)
                              }
                            />
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* ---------- Cards: below md ---------- */}
          <ul className="space-y-2 md:hidden">
            {visible.map((item) => {
              const open = expandedId === item.review_item_id;
              const panelId = `demo-card-panel-${item.review_item_id}`;
              return (
                <li
                  key={item.review_item_id}
                  id={`demo-card-${item.review_item_id}`}
                  className={cn(
                    "overflow-hidden rounded-lg border bg-white shadow-sm transition-colors",
                    open ? "border-brand-600" : "border-slate-200",
                  )}
                >
                  <button
                    type="button"
                    aria-expanded={open}
                    aria-controls={panelId}
                    onClick={() => toggle(item.review_item_id)}
                    className="w-full px-3 py-3 text-left transition-colors hover:bg-slate-50/60 focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:outline-none"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-ink-900">
                          {item.ledger_entry.party_name}
                        </p>
                        <p className="mt-0.5 text-[11px] text-ink-400">
                          {formatDate(item.ledger_entry.date)} · {item.review_item_id}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="text-sm font-bold text-ink-900 tabular-nums">
                          {formatMoney(
                            item.ledger_entry.amount,
                            item.ledger_entry.currency,
                          )}
                        </p>
                        <span className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-brand-700">
                          {open ? "Hide" : "Evidence"}
                          {open ? (
                            <ChevronUp className="h-3.5 w-3.5" aria-hidden />
                          ) : (
                            <ChevronDown className="h-3.5 w-3.5" aria-hidden />
                          )}
                        </span>
                      </div>
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <StatusBadge status={item.match.status} />
                      {item.flags.length > 0 && <StatusBadge status="flagged" />}
                      <ConfidenceBadge confidence={item.extraction_confidence} />
                      <MatchStrengthBadge strength={item.match.match_strength} />
                      <DecisionBadge decision={item.decision} />
                    </div>
                  </button>
                  {open && (
                    <div id={panelId}>
                      <EvidencePanel
                        item={item}
                        idPrefix="demo-card"
                        onDecide={(decision, reason) =>
                          onDecide(item.review_item_id, decision, reason)
                        }
                      />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
