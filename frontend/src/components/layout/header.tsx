"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Check, ChevronsUpDown, FolderOpen } from "lucide-react";
import { FIXTURE_MODE, getActiveCaseId, listCases, setActiveCaseId } from "@/lib/api";
import { useActiveCaseVersion } from "@/lib/use-active-case";
import type { CaseStatus, CaseSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS_DOT: Record<CaseStatus, string> = {
  uploaded: "bg-slate-400",
  extracting: "bg-sky-500 animate-pulse",
  awaiting_matching: "bg-amber-500 animate-pulse",
  ready_for_review: "bg-emerald-500",
  failed: "bg-rose-500",
};

/**
 * The page header: which case is open, who is signed in, and — honestly —
 * whether the data on screen is fixture data or the live backend.
 *
 * The case chip is the case switcher. It opens the organization's engagements
 * (`GET /v1/cases`) instead of navigating away: picking one writes the
 * browser's saved selection, and the workspace remounts every screen against
 * it (see `Workspace`). Renaming and deleting live behind "Manage cases", on
 * the Cases screen. With no case yet, no chip: nothing is invented
 * client-side.
 */
export function Header() {
  const pathname = usePathname();
  const caseVersion = useActiveCaseVersion();
  const [cases, setCases] = React.useState<CaseSummary[] | null>(null);
  const [activeId, setActiveId] = React.useState<string | null>(null);
  const [open, setOpen] = React.useState(false);
  const rootRef = React.useRef<HTMLDivElement | null>(null);

  const readCases = React.useCallback(() => {
    listCases()
      .then((response) => {
        setCases(response.cases);
        setActiveId(getActiveCaseId());
      })
      .catch(() => {
        // No case yet, or the backend is unreachable: show no chip.
        setCases(null);
      });
  }, []);

  // Refetched on navigation (a freshly uploaded case appears without a full
  // reload) and whenever the selection changes somewhere else — the Cases and
  // Upload screens write the same storage key this reads.
  React.useEffect(() => {
    let cancelled = false;
    listCases()
      .then((response) => {
        if (!cancelled) {
          setCases(response.cases);
          setActiveId(getActiveCaseId());
        }
      })
      .catch(() => {
        if (!cancelled) setCases(null);
      });
    return () => {
      cancelled = true;
    };
  }, [pathname, caseVersion]);

  // Close the dropdown the two ways people expect: a click elsewhere, or
  // Escape. The chip itself is a plain button and stays in the tab order.
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

  // With no explicit selection the workspace follows the newest case — the
  // same default the backend applies to an absent ?case_id=.
  const active = cases
    ? (cases.find((item) => item.case_id === activeId) ?? cases[0] ?? null)
    : null;

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next) readCases(); // names change; the list is read fresh each open
  };

  const select = (caseSummary: CaseSummary) => {
    setOpen(false);
    if (caseSummary.case_id !== active?.case_id) {
      setActiveId(caseSummary.case_id); // optimistic; the event confirms it
      setActiveCaseId(caseSummary.case_id);
    }
  };

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
      <div className="flex items-center gap-3">
        {active && cases && cases.length > 0 && (
          <>
            <span className="text-xs font-medium text-ink-400">Case:</span>
            <div className="relative" ref={rootRef}>
              <button
                type="button"
                onClick={toggle}
                title="Switch case"
                aria-haspopup="listbox"
                aria-expanded={open}
                className="flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-3 py-1 text-sm font-medium text-ink-900 transition-colors hover:border-brand-600 hover:text-brand-900"
              >
                <span className="max-w-56 truncate">{active.client_name}</span>
                <ChevronsUpDown className="h-3.5 w-3.5 text-ink-400" aria-hidden />
              </button>
              {open && (
                <div className="absolute left-0 top-full z-40 mt-1.5 w-80 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg">
                  <div className="max-h-80 overflow-y-auto p-1" role="listbox" aria-label="Cases">
                    {cases.map((caseSummary) => {
                      const isActive = caseSummary.case_id === active.case_id;
                      return (
                        <button
                          key={caseSummary.case_id}
                          type="button"
                          role="option"
                          aria-selected={isActive}
                          onClick={() => select(caseSummary)}
                          className={cn(
                            "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors",
                            isActive ? "bg-brand-50" : "hover:bg-slate-50",
                          )}
                        >
                          <span
                            className={cn(
                              "h-1.5 w-1.5 shrink-0 rounded-full",
                              STATUS_DOT[caseSummary.status],
                            )}
                            title={caseSummary.status}
                            aria-hidden
                          />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-medium text-ink-900">
                              {caseSummary.client_name}
                            </span>
                            <span className="block font-mono text-[10px] text-ink-400">
                              {caseSummary.case_id}
                            </span>
                          </span>
                          {caseSummary.pending_items > 0 && (
                            <span className="shrink-0 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-800 ring-1 ring-amber-200">
                              {caseSummary.pending_items} pending
                            </span>
                          )}
                          {isActive && (
                            <Check className="h-3.5 w-3.5 shrink-0 text-brand-700" aria-hidden />
                          )}
                        </button>
                      );
                    })}
                  </div>
                  <div className="border-t border-slate-100 p-1">
                    <Link
                      href="/cases"
                      onClick={() => setOpen(false)}
                      className="flex items-center gap-2 rounded-md px-2.5 py-2 text-xs text-ink-600 transition-colors hover:bg-slate-50 hover:text-ink-900"
                    >
                      <FolderOpen className="h-3.5 w-3.5" aria-hidden />
                      Manage cases — rename, delete, or open
                    </Link>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
        {FIXTURE_MODE && (
          <span
            className="rounded-full bg-sky-50 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-sky-700 ring-1 ring-sky-200"
            title="NEXT_PUBLIC_TARAZU_API_URL is unset, so data comes from sample fixtures"
          >
            FIXTURE DATA
          </span>
        )}
      </div>
    </header>
  );
}
