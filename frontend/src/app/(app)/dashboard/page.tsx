"use client";

/**
 * The dashboard: the screen that sells the numbers. Every figure is counted by
 * the backend from deterministic results — nothing on this page is estimated
 * by a model, and nothing is computed client-side.
 */

import * as React from "react";
import Link from "next/link";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  DollarSign,
  Layers,
  Package,
} from "lucide-react";
import { ApiError, getDashboard, listReports } from "@/lib/api";
import type {
  DashboardSummary,
  MonthlyRevenue,
  ReadinessComponent,
  SalesAnalyticsResult,
} from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { SeverityBadge } from "@/components/ui/badge";
import { BenfordChart } from "@/components/dashboard/benford-chart";
import { FirstRunChecklist } from "@/components/dashboard/first-run-checklist";
import { formatDate } from "@/lib/format";

/**
 * Mini revenue trend chart: pure SVG bars, one per month. No chart library
 * needed for six bars — the determinism guarantee means the same data always
 * renders the same picture.
 */
function RevenueTrendChart({ monthly }: { monthly: MonthlyRevenue[] }) {
  if (monthly.length === 0) return null;
  const maxRevenue = Math.max(...monthly.map((m) => m.revenue), 1);
  const barWidth = 32;
  const gap = 8;
  const chartHeight = 100;
  const chartWidth = monthly.length * (barWidth + gap) - gap;

  return (
    <div className="overflow-x-auto" role="img" aria-label="Monthly revenue trend chart">
      <svg
        width={chartWidth + 40}
        height={chartHeight + 36}
        viewBox={`0 0 ${chartWidth + 40} ${chartHeight + 36}`}
        className="min-w-0"
      >
        {monthly.map((entry, index) => {
          const height = Math.max(2, (entry.revenue / maxRevenue) * chartHeight);
          const x = index * (barWidth + gap) + 20;
          const y = chartHeight - height + 4;
          const label = entry.month.slice(5); // "MM" from "YYYY-MM"
          return (
            <g key={entry.month}>
              <title>{`${entry.month}: ${formatCurrency(entry.revenue)}`}</title>
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={height}
                rx={3}
                className="fill-brand-600 transition-colors hover:fill-brand-800"
              />
              <text
                x={x + barWidth / 2}
                y={chartHeight + 18}
                textAnchor="middle"
                className="fill-ink-400 text-[10px]"
              >
                {label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/**
 * Format a number as PKR currency for display. No AI, just Intl.
 */
function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-PK", {
    style: "decimal",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

/**
 * The Sales Overview section: three summary cards and a revenue trend chart.
 * Renders nothing when no sales analytics are available — the dashboard is
 * complete without them.
 */
function SalesOverview({ analytics }: { analytics: SalesAnalyticsResult }) {
  const topProduct = analytics.revenue_by_product[0];
  const anomalyCount = analytics.anomalies.length;

  return (
    <>
      {/* Sales summary cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card className="hover-lift">
          <CardContent className="flex items-start justify-between px-5 py-4">
            <div className="min-w-0">
              <p className="text-xs font-medium text-ink-400">Total Revenue</p>
              <p className="mt-1 text-2xl font-bold text-ink-900 tabular-nums">
                {formatCurrency(analytics.total_revenue)}
              </p>
              <p className="mt-0.5 text-[11px] text-ink-400">
                {analytics.record_count} transactions ·{" "}
                {analytics.period_start && analytics.period_end
                  ? `${analytics.period_start} to ${analytics.period_end}`
                  : "no period"}
              </p>
            </div>
            <span className="rounded-lg bg-gradient-to-br from-emerald-50 to-emerald-100 p-2.5 text-emerald-600 shadow-sm">
              <DollarSign className="h-5 w-5" aria-hidden />
            </span>
          </CardContent>
        </Card>

        <Card className="hover-lift">
          <CardContent className="flex items-start justify-between px-5 py-4">
            <div className="min-w-0">
              <p className="text-xs font-medium text-ink-400">Top Product</p>
              <p className="mt-1 break-words text-2xl font-bold text-ink-900">
                {topProduct ? topProduct.product : "-"}
              </p>
              {topProduct && (
                <p className="mt-0.5 text-[11px] text-ink-400">
                  {formatCurrency(topProduct.revenue)} · {topProduct.share.toFixed(1)}% of total
                </p>
              )}
            </div>
            <span className="rounded-lg bg-gradient-to-br from-brand-50 to-brand-100 p-2.5 text-brand-700 shadow-sm">
              <Package className="h-5 w-5" aria-hidden />
            </span>
          </CardContent>
        </Card>

        <Card className="hover-lift">
          <CardContent className="flex items-start justify-between px-5 py-4">
            <div className="min-w-0">
              <p className="text-xs font-medium text-ink-400">Anomalies</p>
              <p className="mt-1 text-2xl font-bold text-ink-900 tabular-nums">
                {anomalyCount}
              </p>
              <p className="mt-0.5 text-[11px] text-ink-400">
                {anomalyCount === 0
                  ? "No anomalies detected"
                  : `${anomalyCount} finding${anomalyCount > 1 ? "s" : ""} to review`}
              </p>
            </div>
            <span
              className={
                anomalyCount > 0
                  ? "rounded-lg bg-gradient-to-br from-amber-50 to-amber-100 p-2.5 text-amber-600 shadow-sm"
                  : "rounded-lg bg-gradient-to-br from-slate-50 to-slate-100 p-2.5 text-slate-500 shadow-sm"
              }
            >
              <AlertCircle className="h-5 w-5" aria-hidden />
            </span>
          </CardContent>
        </Card>
      </div>

      {/* Revenue trend chart */}
      {analytics.monthly_revenue.length > 0 && (
        <Card className="hover-lift">
          <CardHeader>
            <CardTitle>Revenue trend</CardTitle>
          </CardHeader>
          <CardContent>
            <RevenueTrendChart monthly={analytics.monthly_revenue} />
            {anomalyCount > 0 && (
              <ul className="mt-4 space-y-1.5 border-t border-slate-100 pt-3">
                {analytics.anomalies.map((anomaly) => (
                  <li
                    key={anomaly.anomaly_id}
                    className="flex items-start gap-2 text-xs text-ink-600"
                  >
                    <AlertTriangle
                      className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500"
                      aria-hidden
                    />
                    <span>
                      <span className="font-medium text-ink-900">{anomaly.kind}</span>:{" "}
                      {anomaly.explanation}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}
    </>
  );
}

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
      <CardContent className="flex items-start justify-between gap-2 px-3.5 py-3.5 sm:px-5 sm:py-4">
        <div className="min-w-0">
          <p className="text-xs font-medium leading-tight text-ink-400">{label}</p>
          <p className="mt-1 text-xl font-bold text-ink-900 tabular-nums sm:text-2xl">{value}</p>
          {detail && <p className="mt-0.5 text-[11px] leading-snug text-ink-400">{detail}</p>}
        </div>
        <span
          className={
            tone === "good"
              ? "hidden shrink-0 rounded-lg bg-gradient-to-br from-emerald-50 to-emerald-100 p-2.5 text-emerald-600 shadow-sm sm:inline"
              : tone === "warn"
                ? "hidden shrink-0 rounded-lg bg-gradient-to-br from-purple-50 to-purple-100 p-2.5 text-purple-600 shadow-sm sm:inline"
                : "hidden shrink-0 rounded-lg bg-gradient-to-br from-brand-50 to-brand-100 p-2.5 text-brand-700 shadow-sm sm:inline"
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
  const [noCases, setNoCases] = React.useState(false);
  // Only for the first-run checklist: whether this case has ever produced a
  // report. A failure here is not worth an error state — the checklist simply
  // shows that step as outstanding.
  const [hasReport, setHasReport] = React.useState(false);

  const load = React.useCallback(() => {
    setError(null);
    setSummary(null);
    setNoCases(false);
    listReports()
      .then((reports) => setHasReport(reports.total > 0))
      .catch(() => setHasReport(false));
    getDashboard()
      .then(setSummary)
      .catch((caught) => {
        // "No cases yet" is a state, not a failure: show the upload CTA.
        if (caught instanceof ApiError && caught.status === 404) {
          setNoCases(true);
          return;
        }
        setError(
          caught instanceof ApiError ? caught.message : "Could not load the dashboard.",
        );
      });
  }, []);

  React.useEffect(load, [load]);

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  if (noCases) {
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

  if (summary === null) {
    return (
      <div className="space-y-4 pb-20 md:pb-0">
        <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-24" />
          ))}
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Skeleton className="lg:col-span-2 h-80" />
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
      ? `${formatDate(summary.period_start)} to ${formatDate(summary.period_end)}`
      : undefined;

  return (
    <div className="space-y-4 pb-20 md:pb-0">
      <div className="flex items-end justify-between">
        <div className="min-w-0">
          <h1 className="break-words text-xl font-bold text-ink-900">{summary.client_name}</h1>
          <p className="mt-1 break-words text-xs text-ink-600 sm:text-sm">
            {summary.case_id}
            {period ? ` · ${period}` : ""}
          </p>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Benford */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Benford&apos;s Law: first-digit distribution</CardTitle>
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

      {/* Sales Overview — shown only when sales analytics ran */}
      {summary.sales_analytics && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold text-ink-900">Sales Overview</h2>
            <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-ink-400">
              deterministic · no AI
            </span>
            <Link
              href="/analytics"
              className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-brand-700 hover:underline"
            >
              Full analytics
              <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </Link>
          </div>
          <SalesOverview analytics={summary.sales_analytics} />
        </>
      )}

      {/* Next best actions */}
      <Card>
        <CardHeader>
          <CardTitle>Next best actions</CardTitle>
        </CardHeader>
        <CardContent>
          {summary.next_best_actions.length === 0 ? (
            <p className="text-sm text-ink-400">
              Nothing outstanding: every flag sits on a decided item.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {summary.next_best_actions.map((action, index) => (
                <li key={`${action.review_item_id}-${action.rule_id}-${index}`}>
                  <Link
                    href={`/review?item=${encodeURIComponent(action.review_item_id)}`}
                    className="group flex items-center justify-between gap-3 py-2.5"
                  >
                    <span className="flex min-w-0 items-center gap-2 sm:gap-3">
                      <SeverityBadge severity={action.severity} />
                      <span className="truncate text-sm text-ink-900 transition-colors group-hover:text-brand-700">
                        {action.action}
                      </span>
                      <span className="hidden shrink-0 font-mono text-[10px] text-ink-400 sm:inline">
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

      <FirstRunChecklist
        hasCase
        hasDecisions={summary.decisions.approved + summary.decisions.rejected > 0}
        hasReport={hasReport}
      />
    </div>
  );
}
