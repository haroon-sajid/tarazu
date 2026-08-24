import * as React from "react";
import { cn } from "@/lib/utils";
import type { Confidence, MatchStatus, MatchStrength, ReviewDecision, Severity } from "@/lib/types";

function BaseBadge({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap",
        className,
      )}
      {...props}
    />
  );
}

/** Matched green, Partial amber, Unmatched red — plus Flagged purple. */
const statusStyles: Record<MatchStatus | "flagged", string> = {
  matched: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  partial: "bg-amber-50 text-amber-700 ring-1 ring-amber-300",
  unmatched: "bg-rose-50 text-rose-700 ring-1 ring-rose-200",
  flagged: "bg-purple-50 text-purple-700 ring-1 ring-purple-200",
};

const statusLabels: Record<MatchStatus | "flagged", string> = {
  matched: "Matched",
  partial: "Partial",
  unmatched: "Unmatched",
  flagged: "Flagged",
};

export function StatusBadge({ status }: { status: MatchStatus | "flagged" }) {
  return <BaseBadge className={statusStyles[status]}>{statusLabels[status]}</BaseBadge>;
}

/**
 * The two three-level scales get deliberately different looks so they can
 * never be confused: match strength (deterministic) is a filled dot meter,
 * extraction confidence (AI) is a plain tinted pill.
 */
const levelTint: Record<"high" | "medium" | "low", string> = {
  high: "text-emerald-700",
  medium: "text-amber-700",
  low: "text-rose-700",
};

export function MatchStrengthBadge({ strength }: { strength: MatchStrength }) {
  const filled = strength === "high" ? 3 : strength === "medium" ? 2 : 1;
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 text-xs font-medium", levelTint[strength])}
      title="Match strength — computed by the deterministic matcher, never by AI"
    >
      <span className="inline-flex items-center gap-0.5" aria-hidden>
        {[1, 2, 3].map((step) => (
          <span
            key={step}
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              step <= filled ? "bg-current" : "bg-slate-200",
            )}
          />
        ))}
      </span>
      <span className="capitalize">{strength}</span>
    </span>
  );
}

const confidenceStyles: Record<Confidence, string> = {
  high: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  medium: "bg-amber-50 text-amber-700 ring-1 ring-amber-300",
  low: "bg-rose-50 text-rose-700 ring-1 ring-rose-200",
};

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  return (
    <BaseBadge
      className={confidenceStyles[confidence]}
      title="Extraction confidence — how sure the AI is that it read the value correctly"
    >
      AI: <span className="capitalize">{confidence}</span>
    </BaseBadge>
  );
}

const severityStyles: Record<Severity, string> = {
  high: "bg-rose-50 text-rose-700 ring-1 ring-rose-200",
  medium: "bg-amber-50 text-amber-700 ring-1 ring-amber-300",
  low: "bg-slate-100 text-ink-600 ring-1 ring-slate-200",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <BaseBadge className={severityStyles[severity]}>
      <span className="capitalize">{severity}</span>
    </BaseBadge>
  );
}

const decisionStyles: Record<ReviewDecision, string> = {
  pending: "bg-slate-100 text-ink-600 ring-1 ring-slate-200",
  approved: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  rejected: "bg-rose-50 text-rose-700 ring-1 ring-rose-200",
};

export function DecisionBadge({ decision }: { decision: ReviewDecision }) {
  return (
    <BaseBadge className={decisionStyles[decision]}>
      <span className="capitalize">{decision}</span>
    </BaseBadge>
  );
}
