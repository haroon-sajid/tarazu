"use client";

/**
 * Revenue by product as horizontal bars — whole-period figures, highest first,
 * exactly as the backend ranked them. Long product names truncate on the axis
 * and stay whole in the tooltip.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ProductRevenue } from "@/lib/types";
import { formatCompactNumber, formatMoney } from "@/lib/format";

const truncate = (name: string) =>
  name.length > 14 ? `${name.slice(0, 13)}…` : name;

export function ProductChart({ products }: { products: ProductRevenue[] }) {
  if (products.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-ink-400">
        No products in this export.
      </p>
    );
  }
  // One bar per product plus breathing room; a taller list grows the chart.
  const height = Math.max(200, products.length * 44 + 16);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={products}
        layout="vertical"
        margin={{ top: 4, right: 12, bottom: 0, left: 0 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
        <XAxis
          type="number"
          tickFormatter={(value: number) => formatCompactNumber(value)}
          tick={{ fontSize: 11, fill: "#64748b" }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="product"
          width={104}
          tickFormatter={(name: string) => truncate(name)}
          tick={{ fontSize: 11, fill: "#64748b" }}
          axisLine={{ stroke: "#cbd5e1" }}
          tickLine={false}
        />
        <Tooltip
          formatter={(value: unknown, name: unknown) => [
            formatMoney(Number(value)),
            String(name),
          ]}
          contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: "#e2e8f0" }}
          cursor={{ fill: "#f8fafc" }}
        />
        <Bar
          dataKey="revenue"
          name="Revenue"
          fill="#0f766e"
          radius={[0, 3, 3, 0]}
          barSize={18}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
