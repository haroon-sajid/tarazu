"use client";

/**
 * Sales analytics: the deterministic readout of the case's sales exports.
 * Every figure was computed by the backend's pandas — this page only chooses
 * which months are in view. Sales exports are uploaded separately from the
 * audit documents, in whatever format the client's software produced; the
 * analysis runs as soon as an upload lands, and the saved readout is what
 * loads on the next visit. The readout says how each file was read and
 * cleaned, and it can leave the product as a workbook.
 */

import * as React from "react";
import { useSearchParams } from "next/navigation";
import {
  ClipboardCheck,
  Download,
  FileSpreadsheet,
  Loader2,
  RotateCw,
  Trash2,
  TrendingUp,
  UploadCloud,
} from "lucide-react";
import {
  ApiError,
  FIXTURE_MODE,
  SALES_DATA_ACCEPT,
  deleteSalesData,
  downloadSalesAnalytics,
  getSalesAnalytics,
  listSalesData,
  runSalesAnalytics,
  uploadSalesData,
} from "@/lib/api";
import type {
  MonthlyRevenue,
  SalesAnalyticsResult,
  SalesDataUploadSummary,
  SourceReadReport,
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

/** Plain words for the reader's skip reasons and canonical field names. */
const SKIP_LABEL: Record<string, string> = {
  blank: "blank rows",
  total_row: "total / subtotal rows",
  no_date: "rows with no readable date",
  no_amount: "rows with no readable amount",
};

const FIELD_LABEL: Record<string, string> = {
  date: "Date",
  amount: "Amount",
  quantity: "Quantity",
  unit_price: "Unit price",
  customer_name: "Customer",
  product: "Product",
  region: "Region",
  sales_row_id: "Row id",
};

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
  const [downloading, setDownloading] = React.useState(false);
  const [downloadError, setDownloadError] = React.useState<string | null>(null);

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
    setDownloadError(null);
    setResult(null);
    setNotRun(false);
    setUploadsError(null);
    setUploadsLoading(true);

    // The uploads come first: a case with no sales export has no readout by
    // definition, so the saved-readout lookup is only made when there is one
    // (fixture mode always has its sample readout to show).
    listSalesData(explicitCaseId)
      .then(async (response) => {
        setUploads(response.uploads);
        if (response.uploads.length === 0 && !FIXTURE_MODE) {
          setNotRun(true);
          return;
        }
        try {
          setResult(await getSalesAnalytics(explicitCaseId));
        } catch (caught) {
          // 404 means the analysis has not been saved for this case yet — a
          // state, not a failure: the run button is the way forward.
          if (caught instanceof ApiError && caught.status === 404) {
            setNotRun(true);
            return;
          }
          setLoadError(
            caught instanceof ApiError
              ? caught.message
              : "Could not load the sales analytics.",
          );
        }
      })
      .catch((caught) => {
        setUploadsError(
          caught instanceof ApiError
            ? caught.message
            : "Could not load the sales data uploads.",
        );
        setNotRun(true);
      })
      .finally(() => setUploadsLoading(false));
  }, [explicitCaseId]);

  React.useEffect(load, [load]);

  const run = React.useCallback(async () => {
    setRunning(true);
    setRunError(null);
    try {
      const fresh = await runSalesAnalytics(explicitCaseId);
      setResult(fresh);
      setNotRun(false);
    } catch (caught) {
      setRunError(
        caught instanceof ApiError
          ? caught.message
          : "Could not run the sales analytics.",
      );
    } finally {
      setRunning(false);
    }
  }, [explicitCaseId]);

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
        setUploading(false);
        setPendingFile(null);
        return;
      }
      setUploading(false);
      setPendingFile(null);
      // The export was read successfully when it was stored; the readout is
      // the next thing the auditor wants, so it runs without another click.
      await run();
    },
    [explicitCaseId, run, uploading],
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

  const download = React.useCallback(
    async (format: "xlsx" | "json") => {
      if (downloading) return;
      setDownloading(true);
      setDownloadError(null);
      try {
        await downloadSalesAnalytics(format, explicitCaseId);
      } catch (caught) {
        setDownloadError(
          caught instanceof ApiError
            ? caught.message
            : "Could not download the sales analytics.",
        );
      } finally {
        setDownloading(false);
      }
    },
    [downloading, explicitCaseId],
  );

  const days = RANGES.find((entry) => entry.key === range)?.days ?? null;
  const months = result
    ? monthsInRange(result.monthly_revenue, result.period_end, days)
    : [];

  const canRun = uploads.length > 0 && !running && !uploading;
  const loading = uploadsLoading || (result === null && !notRun && !loadError);

  if (loadError) {
    return <ErrorState message={loadError} onRetry={load} />;
  }

  return (
    <div className="space-y-4 pb-20 md:pb-0">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-bold text-ink-900">
          <TrendingUp className="h-5 w-5 text-brand-700" aria-hidden />
          Sales analytics
        </h1>
        <p className="mt-1 text-sm text-ink-600">
          Deterministic pandas over the case&apos;s sales exports, a separate
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
      {downloadError && (
        <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
          {downloadError}
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
              Upload the client&apos;s sales export in whatever shape their
              software produced: Excel, OpenDocument, CSV, TSV, or JSON. The
              reader finds the header under any title rows, maps the
              client&apos;s own column names, and says exactly what it skipped.
              The analysis runs as soon as the file lands. These files are not
              audit evidence and do not start the audit pipeline.
            </p>
            <DropZone
              label={
                uploading
                  ? "Reading the export…"
                  : running
                    ? "Analysing…"
                    : "Drop a sales export"
              }
              hint="Excel (.xlsx, .xls, .xlsm), .ods, .csv, .tsv, .txt, or .json · up to 25 MB"
              accept={SALES_DATA_ACCEPT}
              files={pendingFile ? [pendingFile] : []}
              onFiles={handleUpload}
              disabled={uploading || running || uploadsLoading}
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

      {loading || (running && result === null) ? (
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
              ? "Drop the client's sales export above. It is read on arrival, and the readout appears here right away: revenue by month, product, and region, the top customers, and anything anomalous."
              : "Run the analysis to read the uploaded exports and save the readout: revenue by month, product, and region, the top customers, and anything anomalous."
          }
          action={
            uploads.length > 0 ? (
              <Button onClick={() => void run()} disabled={!canRun}>
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
          onRun={() => void run()}
          downloading={downloading}
          onDownload={(format) => void download(format)}
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
  downloading,
  onDownload,
}: {
  result: SalesAnalyticsResult;
  months: MonthlyRevenue[];
  range: RangeKey;
  onRange: (range: RangeKey) => void;
  running: boolean;
  canRun: boolean;
  onRun: () => void;
  downloading: boolean;
  onDownload: (format: "xlsx" | "json") => void;
}) {
  const period =
    result.period_start && result.period_end
      ? `${formatDate(result.period_start)} to ${formatDate(result.period_end)}`
      : null;
  const reports = result.data_quality ?? [];

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
          <Button
            size="sm"
            onClick={() => onDownload("xlsx")}
            disabled={downloading}
            title="Every sheet is copied from this readout; nothing is recomputed"
          >
            {downloading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            ) : (
              <Download className="h-3.5 w-3.5" aria-hidden />
            )}
            Download Excel
          </Button>
          <button
            type="button"
            onClick={() => onDownload("json")}
            disabled={downloading}
            className="text-xs font-medium text-brand-700 hover:underline disabled:opacity-50"
          >
            JSON
          </button>
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

      {reports.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ClipboardCheck className="h-4 w-4 text-brand-700" aria-hidden />
              How the data was read
              <span className="ml-1.5 text-[11px] font-normal text-ink-400">
                nothing was cleaned silently
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {reports.map((report) => (
              <ReadReport key={report.document_id} report={report} />
            ))}
          </CardContent>
        </Card>
      )}

      <p className="text-xs text-ink-400">
        Read from sales exports{" "}
        {result.document_ids.length > 0 ? result.document_ids.join(", ") : "-"} ·
        anomalies are suggestions for a human, never verdicts.
      </p>
    </div>
  );
}

/** One export's cleaning report, in plain words. Every number is the backend's. */
function ReadReport({ report }: { report: SourceReadReport }) {
  const where = [
    report.format.toUpperCase(),
    report.sheet ? `sheet “${report.sheet}”` : null,
    report.encoding && report.encoding !== "utf-8-sig" ? `decoded as ${report.encoding}` : null,
    report.delimiter && report.delimiter !== "," ? `split on ${report.delimiter === "\t" ? "tabs" : `“${report.delimiter}”`}` : null,
    `header on row ${report.header_row}`,
  ]
    .filter(Boolean)
    .join(" · ");
  const skipped = Object.entries(report.skipped);
  const filled = Object.entries(report.filled_defaults);
  const columns = Object.entries(report.columns);

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-3 text-xs">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="min-w-0 break-all font-medium text-ink-900">{report.filename}</p>
        <p className="text-ink-500">
          <span className="font-semibold text-ink-900 tabular-nums">{report.rows_used}</span>{" "}
          of {report.rows_seen} rows used
          {report.rows_skipped > 0 ? ` · ${report.rows_skipped} skipped` : ""}
        </p>
      </div>
      <p className="mt-1 text-ink-500">{where}</p>

      {columns.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {columns.map(([canonical, source]) => (
            <span
              key={canonical}
              className="rounded-full bg-white px-2 py-0.5 text-[11px] text-ink-600 ring-1 ring-slate-200"
            >
              {FIELD_LABEL[canonical] ?? canonical} ← <span className="font-medium text-ink-900">{source}</span>
            </span>
          ))}
        </div>
      )}

      <ul className="mt-2 space-y-0.5 text-ink-600">
        {report.amount_derived && (
          <li>Amount computed as quantity × unit price, row by row, exactly.</li>
        )}
        {skipped.map(([reason, count]) => (
          <li key={reason}>
            Skipped {count} {SKIP_LABEL[reason] ?? reason.replace(/_/g, " ")}.
          </li>
        ))}
        {filled.map(([field, count]) => (
          <li key={field}>
            {count} row{count === 1 ? "" : "s"} had no {FIELD_LABEL[field]?.toLowerCase() ?? field} and were filed under “Unspecified”.
          </li>
        ))}
        {report.warnings.map((warning) => (
          <li key={warning} className="text-amber-700">
            {warning}
          </li>
        ))}
      </ul>
    </div>
  );
}
