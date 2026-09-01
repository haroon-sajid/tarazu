"use client";

/**
 * The anomalies card: what the deterministic rules found in the sales export,
 * in the order the backend emitted them. Like a `Flag`, each row is a
 * suggestion for a human — never a verdict — and nothing here can suppress or
 * resolve one.
 *
 * The contract's `Anomaly` carries no severity, only the rule `kind`; the kind
 * decides only how loudly the badge is colored. That mapping is presentation:
 * it never changes what a finding means.
 */

import { CheckCircle2 } from "lucide-react";
import type { SalesAnomaly, Severity } from "@/lib/types";
import { formatMonth } from "@/lib/format";
import { SeverityBadge } from "@/components/ui/badge";

/**
 * Display-only tiering of the backend's anomaly kinds: money moving backwards
 * and possible duplicates read loudest, a whale sale reads quietest. An
 * unknown kind — a rule newer than this build — defaults to medium rather
 * than guessing high.
 */
const KIND_SEVERITY: Record<string, Severity> = {
  "negative-amount": "high",
  "duplicate-transaction": "high",
  "revenue-spike": "medium",
  "large-transaction": "low",
};

export function anomalySeverity(kind: string): Severity {
  return KIND_SEVERITY[kind] ?? "medium";
}

export function AnomalyList({ anomalies }: { anomalies: SalesAnomaly[] }) {
  if (anomalies.length === 0) {
    return (
      <p className="flex items-center justify-center gap-2 py-8 text-sm text-ink-400">
        <CheckCircle2 className="h-4 w-4 text-emerald-500" aria-hidden />
        Nothing anomalous: no negative, duplicate, spiked, or outlying sales.
      </p>
    );
  }
  return (
    <ul className="divide-y divide-slate-100">
      {anomalies.map((anomaly) => (
        <li
          key={anomaly.anomaly_id}
          className="flex items-start gap-3 py-3 first:pt-0 last:pb-0"
        >
          <SeverityBadge severity={anomalySeverity(anomaly.kind)} />
          <div className="min-w-0 flex-1">
            <p className="text-sm leading-relaxed text-ink-900">
              {anomaly.explanation}
            </p>
            <p className="mt-0.5 break-words font-mono text-[10px] text-ink-400">
              {anomaly.anomaly_id} · {anomaly.kind}
              {anomaly.month ? ` · ${formatMonth(anomaly.month)}` : ""}
              {anomaly.related_row_ids.length > 0
                ? ` · rows ${anomaly.related_row_ids.join(", ")}`
                : anomaly.source_row_id
                  ? ` · row ${anomaly.source_row_id}`
                  : ""}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}
