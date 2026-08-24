"use client";

/**
 * The dashboard: the screen that sells the numbers. Every figure is counted by
 * the backend from deterministic results — nothing on this page is estimated
 * by a model, and nothing is computed client-side.
 */

import * as React from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Layers,
} from "lucide-react";
import { ApiError, getDashboard } from "@/lib/api";
import type { DashboardSummary, ReadinessComponent } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { SeverityBadge } from "@/components/ui/badge";
import { BenfordChart } from "@/components/dashboard/benford-chart";
import { formatDate } from "@/lib/format";

function StatCard({
  label,
  value,
  detail,
  icon: Icon,
  tone = "default",
}: {
  label: string;
  value: string;
  detail?: string;
  icon: React.ComponentType<{ className?: string }>;
  tone?: "default" | "good" | "warn";
}) {
  return (
    <Card>
      <CardContent className="flex items-start justify-between px-5 py-4">
        <div>
          <p className="text-xs font-medium text-ink-400">{label}</p>
          <p className="mt-1 text-2xl font-bold text-ink-900 tabular-nums">{value}</p>
          {detail && <p className="mt-0.5 text-[11px] text-ink-400">{detail}</p>}
        </div>
        <span
          className={
            tone === "good"
              ? "rounded-md bg-emerald-50 p-2 text-emerald-600"
              : tone === "warn"
                ? "rounded-md bg-purple-50 p-2 text-purple-600"
                : "rounded-md bg-brand-50 p-2 text-brand-700"
          }
        >
          <Icon className="h-5 w-5" aria-hidden />
        </span>
      </CardContent>
    </Card>
  );
}

function ReadinessRow({
  label,
  component,
}: {
  label: string;
  component: ReadinessComponent;
}) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="font-medium text-ink-600">{label}</span>
        <span className="text-ink-400 tabular-nums">
          {component.count} of {component.total} · {component.percent.toFixed(0)}%
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-brand-700"
          style={{ width: `${component.percent}%` }}
        />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [summary, setSummary] = React.useState<DashboardSummary | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    setError(null);
    setSummary(null);
    getDashboard()
      .then(setSummary)
      .catch((caught) =>
        setError(
          caught instanceof ApiError ? caught.message : "Could not load the dashboard.",
        ),
      );
  }, []);

  React.useEffect(load, [load]);

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  if (summary === null) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-24" />
          ))}
        </div>
        <div className="grid grid-cols-3 gap-4">
          <Skeleton className="col-span-2 h-80" />
          <Skeleton className="h-80" />
        </div>
      </div>
    );
  }

  if (summary.total_review_items === 0) {
    return (
      <EmptyState
        title="No data yet"
        message="Upload a bank statement, invoices, and a ledger to begin."
        action={
          <Link
            href="/upload"
            className="text-sm font-medium text-brand-700 hover:underline"
          >
            Go to upload →
          </Link>
        }
      />
    );
  }

  const matchedPercent = Math.round(
    (summary.match_status.matched / summary.total_review_items) * 100,
  );
  const period =
    summary.period_start && summary.period_end
      ? `${formatDate(summary.period_start)} – ${formatDate(summary.period_end)}`
      : undefined;

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink-900">{summary.client_name}</h1>
          <p className="mt-1 text-sm text-ink-600">
            {summary.case_id}
            {period ? ` · ${period}` : ""}
          </p>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard
          label="Total review items"
          value={String(summary.total_review_items)}
          detail={`${summary.decisions.pending} pending · ${summary.decisions.approved} approved · ${summary.decisions.rejected} rejected`}
          icon={Layers}
        />
        <StatCard
          label="Matched"
          value={`${matchedPercent}%`}
          detail={`${summary.match_status.matched} matched · ${summary.match_status.partial} partial · ${summary.match_status.unmatched} unmatched`}
          icon={CheckCircle2}
          tone="good"
        />
        <StatCard
          label="Flags raised"
          value={String(summary.total_flags)}
          detail={`${summary.flags_by_severity.high} high · ${summary.flags_by_severity.medium} medium · ${summary.flags_by_severity.low} low`}
          icon={AlertTriangle}
          tone="warn"
        />
        <StatCard
          label="Estimated hours saved"
          value={summary.estimated_hours_saved.toFixed(1)}
          detail="vs. fully manual reconciliation"
          icon={Clock3}
        />
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Benford */}
        <Card className="col-span-2">
          <CardHeader>
            <CardTitle>Benford&apos;s Law — first-digit distribution</CardTitle>
          </CardHeader>
          <CardContent>
            {summary.benford ? (
              <BenfordChart benford={summary.benford} />
            ) : (
              <p className="py-10 text-center text-sm text-ink-400">
                Benford analysis is not available for this case yet.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Readiness + data confidence */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Audit readiness</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-4xl font-bold text-brand-900 tabular-nums">
                {summary.audit_readiness_score.score}
                <span className="text-base font-medium text-ink-400"> / 100</span>
              </p>
              <div className="mt-4 space-y-3">
                <ReadinessRow
                  label="Matched"
                  component={summary.audit_readiness_score.matched}
                />
                <ReadinessRow
                  label="Flags reviewed"
                  component={summary.audit_readiness_score.flags_reviewed}
                />
                <ReadinessRow
                  label="Completeness"
                  component={summary.audit_readiness_score.completeness}
                />
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Data confidence</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed text-ink-600">
                {summary.data_confidence}
              </p>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Next best actions */}
      <Card>
        <CardHeader>
          <CardTitle>Next best actions</CardTitle>
        </CardHeader>
        <CardContent>
          {summary.next_best_actions.length === 0 ? (
            <p className="text-sm text-ink-400">
              Nothing outstanding — every flag sits on a decided item.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {summary.next_best_actions.map((action, index) => (
                <li key={`${action.review_item_id}-${action.rule_id}-${index}`}>
                  <Link
                    href={`/review?item=${encodeURIComponent(action.review_item_id)}`}
                    className="group flex items-center justify-between gap-3 py-2.5"
                  >
                    <span className="flex min-w-0 items-center gap-3">
                      <SeverityBadge severity={action.severity} />
                      <span className="truncate text-sm text-ink-900 group-hover:text-brand-800">
                        {action.action}
                      </span>
                      <span className="shrink-0 font-mono text-[10px] text-ink-400">
                        {action.rule_id}
                      </span>
                    </span>
                    <ArrowRight
                      className="h-4 w-4 shrink-0 text-ink-400 group-hover:text-brand-700"
                      aria-hidden
                    />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
