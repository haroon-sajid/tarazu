"use client";

/**
 * Sales by region as a donut. Only rows that carry a region are in the slices
 * — the backend's caveat, so shares can sum below 100% — and the legend spells
 * out each slice's money and share for readers who cannot compare angles, or
 * are on a small screen.
 */

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { RegionSummary } from "@/lib/types";
import { formatMoney, formatMoneyCompact } from "@/lib/format";

const SLICE_COLORS = ["#0f766e", "#14b8a6", "#f59e0b", "#8b5cf6", "#0ea5e9", "#64748b"];

export function RegionChart({ regions }: { regions: RegionSummary[] }) {
  if (regions.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-ink-400">
        No region column in this export — rows without one never reach this chart.
      </p>
    );
  }
  const slices = regions.map((region, index) => ({
    ...region,
    fill: SLICE_COLORS[index % SLICE_COLORS.length],
  }));
  return (
    <div>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie
            data={slices}
            dataKey="revenue"
            nameKey="region"
            innerRadius="58%"
            outerRadius="88%"
            paddingAngle={2}
            stroke="none"
          >
            {slices.map((slice) => (
              <Cell key={slice.region} fill={slice.fill} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value: unknown, name: unknown) => [
              formatMoney(Number(value)),
              String(name),
            ]}
            contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: "#e2e8f0" }}
          />
        </PieChart>
      </ResponsiveContainer>
      <ul className="mt-2 space-y-1.5">
        {slices.map((slice) => (
          <li
            key={slice.region}
            className="flex items-center justify-between gap-2 text-xs"
          >
            <span className="flex min-w-0 items-center gap-2">
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: slice.fill }}
                aria-hidden
              />
              <span className="truncate text-ink-600">{slice.region}</span>
            </span>
            <span className="shrink-0 tabular-nums text-ink-900">
              {formatMoneyCompact(slice.revenue)} · {slice.share.toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
