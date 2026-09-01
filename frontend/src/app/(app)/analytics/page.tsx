"use client";

/**
 * Sales analytics: the deterministic readout of the case's sales exports.
 * Every figure was computed by the backend's pandas — this page only chooses
 * which months are in view. Sales data exports are uploaded separately from the
 * audit documents; running (or re-running) the analysis is an explicit click,
 * and the saved readout is what loads on the next visit.
 */

import * as React from "react";
import { useSearchParams } from "next/navigation";
import {
  FileSpreadsheet,
  Loader2,
  RotateCw,
  Trash2,
  TrendingUp,
  UploadCloud,
} from "lucide-react";
import {
  ApiError,
  deleteSalesData,
  getSalesAnalytics,
  listSalesData,
  runSalesAnalytics,
  uploadSalesData,
} from "@/lib/api";
import type {
  MonthlyRevenue,
  SalesAnalyticsResult,
  SalesDataUploadSummary,
} from "@/lib/types";
import { formatDate, formatFileSize, formatTimestamp } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { DropZone } from "@/components/upload/drop-zone";
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

/** Accepted sales export formats, kept in sync with backend/app/api/analytics.py. */
const SALES_DATA_ACCEPT = [".xlsx", ".xlsm", ".xls", ".csv"];

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

  const [uploads, setUploads] = React.useState<SalesDataUploadSummary[]>([]);
  const [uploadsLoading, setUploadsLoading] = React.useState(false);
  const [uploadsError, setUploadsError] = React.useState<string | null>(null);
  const [uploading, setUploading] = React.useState(false);
  const [pendingFile, setPendingFile] = React.useState<File | null>(null);
  const [uploadError, setUploadError] = React.useState<string | null>(null);
  const [deletingId, setDeletingId] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    setLoadError(null);
    setRunError(null);
    setResult(null);
    setNotRun(false);
    setUploadsError(null);
    setUploadsLoading(true);

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

    listSalesData(explicitCaseId)
      .then((response) => setUploads(response.uploads))
      .catch((caught) => {
        setUploadsError(
          caught instanceof ApiError
            ? caught.message
            : "Could not load the sales data uploads.",
        );
      })
      .finally(() => setUploadsLoading(false));
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

  const handleUpload = React.useCallback(
    async (files: File[]) => {
      const file = files[0];
      if (!file || uploading) return;
      setPendingFile(file);
      setUploading(true);
      setUploadError(null);
      try {
        await uploadSalesData(file, explicitCaseId);
        const response = await listSalesData(explicitCaseId);
        setUploads(response.uploads);
      } catch (caught) {
        setUploadError(
          caught instanceof ApiError
            ? caught.message
            : "Could not upload the sales data file.",
        );
      } finally {
        setUploading(false);
        setPendingFile(null);
      }
    },
    [explicitCaseId, uploading],
  );

  const handleDelete = React.useCallback(
    async (salesDataId: string) => {
      if (deletingId) return;
      setDeletingId(salesDataId);
      setUploadError(null);
      try {
        await deleteSalesData(salesDataId, explicitCaseId);
        const response = await listSalesData(explicitCaseId);
        setUploads(response.uploads);
      } catch (caught) {
        setUploadError(
          caught instanceof ApiError
            ? caught.message
            : "Could not delete the sales data file.",
        );
      } finally {
        setDeletingId(null);
      }
    },
    [deletingId, explicitCaseId],
  );

  const days = RANGES.find((entry) => entry.key === range)?.days ?? null;
  const months = result
    ? monthsInRange(result.monthly_revenue, result.period_end, days)
    : [];

  const canRun = uploads.length > 0 && !running;
  const loading = uploadsLoading || (result === null && !notRun);

  if (loadError) {
    return <ErrorState message={loadError} onRetry={load} />;
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-bold text-ink-900">
          <TrendingUp className="h-5 w-5 text-brand-700" aria-hidden />
          Sales analytics
        </h1>
        <p className="mt-1 text-sm text-ink-600">
          Deterministic pandas over the case&apos;s sales exports — a separate
          data source from the audit documents.
        </p>
      </div>

      {runError && (
        <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
          {runError}
        </p>
      )}
      {uploadError && (
        <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
          {uploadError}
        </p>
      )}
      {uploadsError && (
        <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
          {uploadsError}
        </p>
      )}

      {loading ? (
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-40" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-32" />
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileSpreadsheet className="h-4 w-4 text-brand-700" aria-hidden />
              Sales data source
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-ink-600">
              Upload the client&apos;s sales export (Excel or CSV). The analysis
              reads these files only — they are not audit evidence and do not
              start the audit pipeline.
            </p>
            <DropZone
              label={uploading ? "Uploading sales export..." : "Drop a sales export"}
              hint="Excel (.xlsx, .xlsm, .xls) or CSV, up to 25 MB"
              accept={SALES_DATA_ACCEPT}
              files={pendingFile ? [pendingFile] : []}
              onFiles={handleUpload}
              disabled={uploading || uploadsLoading}
            />
            {uploads.length > 0 && (
              <ul className="space-y-2">
                {uploads.map((upload) => (
                  <li
                    key={upload.sales_data_id}
                    className="flex items-center justify-between gap-3 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <UploadCloud
                        className="h-3.5 w-3.5 shrink-0 text-ink-400"
                        aria-hidden
                      />
                      <span className="truncate font-medium text-ink-900">
                        {upload.filename}
                      </span>
                      <span className="shrink-0 text-ink-400">
                        {formatFileSize(upload.size_bytes)}
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2 text-ink-400">
                      <span className="hidden sm:inline">
                        {formatTimestamp(upload.uploaded_at)}
                      </span>
                      <button
                        onClick={() => handleDelete(upload.sales_data_id)}
                        disabled={deletingId === upload.sales_data_id}
                        className="rounded p-1 hover:bg-rose-50 hover:text-rose-600 disabled:opacity-50"
                        aria-label={`Delete ${upload.filename}`}
                      >
                        {deletingId === upload.sales_data_id ? (
                          <Loader2
                            className="h-3.5 w-3.5 animate-spin"
                            aria-hidden
                          />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5" aria-hidden />
                        )}
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}

      {loading ? (
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
      ) : notRun ? (
        <EmptyState
          title={
            uploads.length === 0
              ? "Upload sales data first"
              : "No sales analytics for this case yet"
          }
          message={
            uploads.length === 0
              ? "Sales analytics needs at least one sales export before it can compute the readout."
              : "Run the analysis to read the uploaded exports and save the readout — revenue by month, product, and region, the top customers, and anything anomalous."
          }
          action={
            uploads.length > 0 ? (
              <Button onClick={run} disabled={!canRun}>
                {running ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                ) : (
                  <RotateCw className="h-3.5 w-3.5" aria-hidden />
                )}
                {running ? "Running…" : "Run the analysis"}
              </Button>
            ) : undefined
          }
        />
      ) : result === null ? null : (
        <AnalyticsResult
          result={result}
          months={months}
          range={range}
          onRange={setRange}
          running={running}
          canRun={canRun}
          onRun={run}
        />
      )}
    </div>
  );
}

function AnalyticsResult({
  result,
  months,
  range,
  onRange,
  running,
  canRun,
  onRun,
}: {
  result: SalesAnalyticsResult;
  months: MonthlyRevenue[];
  range: RangeKey;
  onRange: (range: RangeKey) => void;
  running: boolean;
  canRun: boolean;
  onRun: () => void;
}) {
  const period =
    result.period_start && result.period_end
      ? `${formatDate(result.period_start)} to ${formatDate(result.period_end)}`
      : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-ink-900">Analysis readout</h2>
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
                onClick={() => onRange(key)}
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
          <Button variant="outline" size="sm" onClick={onRun} disabled={!canRun}>
            {running ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            ) : (
              <RotateCw className="h-3.5 w-3.5" aria-hidden />
            )}
            {running ? "Running…" : "Re-run"}
          </Button>
        </div>
      </div>

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
        Read from sales exports{" "}
        {result.document_ids.length > 0 ? result.document_ids.join(", ") : "—"} ·
        anomalies are suggestions for a human, never verdicts.
      </p>
    </div>
  );
}
