"use client";

/**
 * The top customers, ranked by the backend — at most five, whole-period. The
 * share bar mirrors the readiness meters' look: a readout of the share the
 * backend computed, not a new calculation.
 */

import type { CustomerSummary } from "@/lib/types";
import { formatMoney } from "@/lib/format";

export function CustomerTable({ customers }: { customers: CustomerSummary[] }) {
  if (customers.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-ink-400">
        No customers ranked. A readout with no sales has nobody to rank.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 text-[10px] font-semibold tracking-wide text-ink-400 uppercase">
            <th className="px-3 py-2.5">Customer</th>
            <th className="px-3 py-2.5 text-right">Revenue</th>
            <th className="px-3 py-2.5 text-right">Sales</th>
            <th className="px-3 py-2.5">Share</th>
          </tr>
        </thead>
        <tbody>
          {customers.map((customer, index) => (
            <tr
              key={customer.customer_name}
              className="border-b border-slate-100 text-sm last:border-0 hover:bg-slate-50/60"
            >
              <td className="max-w-52 truncate px-3 py-2.5 font-medium text-ink-900">
                <span className="mr-2 text-xs text-ink-400 tabular-nums">
                  {index + 1}.
                </span>
                {customer.customer_name}
              </td>
              <td className="whitespace-nowrap px-3 py-2.5 text-right font-medium text-ink-900 tabular-nums">
                {formatMoney(customer.revenue)}
              </td>
              <td className="whitespace-nowrap px-3 py-2.5 text-right text-ink-600 tabular-nums">
                {customer.transaction_count}
              </td>
              <td className="px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-brand-700"
                      style={{ width: `${Math.min(100, customer.share)}%` }}
                    />
                  </div>
                  <span className="text-xs text-ink-600 tabular-nums">
                    {customer.share.toFixed(1)}%
                  </span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
