"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronsUpDown } from "lucide-react";
import { FIXTURE_MODE, getDashboard } from "@/lib/api";

/**
 * The page header: which case is open, who is signed in, and — honestly —
 * whether the data on screen is fixture data or the live backend.
 *
 * The case chip is the organization's current case as the backend reports it
 * (`GET /v1/dashboard` names the most recent case). With no case yet, no chip:
 * nothing is invented client-side.
 */
export function Header() {
  const pathname = usePathname();
  const [caseLabel, setCaseLabel] = React.useState<string | null>(null);

  // Refetched on navigation so a freshly uploaded case appears without a
  // full reload. The layout keeps this component mounted between routes.
  React.useEffect(() => {
    let cancelled = false;
    getDashboard()
      .then((summary) => {
        if (!cancelled) setCaseLabel(summary.client_name);
      })
      .catch(() => {
        // No case yet, or the backend is unreachable: show no chip.
        if (!cancelled) setCaseLabel(null);
      });
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white/80 px-6 backdrop-blur-sm transition-all duration-300 md:h-12 md:px-4">
      <div className="flex items-center gap-3 min-w-0">
        {caseLabel && (
          <>
            <span className="text-xs font-medium text-ink-400 hidden sm:inline">Case:</span>
            <Link
              href="/cases"
              title="Switch case"
              className="hover-lift flex items-center gap-1.5 rounded-lg border border-slate-200 bg-gradient-to-b from-slate-50 to-white px-3 py-1.5 text-sm font-medium text-ink-900 transition-all"
            >
              <span className="truncate">{caseLabel}</span>
              <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-ink-400 transition-transform group-hover:rotate-180" aria-hidden />
            </Link>
          </>
        )}
        {FIXTURE_MODE && (
          <span
            className="animate-glow-pulse rounded-full bg-sky-50 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-sky-700 ring-1 ring-sky-200 whitespace-nowrap"
            title="NEXT_PUBLIC_TARAZU_API_URL is unset, so data comes from sample fixtures"
          >
            FIXTURE DATA
          </span>
        )}
      </div>
    </header>
  );
}
