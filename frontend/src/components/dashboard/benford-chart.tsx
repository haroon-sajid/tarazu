"use client";

/**
 * Benford's Law first-digit chart: observed vs expected frequency per digit
 * 1–9 as grouped bars. Both series come straight from the backend's
 * deterministic `BenfordResult`; nothing is computed here.
 */

import * as React from "react";
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
import type { BenfordResult } from "@/lib/types";
import { formatPercent } from "@/lib/format";

// Phones render nine digit groups in a much narrower box: a shorter chart, a
// slimmer Y axis, and smaller ticks keep it readable. ≥sm keeps the desktop look.
function useIsPhone() {
  const [phone, setPhone] = React.useState(false);
  React.useEffect(() => {
    const query = window.matchMedia("(max-width: 639px)");
    const sync = () => setPhone(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);
  return phone;
}

export function BenfordChart({ benford }: { benford: BenfordResult }) {
  const phone = useIsPhone();
  const data = benford.digits.map((digit) => ({
    digit: String(digit.digit),
    Observed: +(digit.observed_frequency * 100).toFixed(2),
    Expected: +(digit.expected_frequency * 100).toFixed(2),
    count: digit.observed_count,
  }));

  return (
    <div>
      <ResponsiveContainer width="100%" height={phone ? 210 : 260}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: phone ? 0 : -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis
            dataKey="digit"
            tick={{ fontSize: phone ? 10 : 11, fill: "#64748b" }}
            axisLine={{ stroke: "#cbd5e1" }}
            tickLine={false}
            label={{
              value: "First digit",
              position: "insideBottom",
              offset: -2,
              fontSize: 10,
              fill: "#94a3b8",
            }}
          />
          <YAxis
            width={phone ? 34 : undefined}
            tick={{ fontSize: phone ? 10 : 11, fill: "#64748b" }}
            axisLine={false}
            tickLine={false}
            unit="%"
          />
          <Tooltip
            formatter={(value: unknown, name: unknown) => [`${value}%`, String(name)]}
            labelFormatter={(label) => `Digit ${label}`}
            contentStyle={{ fontSize: 12, borderRadius: 8, borderColor: "#e2e8f0" }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="Observed" fill="#0f766e" radius={[3, 3, 0, 0]} />
          <Bar dataKey="Expected" fill="#99f6e4" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <p className="mt-1 text-[11px] text-ink-400">
        {benford.sample_size} amounts · χ² = {benford.chi_square} (
        {benford.degrees_of_freedom} df) ·{" "}
        {benford.deviates_significantly ? (
          <span className="font-medium text-rose-600">
            deviates significantly from Benford&apos;s expectation
          </span>
        ) : (
          "no significant deviation"
        )}
        {" · "}expected digit-1 share {formatPercent(benford.digits[0]?.expected_frequency ?? 0.301)}
      </p>
    </div>
  );
}
