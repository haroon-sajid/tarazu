"use client";

/**
 * The summary cards: every figure was computed by the backend's pandas. The
 * one client-side calculation is display bookkeeping — summing the monthly
 * figures the date-range filter leaves in view — never a new audit figure.
 */

import * as React from "react";
import {
  AlertTriangle,
  CalendarRange,
  CircleDollarSign,
  Package,
  ShoppingCart,
  Users,
} from "lucide-react";
import type { MonthlyRevenue, SalesAnalyticsResult } from "@/lib/types";
import { formatMoney, formatMonth } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";
import { anomalySeverity } from "./anomaly-list";

function SummaryCard({
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
      <CardContent className="flex items-start justify-between gap-3 px-5 py-4">
        <div className="min-w-0">
          <p className="text-xs font-medium text-ink-400">{label}</p>
          <p
            className="mt-1 truncate text-2xl font-bold text-ink-900 tabular-nums"
            title={value}
          >
            {value}
          </p>
          {detail && <p className="mt-0.5 text-[11px] text-ink-400">{detail}</p>}
        </div>
        <span
          className={
            tone === "good"
              ? "rounded-lg bg-gradient-to-br from-emerald-50 to-emerald-100 p-2.5 text-emerald-600 shadow-sm"
              : tone === "warn"
                ? "rounded-lg bg-gradient-to-br from-purple-50 to-purple-100 p-2.5 text-purple-600 shadow-sm"
                : "rounded-lg bg-gradient-to-br from-brand-50 to-brand-100 p-2.5 text-brand-700 shadow-sm"
          }
        >
          <Icon className="h-5 w-5" aria-hidden />
        </span>
      </CardContent>
    </Card>
  );
}

export function SummaryCards({
  result,
  months,
}: {
  result: SalesAnalyticsResult;
  /** The monthly series as the date-range filter left it — the window being summed. */
  months: MonthlyRevenue[];
}) {
  const wholePeriod = months.length === result.monthly_revenue.length;
  const revenue = months.reduce((sum, entry) => sum + entry.revenue, 0);
  const sales = months.reduce((sum, entry) => sum + entry.transaction_count, 0);
  const span =
    months.length === 0
      ? "no months in this range"
      : months.length === 1
        ? formatMonth(months[0].month)
        : `${formatMonth(months[0].month)} – ${formatMonth(months[months.length - 1].month)}`;

  const severity = { high: 0, medium: 0, low: 0 };
  for (const anomaly of result.anomalies)
    severity[anomalySeverity(anomaly.kind)] += 1;

  const topCustomer = result.top_customers[0];
  const topProduct = result.revenue_by_product[0];
  const bestMonth = months.reduce<MonthlyRevenue | null>(
    (best, entry) => (best === null || entry.revenue > best.revenue ? entry : best),
    null,
  );

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <SummaryCard
        label="Revenue"
        value={formatMoney(revenue)}
        detail={
          wholePeriod
            ? `${months.length} month${months.length === 1 ? "" : "s"} · ${span}`
            : `${months.length} of ${result.monthly_revenue.length} months · ${span}`
        }
        icon={CircleDollarSign}
      />
      <SummaryCard
        label="Sales records"
        value={String(sales)}
        detail={
          wholePeriod
            ? `${result.record_count} in the case`
            : `of ${result.record_count} in the case`
        }
        icon={ShoppingCart}
      />
      <SummaryCard
        label="Anomalies"
        value={String(result.anomalies.length)}
        detail={
          result.anomalies.length === 0
            ? "none found by the rules"
            : `${severity.high} high · ${severity.medium} medium · ${severity.low} low`
        }
        icon={AlertTriangle}
        tone="warn"
      />
      <SummaryCard
        label="Top customer"
        value={topCustomer ? topCustomer.customer_name : "—"}
        detail={
          topCustomer
            ? `${formatMoney(topCustomer.revenue)} · ${topCustomer.share.toFixed(1)}% of revenue`
            : "no customers ranked"
        }
        icon={Users}
        tone="good"
      />
      <SummaryCard
        label="Top product"
        value={topProduct ? topProduct.product : "—"}
        detail={
          topProduct
            ? `${formatMoney(topProduct.revenue)} · ${topProduct.share.toFixed(1)}% of revenue`
            : "no products in the export"
        }
        icon={Package}
      />
      <SummaryCard
        label="Best month"
        value={bestMonth ? formatMonth(bestMonth.month) : "—"}
        detail={
          bestMonth
            ? `${formatMoney(bestMonth.revenue)} · ${bestMonth.transaction_count} sales`
            : span
        }
        icon={CalendarRange}
        tone="good"
      />
    </div>
  );
}
