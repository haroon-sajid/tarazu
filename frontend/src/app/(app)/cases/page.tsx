"use client";

/**
 * Cases — every engagement the firm has open, and the switch that decides
 * which one the workspace screens (dashboard, documents, review, assistant,
 * audit trail, reports) are about. The selection lives in this browser only;
 * the backend re-checks tenancy on the id with every request.
 *
 * Each row carries two actions of its own: rename (or correct the period) and
 * delete. Both call the case routes directly — an edit updates the row in
 * place, a delete asks first, because it removes the engagement's working
 * data for good. The audit trail of what was changed or removed is append-only
 * and outlives the case.
 */

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle2, Loader2, Plus, SquarePen, Trash2 } from "lucide-react";
import {
  ApiError,
  deleteCase,
  getActiveCaseId,
  listCases,
  refreshWorkspace,
  setActiveCaseId,
  updateCase,
} from "@/lib/api";
import type { CaseStatus, CaseSummary } from "@/lib/types";
import { formatDate, formatTimestamp } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
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

  const [editing, setEditing] = React.useState<CaseSummary | null>(null);
  const [editName, setEditName] = React.useState("");
  const [editStart, setEditStart] = React.useState("");
  const [editEnd, setEditEnd] = React.useState("");
  const [editBusy, setEditBusy] = React.useState(false);
  const [editError, setEditError] = React.useState<string | null>(null);

  const [deleting, setDeleting] = React.useState<CaseSummary | null>(null);
  const [deleteBusy, setDeleteBusy] = React.useState(false);
  const [deleteError, setDeleteError] = React.useState<string | null>(null);

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

  const startEdit = (caseSummary: CaseSummary) => {
    setEditError(null);
    setEditName(caseSummary.client_name);
    setEditStart(caseSummary.period_start ?? "");
    setEditEnd(caseSummary.period_end ?? "");
    setEditing(caseSummary);
  };

  const submitEdit = async () => {
    if (!editing || editBusy || !editName.trim()) return;
    if (editStart && editEnd && editEnd < editStart) {
      setEditError("The period cannot end before it starts.");
      return;
    }
    setEditBusy(true);
    setEditError(null);
    try {
      const updated = await updateCase(editing.case_id, {
        client_name: editName.trim(),
        period_start: editStart || null,
        period_end: editEnd || null,
      });
      setCases((current) =>
        current
          ? current.map((item) => (item.case_id === updated.case_id ? updated : item))
          : current,
      );
      setEditing(null);
      // The active case's name is on the dashboard and in the header chip;
      // remount the workspace so both retell the truth.
      if (updated.case_id === effectiveActive) refreshWorkspace();
    } catch (caught) {
      setEditError(
        caught instanceof ApiError ? caught.message : "Could not save the case.",
      );
    } finally {
      setEditBusy(false);
    }
  };

  const submitDelete = async () => {
    if (!deleting || deleteBusy) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      const gone = await deleteCase(deleting.case_id);
      setDeleting(null);
      setCases((current) =>
        current ? current.filter((item) => item.case_id !== gone.case_id) : current,
      );
      if (getActiveCaseId() === gone.case_id) {
        // The saved selection just evaporated: drop it and let every screen
        // fall back to the newest remaining case.
        setActiveCaseId(null);
      } else {
        refreshWorkspace();
      }
    } catch (caught) {
      setDeleteError(
        caught instanceof ApiError ? caught.message : "Could not delete the case.",
      );
    } finally {
      setDeleteBusy(false);
    }
  };

  return (
    <div>
      <div className="mb-5 flex items-end justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink-900">Cases</h1>
          <p className="mt-1 text-sm text-ink-600">
            Every engagement in your firm. Open one to point the whole
            workspace (dashboard, documents, review, and reports) at it; rename
            or delete it from the row actions.
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
          <table className="w-full min-w-[1040px] text-left">
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
                <th className="px-4 py-2.5 text-right" aria-label="Actions" />
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
                    <td className="whitespace-nowrap px-4 py-3 text-right">
                      <span className="inline-flex items-center gap-1">
                        <button
                          onClick={(event) => {
                            event.stopPropagation();
                            startEdit(caseSummary);
                          }}
                          title={`Rename “${caseSummary.client_name}” or correct its period`}
                          aria-label={`Rename ${caseSummary.client_name}`}
                          className="rounded-md p-1.5 text-ink-600 transition-colors hover:bg-slate-100 hover:text-ink-900"
                        >
                          <SquarePen className="h-4 w-4" aria-hidden />
                        </button>
                        <button
                          onClick={(event) => {
                            event.stopPropagation();
                            setDeleteError(null);
                            setDeleting(caseSummary);
                          }}
                          title={`Delete “${caseSummary.client_name}” and its working data`}
                          aria-label={`Delete ${caseSummary.client_name}`}
                          className="rounded-md p-1.5 text-red-500 transition-colors hover:bg-rose-50 hover:text-red-600"
                        >
                          <Trash2 className="h-4 w-4" aria-hidden />
                        </button>
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Rename / correct the period */}
      <Dialog
        open={editing !== null}
        onClose={() => !editBusy && setEditing(null)}
        title={`Edit “${editing?.client_name ?? ""}”`}
      >
        <div className="space-y-4">
          <Input
            label="Client name"
            autoFocus
            maxLength={200}
            value={editName}
            onChange={(event) => setEditName(event.target.value)}
            placeholder="Haroon Textiles"
            hint="The client this engagement audits, shown on every screen and report."
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Period start"
              type="date"
              value={editStart}
              onChange={(event) => setEditStart(event.target.value)}
            />
            <Input
              label="Period end"
              type="date"
              value={editEnd}
              onChange={(event) => setEditEnd(event.target.value)}
            />
          </div>
          <p className="text-[11px] text-ink-400">
            The status, creator, and timestamps are facts the pipeline records;
            they are not editable here. The change is written to the case's
            audit trail.
          </p>
          {editError && (
            <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
              {editError}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEditing(null)}
              disabled={editBusy}
            >
              Cancel
            </Button>
            <Button size="sm" onClick={submitEdit} disabled={editBusy || !editName.trim()}>
              {editBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
              Save
            </Button>
          </div>
        </div>
      </Dialog>

      {/* Delete confirmation — permanent, the working data goes */}
      <Dialog
        open={deleting !== null}
        onClose={() => !deleteBusy && setDeleting(null)}
        title={`Delete “${deleting?.client_name ?? ""}”?`}
      >
        <p className="text-sm text-ink-600">
          This removes the engagement and its working data — documents,
          extractions, the review queue, flags, and the Benford analysis — for
          good. Generated reports and the audit trail are append-only evidence:
          they outlive the case, and the deletion itself is recorded in the
          trail.
        </p>
        {deleteError && (
          <p className="mt-3 rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
            {deleteError}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setDeleting(null)}
            disabled={deleteBusy}
          >
            Cancel
          </Button>
          <Button variant="danger" size="sm" onClick={submitDelete} disabled={deleteBusy}>
            {deleteBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
            Delete case
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
