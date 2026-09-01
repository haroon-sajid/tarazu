"use client";

/**
 * Business view — the dedicated owner-facing screen.
 *
 * This is not the auditor's dashboard. It shows the same counts, but in plain
 * language and with the Urdu executive summary when the client record says the
 * owner reads Urdu. The emphasis is on what was checked, what was decided, and
 * what the business can download.
 */

import * as React from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileText,
  HelpCircle,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { ApiError, downloadReport, getBusinessSummary } from "@/lib/api";
import type { BusinessSummary } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { formatDate, formatTimestamp } from "@/lib/format";

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
  tone?: "default" | "good" | "warn" | "bad";
}) {
  const toneClass =
    tone === "good"
      ? "from-emerald-50 to-emerald-100 text-emerald-600"
      : tone === "warn"
        ? "from-amber-50 to-amber-100 text-amber-600"
        : tone === "bad"
          ? "from-rose-50 to-rose-100 text-rose-600"
          : "from-brand-50 to-brand-100 text-brand-700";
  return (
    <Card>
      <CardContent className="flex items-start justify-between gap-2 px-3.5 py-3.5 sm:px-5 sm:py-4">
        <div className="min-w-0">
          <p className="text-xs font-medium leading-tight text-ink-400">{label}</p>
          <p className="mt-1 break-words text-xl font-bold text-ink-900 tabular-nums sm:text-2xl">
            {value}
          </p>
          {detail && <p className="mt-0.5 text-[11px] leading-snug text-ink-400">{detail}</p>}
        </div>
        <span
          className={`hidden shrink-0 rounded-lg bg-gradient-to-br p-2.5 shadow-sm sm:inline ${toneClass}`}
        >
          <Icon className="h-5 w-5" aria-hidden />
        </span>
      </CardContent>
    </Card>
  );
}

function DownloadReport({ summary }: { summary: BusinessSummary }) {
  const [downloading, setDownloading] = React.useState<"pdf" | "excel" | null>(null);
  if (!summary.latest_report) return null;

  const handle = async (format: "pdf" | "excel") => {
    setDownloading(format);
    try {
      await downloadReport(summary.latest_report!, format);
    } finally {
      setDownloading(null);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileText className="h-4 w-4 text-brand-700" aria-hidden />
          Latest report
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-ink-600">
          Generated {formatTimestamp(summary.latest_report.generated_at)} ·{" "}
          {summary.latest_report.approved_count} approved ·{" "}
          {summary.latest_report.rejected_count} rejected ·{" "}
          {summary.latest_report.pending_count} pending
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => handle("pdf")}
            disabled={downloading !== null}
          >
            <Download className="mr-1.5 h-4 w-4" aria-hidden />
            {downloading === "pdf" ? "Downloading…" : "Download PDF"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => handle("excel")}
            disabled={downloading !== null}
          >
            <Download className="mr-1.5 h-4 w-4" aria-hidden />
            {downloading === "excel" ? "Downloading…" : "Download Excel"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function BusinessPage() {
  const [summary, setSummary] = React.useState<BusinessSummary | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [unavailable, setUnavailable] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    setError(null);
    setUnavailable(null);
    setSummary(null);
    getBusinessSummary()
      .then(setSummary)
      .catch((caught) => {
        if (caught instanceof ApiError && caught.status === 404) {
          setSummary(null);
          return;
        }
        if (caught instanceof ApiError && caught.status === 501) {
          setUnavailable(caught.message);
          return;
        }
        setError(
          caught instanceof ApiError ? caught.message : "Could not load the business summary.",
        );
      });
  }, []);

  React.useEffect(load, [load]);

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  if (unavailable) {
    return (
      <EmptyState
        title="Business view needs the live backend"
        message={`${unavailable} The owner-facing summary is built from stored case results, so it is not available while the app is running on sample fixtures.`}
        action={
          <Link href="/dashboard">
            <Button size="sm" variant="outline">
              Back to dashboard
            </Button>
          </Link>
        }
      />
    );
  }

  if (summary === null) {
    return (
      <div className="space-y-4 pb-20 md:pb-0">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24 w-full" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-24" />
          ))}
        </div>
      </div>
    );
  }

  const period =
    summary.period_start && summary.period_end
      ? `${formatDate(summary.period_start)} to ${formatDate(summary.period_end)}`
      : "Period not set";

  return (
    <div className="space-y-4 pb-20 md:pb-0">
      <div>
        <h1 className="text-xl font-bold text-ink-900">{summary.client_name}</h1>
        <p className="mt-1 break-words text-sm text-ink-600">
          {period} · {summary.case_id}
        </p>
      </div>

      <Card className="border-brand-200 bg-brand-50/40">
        <CardContent className="px-4 py-4 sm:px-5 sm:py-5">
          <p className="text-sm leading-relaxed text-ink-700">{summary.owner_summary}</p>
        </CardContent>
      </Card>

      {summary.urdu_summary && (
        <Card className="border-slate-200" dir="rtl">
          <CardHeader>
            <CardTitle className="text-base">مختصر جائزہ</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="break-words leading-loose text-ink-800" style={{ fontSize: "1.05rem" }}>
              {summary.urdu_summary}
            </p>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard
          label="Total reviewed"
          value={String(summary.total_review_items)}
          detail={`${summary.approved} approved · ${summary.rejected} rejected · ${summary.pending} pending`}
          icon={CheckCircle2}
        />
        <StatCard
          label="Matched"
          value={String(summary.matched)}
          detail={`${summary.partial} partial · ${summary.unmatched} unmatched`}
          icon={ShieldCheck}
          tone="good"
        />
        <StatCard
          label="Flags raised"
          value={String(summary.flag_count)}
          detail={`${summary.high_severity} high · ${summary.medium_severity} medium · ${summary.low_severity} low`}
          icon={AlertTriangle}
          tone={summary.high_severity > 0 ? "bad" : "warn"}
        />
        <StatCard
          label="Total value"
          value={summary.total_amount}
          detail={`Currency: ${summary.currency}`}
          icon={FileText}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DownloadReport summary={summary} />

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <HelpCircle className="h-4 w-4 text-brand-700" aria-hidden />
              What this means
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-ink-600">
            <p>
              <strong>Matched</strong> means the ledger entry lines up with a bank
              transaction and/or invoice. <strong>Partial</strong> means it lines up
              with some but not all expected evidence.
            </p>
            <p>
              <strong>Flags</strong> are suggestions from the firm&apos;s own rules;
              they are not accusations. The auditor approved or rejected each flagged
              item, and the reason is in the full report.
            </p>
            {summary.sign_off_required && (
              <p className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-amber-800">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                This engagement requires a second-person sign-off before the report is
                final.
                {summary.sign_off_satisfied
                  ? " The sign-off has been recorded."
                  : " It has not been signed off yet."}
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
