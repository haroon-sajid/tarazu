"use client";

import { FIXTURE_MODE } from "@/lib/api";
import { CircleUserRound } from "lucide-react";

/**
 * The page header: which case is open, who is signed in, and — honestly —
 * whether the data on screen is fixture data or the live backend.
 */
export function Header({ caseLabel }: { caseLabel?: string }) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
      <div className="flex items-center gap-3">
        <span className="text-xs font-medium text-ink-400">Case:</span>
        <span className="rounded-md border border-slate-200 bg-slate-50 px-3 py-1 text-sm font-medium text-ink-900">
          {caseLabel ?? "Sethi Textiles (Pvt) Ltd — June 2026"}
        </span>
        {FIXTURE_MODE && (
          <span
            className="rounded-full bg-sky-50 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-sky-700 ring-1 ring-sky-200"
            title="NEXT_PUBLIC_TARAZU_API_URL is unset — data comes from sample fixtures"
          >
            FIXTURE DATA
          </span>
        )}
      </div>
      <div className="flex items-center gap-2.5">
        <div className="text-right">
          <p className="text-xs font-semibold text-ink-900">Demo Auditor</p>
          <p className="text-[10px] text-ink-400">user-demo-auditor</p>
        </div>
        <CircleUserRound className="h-7 w-7 text-ink-400" aria-hidden />
      </div>
    </header>
  );
}
