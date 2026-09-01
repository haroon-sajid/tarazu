"use client";

/**
 * Audit trail — the case's spine, rendered as one timeline. Every action by
 * a human, the AI, or a machine credential, in order, with nothing editable
 * anywhere on the screen: the trail is append-only in the stores and this
 * page only reads it.
 */

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  Bot,
  CircleUserRound,
  KeyRound,
  ShieldCheck,
} from "lucide-react";
import { ApiError, getAuditTrail } from "@/lib/api";
import type { ActorType, AuditRecord } from "@/lib/types";
import { formatTimestamp } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";

type ActorFilter = "all" | ActorType;

const ACTOR_FILTERS: { value: ActorFilter; label: string }[] = [
  { value: "all", label: "All actors" },
  { value: "human", label: "Human" },
  { value: "ai", label: "AI" },
  { value: "system", label: "System" },
];

function actorIcon(record: AuditRecord) {
  if (record.actor_id.startsWith("api-key:")) return KeyRound;
  if (record.actor_type === "human") return CircleUserRound;
  return Bot;
}

function actorLabel(record: AuditRecord): string {
  if (record.actor_id.startsWith("api-key:")) {
    return `API key ${record.actor_id.slice("api-key:".length)}`;
  }
  return record.actor_id;
}

const ACTION_TONE: Record<string, string> = {
  item_approved: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  item_rejected: "bg-rose-50 text-rose-700 ring-rose-200",
  flag_raised: "bg-purple-50 text-purple-700 ring-purple-200",
};

export default function AuditTrailPage() {
  const [records, setRecords] = React.useState<AuditRecord[] | null>(null);
  const [caseId, setCaseId] = React.useState<string | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [noCases, setNoCases] = React.useState(false);
  const [actorFilter, setActorFilter] = React.useState<ActorFilter>("all");
  const [actionFilter, setActionFilter] = React.useState<string>("all");

  const load = React.useCallback(() => {
    setLoadError(null);
    setRecords(null);
    setNoCases(false);
    getAuditTrail()
      .then((response) => {
        setRecords(response.records);
        setCaseId(response.case_id);
      })
      .catch((caught) => {
        if (caught instanceof ApiError && caught.status === 404) {
          setNoCases(true);
          return;
        }
        setLoadError(
          caught instanceof ApiError ? caught.message : "Could not load the trail.",
        );
      });
  }, []);

  React.useEffect(load, [load]);

  const actions = React.useMemo(
    () => Array.from(new Set((records ?? []).map((record) => record.action))),
    [records],
  );

  const visible = (records ?? []).filter((record) => {
    if (actorFilter !== "all") {
      // The api-key actor is recorded as `system`; the filter follows suit.
      if (record.actor_type !== actorFilter) return false;
    }
    if (actionFilter !== "all" && record.action !== actionFilter) return false;
    return true;
  });

  return (
    <div className="pb-20 md:pb-0">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-ink-900">
            <ShieldCheck className="h-5 w-5 text-brand-700" aria-hidden />
            Audit trail
          </h1>
          <p className="mt-1 text-sm text-ink-600">
            Every action on this case, in order, forever. Records are
            append-only: nothing on this screen, or anywhere else, can change
            or remove one.
          </p>
        </div>
        {records && (
          <p className="text-xs text-ink-400">
            {caseId} · {records.length} record{records.length === 1 ? "" : "s"}
          </p>
        )}
      </div>

      {noCases ? (
        <EmptyState
          title="No case yet"
          message="The trail starts with the first upload. Open a case to begin."
        />
      ) : loadError ? (
        <ErrorState message={loadError} onRetry={load} />
      ) : records === null ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-12 w-full" />
          ))}
        </div>
      ) : (
        <>
          {/* Filters */}
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <div className="flex gap-1" role="group" aria-label="Filter by actor">
              {ACTOR_FILTERS.map(({ value, label }) => (
                <button
                  key={value}
                  onClick={() => setActorFilter(value)}
                  className={cn(
                    "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                    actorFilter === value
                      ? "bg-brand-800 text-white"
                      : "bg-slate-100 text-ink-600 hover:bg-slate-200 hover:text-ink-900",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            {actions.length > 1 && (
              <select
                value={actionFilter}
                onChange={(event) => setActionFilter(event.target.value)}
                aria-label="Filter by action"
                className="h-8 rounded-full border border-slate-300 bg-white px-3 text-xs text-ink-900 focus:border-brand-600 focus:outline-none"
              >
                <option value="all">All actions</option>
                {actions.map((action) => (
                  <option key={action} value={action}>
                    {action.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            )}
            <span className="text-xs text-ink-400">
              {visible.length} shown
            </span>
          </div>

          {visible.length === 0 ? (
            <EmptyState
              title={records.length === 0 ? "Nothing recorded yet" : "No records match"}
              message={
                records.length === 0
                  ? "Actions land here as they happen: decisions, uploads, extraction, flags."
                  : "No record matches the current filters."
              }
            />
          ) : (
            <ol className="relative space-y-0 border-l border-slate-200 pl-6">
              {visible.map((record) => {
                const Icon = actorIcon(record);
                return (
                  <li key={record.audit_id} className="relative pb-5 last:pb-0">
                    <span
                      className={cn(
                        "absolute -left-[35px] flex h-[22px] w-[22px] items-center justify-center rounded-full bg-white ring-1 ring-slate-200",
                      )}
                    >
                      <Icon className="h-3 w-3 text-ink-400" aria-hidden />
                    </span>
                    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={cn(
                            "rounded-full px-2 py-0.5 text-[11px] font-medium ring-1",
                            ACTION_TONE[record.action] ??
                              "bg-slate-100 text-ink-600 ring-slate-200",
                          )}
                        >
                          {record.action.replace(/_/g, " ")}
                        </span>
                        <span className="min-w-0 break-words text-xs text-ink-600">
                          by <span className="font-medium text-ink-900">{actorLabel(record)}</span>
                        </span>
                        <span className="ml-auto text-[11px] text-ink-400">
                          {formatTimestamp(record.occurred_at)}
                        </span>
                      </div>
                      {record.detail && (
                        <p className="mt-1.5 break-words text-xs leading-relaxed text-ink-600">
                          “{record.detail}”
                        </p>
                      )}
                      {record.item_id && (
                        <Link
                          href={`/review?item=${encodeURIComponent(record.item_id)}`}
                          className="mt-1.5 inline-flex items-center gap-1 font-mono text-[10px] text-brand-700 hover:underline"
                        >
                          {record.item_id}
                          <ArrowRight className="h-3 w-3" aria-hidden />
                        </Link>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </>
      )}
    </div>
  );
}
