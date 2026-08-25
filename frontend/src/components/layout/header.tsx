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
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
      <div className="flex items-center gap-3">
        {caseLabel && (
          <>
            <span className="text-xs font-medium text-ink-400">Case:</span>
            <Link
              href="/cases"
              title="Switch case"
              className="flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-3 py-1 text-sm font-medium text-ink-900 transition-colors hover:border-brand-600 hover:text-brand-900"
            >
              {caseLabel}
              <ChevronsUpDown className="h-3.5 w-3.5 text-ink-400" aria-hidden />
            </Link>
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
