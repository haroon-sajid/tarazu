"use client";

/**
 * The demo dashboard: the stat cards, the Benford chart and the readiness
 * score exactly as the signed-in screen shows them, over the sample case.
 *
 * Every figure here was counted by the backend and stored in the fixture. The
 * one exception is the decision tally, which is recounted from the visitor's
 * own clicks in this session — the same display bookkeeping fixture mode does
 * in `lib/api.ts`, and still not audit math: it counts three states of a
 * radio button, it does not reconcile anything.
 *
 * The Benford chart is the real `BenfordChart` component. The stat card is a
 * local copy of the dashboard's private one rather than a new shared
 * primitive, because a public marketing surface should not get a vote on the
 * shape of the working screen's internals.
 */

import * as React from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, Clock3, Layers } from "lucide-react";
import type { DashboardSummary, ReadinessComponent, ReviewItem } from "@/lib/types";
import { formatDate } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SeverityBadge } from "@/components/ui/badge";
import { BenfordChart } from "@/components/dashboard/benford-chart";

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
  tone?: "default" | "good" | "warn";
}) {
  return (
    <Card>
      <CardContent className="flex items-start justify-between gap-2 px-3.5 py-3.5 sm:px-5 sm:py-4">
        <div className="min-w-0">
          <p className="text-xs leading-tight font-medium text-ink-400">{label}</p>
          <p className="mt-1 text-xl font-bold text-ink-900 tabular-nums sm:text-2xl">
            {value}
          </p>
          {detail && <p className="mt-0.5 text-[11px] leading-snug text-ink-400">{detail}</p>}
        </div>
        <span
          className={
            tone === "good"
              ? "hidden shrink-0 rounded-lg bg-gradient-to-br from-emerald-50 to-emerald-100 p-2.5 text-emerald-600 shadow-sm sm:inline"
              : tone === "warn"
                ? "hidden shrink-0 rounded-lg bg-gradient-to-br from-purple-50 to-purple-100 p-2.5 text-purple-600 shadow-sm sm:inline"
                : "hidden shrink-0 rounded-lg bg-gradient-to-br from-brand-50 to-brand-100 p-2.5 text-brand-700 shadow-sm sm:inline"
          }
        >
          <Icon className="h-5 w-5" aria-hidden />
        </span>
      </CardContent>
    </Card>
  );
}

function ReadinessRow({
  label,
  component,
}: {
  label: string;
  component: ReadinessComponent;
}) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="font-medium text-ink-600">{label}</span>
        <span className="text-ink-400 tabular-nums">
          {component.count} of {component.total} · {component.percent.toFixed(0)}%
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-brand-700"
          style={{ width: `${component.percent}%` }}
        />
      </div>
    </div>
  );
}

export function DemoDashboard({
  summary,
  items,
  onOpenItem,
}: {
  summary: DashboardSummary;
  /** The live demo items, so the decision tally follows the visitor's clicks. */
  items: ReviewItem[];
  /** Send the visitor to that row in the queue tab, opened on its evidence. */
  onOpenItem: (reviewItemId: string) => void;
}) {
  const decisions = { pending: 0, approved: 0, rejected: 0 };
  for (const item of items) decisions[item.decision] += 1;

  const matchedPercent = Math.round(
    (summary.match_status.matched / summary.total_review_items) * 100,
  );
  const period =
    summary.period_start && summary.period_end
      ? `${formatDate(summary.period_start)} to ${formatDate(summary.period_end)}`
      : undefined;

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-bold text-ink-900">{summary.client_name}</h3>
        <p className="mt-1 text-xs break-words text-ink-600 sm:text-sm">
          {summary.case_id}
          {period ? ` · ${period}` : ""}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard
          label="Total review items"
          value={String(summary.total_review_items)}
          detail={`${decisions.pending} pending · ${decisions.approved} approved · ${decisions.rejected} rejected`}
          icon={Layers}
        />
        <StatCard
          label="Matched"
          value={`${matchedPercent}%`}
          detail={`${summary.match_status.matched} matched · ${summary.match_status.partial} partial · ${summary.match_status.unmatched} unmatched`}
          icon={CheckCircle2}
          tone="good"
        />
        <StatCard
          label="Flags raised"
          value={String(summary.total_flags)}
          detail={`${summary.flags_by_severity.high} high · ${summary.flags_by_severity.medium} medium · ${summary.flags_by_severity.low} low`}
          icon={AlertTriangle}
          tone="warn"
        />
        <StatCard
          label="Estimated hours saved"
          value={summary.estimated_hours_saved.toFixed(1)}
          detail="vs. fully manual reconciliation"
          icon={Clock3}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Benford&apos;s Law: first-digit distribution</CardTitle>
          </CardHeader>
          <CardContent>
            {summary.benford ? (
              <BenfordChart benford={summary.benford} />
            ) : (
              <p className="py-10 text-center text-sm text-ink-400">
                Benford analysis is not available for this case.
              </p>
            )}
            <p className="mt-2 text-[11px] leading-relaxed text-ink-400">
              A digit test, not a verdict. It points at where to look; the auditor decides
              whether there is anything there.
            </p>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Audit readiness</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-4xl font-bold text-brand-900 tabular-nums">
                {summary.audit_readiness_score.score}
                <span className="text-base font-medium text-ink-400"> / 100</span>
              </p>
              <div className="mt-4 space-y-3">
                <ReadinessRow
                  label="Matched"
                  component={summary.audit_readiness_score.matched}
                />
                <ReadinessRow
                  label="Flags reviewed"
                  component={summary.audit_readiness_score.flags_reviewed}
                />
                <ReadinessRow
                  label="Completeness"
                  component={summary.audit_readiness_score.completeness}
                />
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Data confidence</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed text-ink-600">
                {summary.data_confidence}
              </p>
            </CardContent>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Next best actions</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="divide-y divide-slate-100">
            {summary.next_best_actions.map((action, index) => (
              <li key={`${action.review_item_id}-${action.rule_id}-${index}`}>
                <button
                  type="button"
                  onClick={() => onOpenItem(action.review_item_id)}
                  className="group flex w-full items-center justify-between gap-3 py-2.5 text-left"
                >
                  <span className="flex min-w-0 items-center gap-2 sm:gap-3">
                    <SeverityBadge severity={action.severity} />
                    <span className="truncate text-sm text-ink-900 transition-colors group-hover:text-brand-700">
                      {action.action}
                    </span>
                    <span className="hidden shrink-0 font-mono text-[10px] text-ink-400 sm:inline">
                      {action.rule_id}
                    </span>
                  </span>
                  <ArrowRight
                    className="h-4 w-4 shrink-0 text-ink-400 group-hover:text-brand-700"
                    aria-hidden
                  />
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-ink-400">
            Ranked by the rules engine, not by a model. Pick one to open the evidence
            behind it in the review queue.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
