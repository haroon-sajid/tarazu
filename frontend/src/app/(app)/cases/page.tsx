"use client";

/**
 * Cases — every engagement the firm has open, and the switch that decides
 * which one the workspace screens (dashboard, documents, review, assistant,
 * audit trail, reports) are about. The selection lives in this browser only;
 * the backend re-checks tenancy on the id with every request.
 */

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle2, Plus } from "lucide-react";
import { ApiError, getActiveCaseId, listCases, setActiveCaseId } from "@/lib/api";
import type { CaseStatus, CaseSummary } from "@/lib/types";
import { formatDate, formatTimestamp } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";

const STATUS_STYLE: Record<CaseStatus, { label: string; className: string }> = {
  uploaded: { label: "Uploaded", className: "bg-slate-100 text-ink-600 ring-slate-200" },
  extracting: { label: "Extracting", className: "bg-sky-50 text-sky-700 ring-sky-200" },
  awaiting_matching: {
    label: "Awaiting matching",
    className: "bg-amber-50 text-amber-800 ring-amber-200",
  },
  ready_for_review: {
    label: "Ready for review",
    className: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  },
  failed: { label: "Failed", className: "bg-rose-50 text-rose-700 ring-rose-200" },
};

function CaseStatusPill({ status }: { status: CaseStatus }) {
  const style = STATUS_STYLE[status];
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ring-1",
        style.className,
      )}
    >
      {style.label}
    </span>
  );
}

export default function CasesPage() {
  const router = useRouter();
  const [cases, setCases] = React.useState<CaseSummary[] | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [activeId, setActiveId] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    setLoadError(null);
    setCases(null);
    listCases()
      .then((response) => setCases(response.cases))
      .catch((caught) =>
        setLoadError(
          caught instanceof ApiError ? caught.message : "Could not load the cases.",
        ),
      );
  }, []);

  React.useEffect(() => {
    load();
    setActiveId(getActiveCaseId());
  }, [load]);

  const open = (caseSummary: CaseSummary) => {
    setActiveCaseId(caseSummary.case_id);
    router.push("/dashboard");
  };

  // With no explicit selection the workspace follows the newest case — mark
  // that row as the effective one so the screen never shows "nothing active".
  const effectiveActive = activeId ?? cases?.[0]?.case_id ?? null;

  return (
    <div>
      <div className="mb-5 flex items-end justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink-900">Cases</h1>
          <p className="mt-1 text-sm text-ink-600">
            Every engagement in your firm. Open one to point the whole
            workspace (dashboard, documents, review, and reports) at it.
          </p>
        </div>
        <Link href="/upload">
          <Button size="sm">
            <Plus className="h-3.5 w-3.5" aria-hidden />
            New case
          </Button>
        </Link>
      </div>

      {loadError ? (
        <ErrorState message={loadError} onRetry={load} />
      ) : cases === null ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-14 w-full" />
          ))}
        </div>
      ) : cases.length === 0 ? (
        <EmptyState
          title="No cases yet"
          message="A case opens when you upload a bank statement, invoices, and a ledger."
          action={
            <Link href="/upload">
              <Button size="sm">Go to upload</Button>
            </Link>
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
          <table className="w-full min-w-[980px] text-left">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                <th className="px-4 py-2.5">Client</th>
                <th className="px-4 py-2.5">Case id</th>
                <th className="px-4 py-2.5">Period</th>
                <th className="px-4 py-2.5">Status</th>
                <th className="px-4 py-2.5 text-right">Items</th>
                <th className="px-4 py-2.5 text-right">Pending</th>
                <th className="px-4 py-2.5 text-right">Flagged</th>
                <th className="px-4 py-2.5">Created</th>
                <th className="px-4 py-2.5" aria-label="Active" />
              </tr>
            </thead>
            <tbody>
              {cases.map((caseSummary) => {
                const active = caseSummary.case_id === effectiveActive;
                return (
                  <tr
                    key={caseSummary.case_id}
                    onClick={() => open(caseSummary)}
                    className={cn(
                      "cursor-pointer border-b border-slate-100 text-sm last:border-0",
                      active ? "bg-brand-50/50" : "hover:bg-slate-50/60",
                    )}
                  >
                    <td className="px-4 py-3 font-medium text-ink-900">
                      {caseSummary.client_name}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-ink-600">
                      {caseSummary.case_id}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-ink-600">
                      {caseSummary.period_start && caseSummary.period_end
                        ? `${formatDate(caseSummary.period_start)} to ${formatDate(caseSummary.period_end)}`
                        : "-"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <CaseStatusPill status={caseSummary.status} />
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                      {caseSummary.total_review_items}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                      {caseSummary.pending_items}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                      {caseSummary.flagged_items}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-ink-600">
                      {formatTimestamp(caseSummary.created_at)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      {active && (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-brand-800">
                          <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
                          Active
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
