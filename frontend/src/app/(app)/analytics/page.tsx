"use client";

/**
 * Sales analytics: the deterministic readout of the case's SALES_DATA export.
 * Every figure was computed by the backend's pandas — this page only chooses
 * which months are in view. Running (or re-running) the analysis is an
 * explicit click, and the saved readout is what loads on the next visit.
 */

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { Loader2, RotateCw, TrendingUp } from "lucide-react";
import { ApiError, getSalesAnalytics, runSalesAnalytics } from "@/lib/api";
import type { MonthlyRevenue, SalesAnalyticsResult } from "@/lib/types";
import { formatDate, formatTimestamp } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { SummaryCards } from "@/components/analytics/summary-cards";
import { RevenueChart } from "@/components/analytics/revenue-chart";
import { ProductChart } from "@/components/analytics/product-chart";
import { RegionChart } from "@/components/analytics/region-chart";
import { CustomerTable } from "@/components/analytics/customer-table";
import { AnomalyList } from "@/components/analytics/anomaly-list";

type RangeKey = "30d" | "90d" | "all";

const RANGES: { key: RangeKey; label: string; days: number | null }[] = [
  { key: "30d", label: "Last 30 days", days: 30 },
  { key: "90d", label: "Last 90 days", days: 90 },
  { key: "all", label: "All", days: null },
];

/**
 * The months whose last day falls inside the window ending at the case's own
 * period end — display slicing of the backend's series, not new math. Months
 * are the grain, so a 30-day window keeps the months it overlaps.
 */
function monthsInRange(
  months: MonthlyRevenue[],
  periodEnd: string | null,
  days: number | null,
): MonthlyRevenue[] {
  if (days === null || months.length === 0) return months;
  const lastMonth = months[months.length - 1].month;
  const anchor = new Date(`${periodEnd ?? `${lastMonth}-01`}T00:00:00Z`);
  const cutoff = new Date(anchor);
  cutoff.setUTCDate(cutoff.getUTCDate() - days + 1);
  return months.filter((entry) => {
    const [year, month] = entry.month.split("-").map(Number);
    // Date.UTC(year, month, 0) is the last day of the month.
    return new Date(Date.UTC(year, month, 0)) >= cutoff;
  });
}

export default function AnalyticsPage() {
  return (
    <React.Suspense>
      <AnalyticsScreen />
    </React.Suspense>
  );
}

function AnalyticsScreen() {
  const searchParams = useSearchParams();
  // ?case= (or ?case_id=) beats the saved selection; the API falls back to it.
  const explicitCaseId =
    searchParams.get("case") ?? searchParams.get("case_id") ?? undefined;

  const [result, setResult] = React.useState<SalesAnalyticsResult | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [notRun, setNotRun] = React.useState(false);
  const [running, setRunning] = React.useState(false);
  const [runError, setRunError] = React.useState<string | null>(null);
  const [range, setRange] = React.useState<RangeKey>("all");

  const load = React.useCallback(() => {
    setLoadError(null);
    setRunError(null);
    setResult(null);
    setNotRun(false);
    getSalesAnalytics(explicitCaseId)
      .then(setResult)
      .catch((caught) => {
        // 404 means the analysis has never been run for this case — a state,
        // not a failure: the run button is the way forward.
        if (caught instanceof ApiError && caught.status === 404) {
          setNotRun(true);
          return;
        }
        setLoadError(
          caught instanceof ApiError
            ? caught.message
            : "Could not load the sales analytics.",
        );
      });
  }, [explicitCaseId]);

  React.useEffect(load, [load]);

  const run = React.useCallback(() => {
    if (running) return;
    setRunning(true);
    setRunError(null);
    runSalesAnalytics(explicitCaseId)
      .then((fresh) => {
        setResult(fresh);
        setNotRun(false);
      })
      .catch((caught) => {
        setRunError(
          caught instanceof ApiError
            ? caught.message
            : "Could not run the sales analytics.",
        );
      })
      .finally(() => setRunning(false));
  }, [explicitCaseId, running]);

  const days = RANGES.find((entry) => entry.key === range)?.days ?? null;
  const months = result
    ? monthsInRange(result.monthly_revenue, result.period_end, days)
    : [];

  if (loadError) {
    return <ErrorState message={loadError} onRetry={load} />;
  }

  if (notRun) {
    return (
      <div className="space-y-4">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-ink-900">
            <TrendingUp className="h-5 w-5 text-brand-700" aria-hidden />
            Sales analytics
          </h1>
          <p className="mt-1 text-sm text-ink-600">
            Deterministic pandas over the case&apos;s sales export — no AI on
            the path, no verdicts, just the arithmetic.
          </p>
        </div>
        {runError && (
          <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
            {runError}
          </p>
        )}
        <EmptyState
          title="No sales analytics for this case yet"
          message="Run the analysis to read the case's sales export and save the readout — revenue by month, product, and region, the top customers, and anything anomalous."
          action={
            <Button onClick={run} disabled={running}>
              {running ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              ) : (
                <RotateCw className="h-3.5 w-3.5" aria-hidden />
              )}
              {running ? "Running…" : "Run the analysis"}
            </Button>
          }
        />
      </div>
    );
  }

  if (result === null) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-56" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-24" />
          ))}
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          <Skeleton className="h-80 lg:col-span-2" />
          <Skeleton className="h-80" />
          <Skeleton className="h-72" />
          <Skeleton className="h-72 lg:col-span-2" />
        </div>
        <Skeleton className="h-40" />
      </div>
    );
  }

  const period =
    result.period_start && result.period_end
      ? `${formatDate(result.period_start)} to ${formatDate(result.period_end)}`
      : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-ink-900">
            <TrendingUp className="h-5 w-5 text-brand-700" aria-hidden />
            Sales analytics
          </h1>
          <p className="mt-1 text-sm text-ink-600">
            {result.record_count} sales records
            {period ? ` · ${period}` : ""} · generated{" "}
            {formatTimestamp(result.generated_at)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex gap-1" role="group" aria-label="Filter by date range">
            {RANGES.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setRange(key)}
                className={cn(
                  "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                  range === key
                    ? "bg-brand-800 text-white"
                    : "bg-slate-100 text-ink-600 hover:bg-slate-200 hover:text-ink-900",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <Button variant="outline" size="sm" onClick={run} disabled={running}>
            {running ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            ) : (
              <RotateCw className="h-3.5 w-3.5" aria-hidden />
            )}
            {running ? "Running…" : "Re-run"}
          </Button>
        </div>
      </div>

      {runError && (
        <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
          {runError}
        </p>
      )}

      <SummaryCards result={result} months={months} />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card className="hover-lift lg:col-span-2">
          <CardHeader>
            <CardTitle>Monthly revenue</CardTitle>
          </CardHeader>
          <CardContent>
            <RevenueChart months={months} />
          </CardContent>
        </Card>
        <Card className="hover-lift">
          <CardHeader>
            <CardTitle>
              Sales by region
              <span className="ml-1.5 text-[11px] font-normal text-ink-400">
                whole period
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <RegionChart regions={result.sales_by_region} />
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card className="hover-lift">
          <CardHeader>
            <CardTitle>
              Revenue by product
              <span className="ml-1.5 text-[11px] font-normal text-ink-400">
                whole period
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ProductChart products={result.revenue_by_product} />
          </CardContent>
        </Card>
        <Card className="hover-lift lg:col-span-2">
          <CardHeader>
            <CardTitle>
              Top customers
              <span className="ml-1.5 text-[11px] font-normal text-ink-400">
                whole period
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <CustomerTable customers={result.top_customers} />
          </CardContent>
        </Card>
      </div>

      <Card className="hover-lift">
        <CardHeader>
          <CardTitle>Anomalies</CardTitle>
        </CardHeader>
        <CardContent>
          <AnomalyList anomalies={result.anomalies} />
        </CardContent>
      </Card>

      <p className="text-xs text-ink-400">
        Read from {result.document_ids.join(", ")} · anomalies are suggestions
        for a human, never verdicts.
      </p>
    </div>
  );
}
