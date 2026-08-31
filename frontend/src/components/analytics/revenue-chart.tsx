"use client";

/**
 * Monthly revenue as a line over the backend's ascending months — the one
 * series with a time axis, so the one the date-range filter reslices. Values
 * arrive already summed per month; nothing is recomputed here.
 */

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MonthlyRevenue } from "@/lib/types";
import { formatCompactNumber, formatMoney, formatMonth } from "@/lib/format";

export function RevenueChart({ months }: { months: MonthlyRevenue[] }) {
  if (months.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-ink-400">
        No months fall inside this range. Switch to All to see the whole series.
      </p>
    );
  }
  const data = months.map((entry) => ({
    month: entry.month,
    revenue: entry.revenue,
  }));
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis
          dataKey="month"
          tickFormatter={(month: string) => formatMonth(month, "2-digit")}
          tick={{ fontSize: 11, fill: "#64748b" }}
          axisLine={{ stroke: "#cbd5e1" }}
          tickLine={false}
        />
        <YAxis
          tickFormatter={(value: number) => formatCompactNumber(value)}
          tick={{ fontSize: 11, fill: "#64748b" }}
          axisLine={false}
          tickLine={false}
          width={44}
        />
        <Tooltip
          formatter={(value: unknown, name: unknown) => [
            formatMoney(Number(value)),
            String(name),
          ]}
          labelFormatter={(label: string) => formatMonth(label)}
          contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: "#e2e8f0" }}
          cursor={{ stroke: "#cbd5e1" }}
        />
        <Line
          type="monotone"
          dataKey="revenue"
          name="Revenue"
          stroke="#0f766e"
          strokeWidth={2}
          dot={{ r: 3, fill: "#0f766e", strokeWidth: 0 }}
          activeDot={{ r: 5 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
