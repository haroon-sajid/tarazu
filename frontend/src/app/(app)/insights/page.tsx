"use client";

/**
 * Insights — the firm across all of its cases, rather than one case at a time.
 *
 * A partner's question is not "what happened in this period" but "where is the
 * work piling up, which parties keep coming back to us, and which of our rules
 * are actually earning their place". That question spans engagements, so the
 * backend answers it in one deterministic pass over every case the firm can
 * see and hands back counts. This screen only arranges them.
 *
 * The vendor table is the part to read carefully. It is *attention*, not risk:
 * there is no score here, nothing is modelled, and nothing on this page claims
 * that a party has done anything wrong. It counts how often the deterministic
 * rules had something to say, and names which rules those were, so an auditor
 * can decide where to look first. Tarazu flags what needs review; it does not
 * detect fraud, and this screen says so out loud.
 *
 * Every number is counted by the backend. The bar chart draws the counts it is
 * given and computes nothing of its own — same contract as the Benford chart.
 */

import * as React from "react";
import Link from "next/link";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  Building2,
  ChevronRight,
  Clock3,
  FileQuestion,
  Layers,
  ListChecks,
} from "lucide-react";
import { ApiError, getInsights } from "@/lib/api";
import type { InsightsResponse } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { SeverityBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

/** "2026-06" → "Jun 26". Display formatting; no arithmetic on the data. */
function monthLabel(month: string): string {
  const date = new Date(`${month}-01T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return month;
  return date.toLocaleDateString("en-GB", {
    month: "short",
    year: "2-digit",
    timeZone: "UTC",
  });
}

function Stat({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: string;
  detail?: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <Card>
      <CardContent className="flex items-start justify-between gap-2 px-3.5 py-3.5 sm:px-5 sm:py-4">
        <div className="min-w-0">
          <p className="text-xs font-medium leading-tight text-ink-400">{label}</p>
          <p className="mt-1 text-xl font-bold text-ink-900 tabular-nums sm:text-2xl">
            {value}
          </p>
          {detail && (
            <p className="mt-0.5 text-[11px] leading-snug text-ink-400">{detail}</p>
          )}
        </div>
        <span className="hidden shrink-0 rounded-lg bg-gradient-to-br from-brand-50 to-brand-100 p-2.5 text-brand-700 shadow-sm sm:inline">
          <Icon className="h-5 w-5" aria-hidden />
        </span>
      </CardContent>
    </Card>
  );
}

/** The high / medium / low split behind one party's flag count. */
function SeveritySplit({
  high,
  medium,
  low,
}: {
  high: number;
  medium: number;
  low: number;
}) {
  const parts: Array<[number, string, string]> = [
    [high, "high", "bg-rose-50 text-rose-700 ring-rose-200"],
    [medium, "medium", "bg-amber-50 text-amber-700 ring-amber-300"],
    [low, "low", "bg-slate-100 text-ink-600 ring-slate-200"],
  ];
  return (
    <span className="inline-flex flex-wrap gap-1">
      {parts
        .filter(([count]) => count > 0)
        .map(([count, name, tone]) => (
          <span
            key={name}
            title={`${count} ${name}-severity ${count === 1 ? "flag" : "flags"}`}
            className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium tabular-nums ring-1 ${tone}`}
          >
            {count} {name}
          </span>
        ))}
    </span>
  );
}

export default function InsightsPage() {
  const [insights, setInsights] = React.useState<InsightsResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  /** 501: the route exists but this build has no backend behind it. */
  const [unavailable, setUnavailable] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    setError(null);
    setUnavailable(null);
    setInsights(null);
    getInsights()
      .then(setInsights)
      .catch((caught) => {
        if (caught instanceof ApiError && caught.status === 501) {
          setUnavailable(caught.message);
          return;
        }
        setError(
          caught instanceof ApiError ? caught.message : "Could not load the insights.",
        );
      });
  }, []);

  React.useEffect(load, [load]);

  const header = (
    <div className="mb-5">
      <h1 className="text-xl font-bold text-ink-900">Insights</h1>
      <p className="mt-1 text-sm text-ink-600">
        Your firm across every case it can see, counted from the same
        deterministic results each dashboard shows. Nothing here is modelled,
        scored, or estimated.
      </p>
    </div>
  );

  if (error) {
    return (
      <div>
        {header}
        <ErrorState message={error} onRetry={load} />
      </div>
    );
  }

  if (unavailable) {
    return (
      <div>
        {header}
        <EmptyState
          title="Insights need the live backend"
          message={`${unavailable} Counting across every case is deterministic work the backend does over stored results — there is nothing to count, and nothing worth inventing, while the app is running on sample fixtures.`}
          action={
            <Link href="/cases">
              <Button size="sm" variant="outline">
                Back to cases
              </Button>
            </Link>
          }
        />
      </div>
    );
  }

  if (!insights) {
    return (
      <div>
        {header}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-24 w-full" />
          ))}
        </div>
        <Skeleton className="mt-4 h-64 w-full" />
        <Skeleton className="mt-4 h-52 w-full" />
      </div>
    );
  }

  if (insights.case_count === 0) {
    return (
      <div>
        {header}
        <EmptyState
          title="Nothing to count yet"
          message="Insights read across finished work. Run a period — upload a bank statement, invoices, and a ledger — and the counts, the parties, and the rules that fired will appear here."
          action={
            <Link href="/upload">
              <Button size="sm">Go to upload</Button>
            </Link>
          }
        />
      </div>
    );
  }

  const months = insights.months.map((point) => ({
    month: monthLabel(point.month),
    Items: point.item_count,
    Flags: point.flag_count,
  }));

  return (
    <div>
      {header}

      <Link
        href="/business"
        className="mb-4 flex items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm transition-colors hover:border-brand-600 hover:bg-slate-50"
      >
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
            <Building2 className="h-5 w-5" aria-hidden />
          </span>
          <div>
            <p className="text-sm font-semibold text-ink-900">Business view</p>
            <p className="text-xs text-ink-500">
              Owner-facing summary of the active engagement.
            </p>
          </div>
        </div>
        <ChevronRight className="h-4 w-4 text-ink-400" aria-hidden />
      </Link>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Cases"
          value={String(insights.case_count)}
          detail={`${insights.client_count} ${insights.client_count === 1 ? "client" : "clients"}`}
          icon={Layers}
        />
        <Stat
          label="Review items"
          value={String(insights.total_review_items)}
          detail={`${insights.pending_items} awaiting a human decision`}
          icon={ListChecks}
        />
        <Stat
          label="Flags raised"
          value={String(insights.total_flags)}
          detail={`${insights.unreviewed_flags} on items nobody has decided yet`}
          icon={AlertTriangle}
        />
        <Stat
          label="Evidence requests"
          value={String(insights.open_evidence_requests)}
          detail="Still open with clients"
          icon={FileQuestion}
        />
      </div>

      <p className="mt-3 flex items-center gap-1.5 text-[11px] text-ink-400">
        <Clock3 className="h-3.5 w-3.5 shrink-0" aria-hidden />
        Estimated {insights.estimated_hours_saved.toFixed(1)} hours saved against
        reconciling these items by hand — an estimate the backend derives from
        item counts, and the only figure on this screen that is not a count.
      </p>

      {/* Vendor attention — not a risk score, and never described as one */}
      <Card className="mt-5">
        <CardHeader>
          <CardTitle>Parties that need attention</CardTitle>
          <p className="mt-1 text-xs leading-relaxed text-ink-600">
            How often the deterministic rules had something to say about each
            party, and which rules those were. Tarazu flags what needs review; it
            does not detect fraud, and this is not a risk score. A flag is a
            question for an auditor, never a verdict about a supplier.
          </p>
        </CardHeader>
        <CardContent>
          {insights.vendors.length === 0 ? (
            <p className="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-ink-600">
              No rule has fired on any party yet.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full min-w-[820px] text-left">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                    <th className="px-4 py-2.5">Party</th>
                    <th className="px-4 py-2.5 text-right">Flags</th>
                    <th className="px-4 py-2.5">Severity</th>
                    <th className="px-4 py-2.5">Rules that fired</th>
                    <th className="px-4 py-2.5 text-right">Items</th>
                    <th className="px-4 py-2.5 text-right">Cases</th>
                    <th className="px-4 py-2.5 text-right">Total amount</th>
                  </tr>
                </thead>
                <tbody>
                  {insights.vendors.map((vendor) => (
                    <tr
                      key={vendor.party_name}
                      className="border-b border-slate-100 text-sm last:border-0"
                    >
                      <td className="px-4 py-3 font-medium text-ink-900">
                        {vendor.party_name}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                        {vendor.flag_count}
                      </td>
                      <td className="px-4 py-3">
                        <SeveritySplit
                          high={vendor.high}
                          medium={vendor.medium}
                          low={vendor.low}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-flex flex-wrap gap-1">
                          {vendor.rules.map((rule) => (
                            <span
                              key={rule}
                              className="rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-ink-600 ring-1 ring-slate-200"
                            >
                              {rule}
                            </span>
                          ))}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                        {vendor.item_count}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-600">
                        {vendor.case_count}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                        {vendor.currency} {vendor.total_amount}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Which rules are earning their place */}
      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Rules that fired</CardTitle>
          <p className="mt-1 text-xs leading-relaxed text-ink-600">
            How often each rule raised a flag, and how many of those flags sit on
            an item somebody has already decided. A rule that fires constantly
            and is always cleared is a threshold worth retuning on the client.
          </p>
        </CardHeader>
        <CardContent>
          {insights.rules.length === 0 ? (
            <p className="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-ink-600">
              No rule has fired yet.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full min-w-[560px] text-left">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                    <th className="px-4 py-2.5">Rule</th>
                    <th className="px-4 py-2.5">Severity</th>
                    <th className="px-4 py-2.5 text-right">Times fired</th>
                    <th className="px-4 py-2.5 text-right">Reviewed</th>
                  </tr>
                </thead>
                <tbody>
                  {insights.rules.map((rule) => (
                    <tr
                      key={rule.rule_id}
                      className="border-b border-slate-100 text-sm last:border-0"
                    >
                      <td className="px-4 py-3 font-mono text-xs text-ink-900">
                        {rule.rule_id}
                      </td>
                      <td className="px-4 py-3">
                        <SeverityBadge severity={rule.severity} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                        {rule.count}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-600">
                        {rule.reviewed}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* The shape of the work, month by month */}
      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Month by month</CardTitle>
          <p className="mt-1 text-xs leading-relaxed text-ink-600">
            Items reviewed and flags raised per month across the firm, with the
            total amount behind each month underneath.
          </p>
        </CardHeader>
        <CardContent>
          {insights.months.length === 0 ? (
            <p className="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-ink-600">
              No dated items yet, so there is no trend to draw.
            </p>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={months} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                  <XAxis
                    dataKey="month"
                    tick={{ fontSize: 11, fill: "#64748b" }}
                    axisLine={{ stroke: "#cbd5e1" }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "#64748b" }}
                    axisLine={false}
                    tickLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: "#e2e8f0" }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="Items" fill="#0f766e" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="Flags" fill="#99f6e4" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>

              {/* The same rows as text: the chart's accessible equivalent, and
                  the only place the month's total amount is readable. */}
              <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full min-w-[480px] text-left">
                  <caption className="sr-only">
                    Items, flags, and total amount per month
                  </caption>
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                      <th className="px-4 py-2.5">Month</th>
                      <th className="px-4 py-2.5 text-right">Items</th>
                      <th className="px-4 py-2.5 text-right">Flags</th>
                      <th className="px-4 py-2.5 text-right">Total amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {insights.months.map((point) => (
                      <tr
                        key={point.month}
                        className="border-b border-slate-100 text-sm last:border-0"
                      >
                        <td className="whitespace-nowrap px-4 py-2.5 text-ink-900">
                          {monthLabel(point.month)}
                        </td>
                        <td className="whitespace-nowrap px-4 py-2.5 text-right tabular-nums text-ink-900">
                          {point.item_count}
                        </td>
                        <td className="whitespace-nowrap px-4 py-2.5 text-right tabular-nums text-ink-900">
                          {point.flag_count}
                        </td>
                        <td className="whitespace-nowrap px-4 py-2.5 text-right tabular-nums text-ink-600">
                          {point.total_amount}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <p className="mt-4 flex items-start gap-1.5 text-[11px] leading-relaxed text-ink-400">
        <Building2 className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
        Counted across the cases your organization can see. Nothing on this
        screen decides anything: every flag behind these numbers still needs a
        human approval or rejection on the review queue.
      </p>
    </div>
  );
}
