"use client";

/**
 * Notification bell for the app header. Surfaces review items that are still
 * pending a human decision, so the auditor sees what needs attention without
 * leaving the screen they are on.
 */

import * as React from "react";
import Link from "next/link";
import { Bell } from "lucide-react";
import { ApiError, getReviewItems } from "@/lib/api";
import type { ReviewItem } from "@/lib/types";
import { formatMoney } from "@/lib/format";

export function Notifications() {
  const [items, setItems] = React.useState<ReviewItem[] | null>(null);
  const [open, setOpen] = React.useState(false);
  const rootRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    let cancelled = false;
    getReviewItems()
      .then((response) => !cancelled && setItems(response.items))
      .catch((caught) => {
        if (!cancelled && caught instanceof ApiError) setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const pending = (items ?? []).filter((item) => item.decision === "pending");
  const count = pending.length;

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-label="Notifications"
        aria-expanded={open}
        className="relative inline-flex h-9 w-9 items-center justify-center rounded-md text-ink-600 transition-colors hover:bg-slate-100 hover:text-ink-900"
      >
        <Bell className="h-5 w-5" aria-hidden />
        {count > 0 && (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold text-white ring-2 ring-white">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <p className="text-sm font-semibold text-ink-900">Awaiting you</p>
            {count > 0 && (
              <span className="rounded-full bg-rose-50 px-2 py-0.5 text-[10px] font-medium text-rose-700 ring-1 ring-rose-200">
                {count} pending
              </span>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {items === null ? (
              <div className="space-y-2 p-4">
                {Array.from({ length: 3 }).map((_, index) => (
                  <div
                    key={index}
                    className="h-10 w-full animate-pulse rounded-md bg-slate-100"
                  />
                ))}
              </div>
            ) : pending.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-ink-400">
                Nothing is waiting on you. Every item has a decision.
              </p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {pending.slice(0, 6).map((item) => (
                  <li key={item.review_item_id}>
                    <Link
                      href={`/review?item=${encodeURIComponent(item.review_item_id)}`}
                      onClick={() => setOpen(false)}
                      className="block px-4 py-3 transition-colors hover:bg-slate-50"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-medium text-ink-900">
                          {item.ledger_entry.party_name}
                        </span>
                        <span className="shrink-0 text-xs tabular-nums text-ink-600">
                          {formatMoney(item.ledger_entry.amount, item.ledger_entry.currency)}
                        </span>
                      </div>
                      <span className="block truncate text-xs text-ink-400">
                        {item.match.reason}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="border-t border-slate-100 p-2">
            <Link
              href="/review"
              onClick={() => setOpen(false)}
              className="block rounded-md px-3 py-2 text-center text-xs font-medium text-brand-700 transition-colors hover:bg-brand-50"
            >
              Open review queue
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
