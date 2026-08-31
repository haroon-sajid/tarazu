"use client";

/**
 * One client — the relationship, its history, and the thresholds it is audited
 * against.
 *
 * The rules editor is the point of this screen. Tarazu ships sensible defaults,
 * but a firm auditing a corner shop and a textile mill needs different approval
 * limits for each, and "the rules are ours" is what makes this the firm's tool
 * rather than a black box with opinions. Every threshold here is an input to
 * the deterministic rules engine; none of them is an input to a model, and
 * none of them approves anything — a threshold can only ever raise a flag for a
 * human to look at.
 *
 * Retuning is forward-looking on purpose. Rules are applied when a period is
 * processed, so a change here shapes the next period and leaves every decision
 * already recorded exactly as the auditor made it. Recomputing a decided queue
 * is not something this product does, and the screen says so where the reader
 * is about to save.
 *
 * The periods list is the same case rows the Cases screen shows, with the same
 * counts from the same backend. Opening one points the whole workspace at it,
 * exactly as the header's case switcher does.
 */

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Loader2, Plus, Save, Upload, X } from "lucide-react";
import {
  ApiError,
  getClient,
  setActiveCaseId,
  updateClient,
} from "@/lib/api";
import type {
  CaseStatus,
  CaseSummary,
  ClientRuleConfig,
  ClientSummary,
} from "@/lib/types";
import { formatDate, formatTimestamp } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";

// --------------------------------------------------------------------------
// near_limit_tolerance: a fraction on the wire, a percentage on the screen
//
// The contract stores the near-limit tolerance as a fraction (0.02) because
// that is what the rules engine multiplies by. Auditors read and write it as a
// percentage (2%). These two helpers are the only place the two forms meet.
//
// Both round, because binary floating point leaves tails on exactly this kind
// of arithmetic (0.07 * 100 is 7.000000000000001, and 4.1 / 100 is
// 0.040999999999999995). Rounding means a round-trip that changes nothing
// sends back byte-for-byte the value the backend already holds, so a no-op save
// stays a no-op and writes no audit entry. Four decimals of percent and six of
// fraction are far finer than the 0-to-50% range this field allows.
// --------------------------------------------------------------------------

const toPercent = (fraction: number): number => Number((fraction * 100).toFixed(4));
const toFraction = (percent: number): number => Number((percent / 100).toFixed(6));

/** The editable form of `ClientRuleConfig`. Strings so a field can be empty
 *  mid-edit without the number input snapping back under the reader. */
interface RuleDraft {
  limits: string[];
  roundFloor: string;
  dateTolerance: string;
  duplicateWindow: string;
  /** The percentage the reader sees; converted on save. */
  nearLimitPercent: string;
  requireSignOff: boolean;
}

function draftFrom(rules: ClientRuleConfig): RuleDraft {
  return {
    limits: rules.approval_limits.map(String),
    roundFloor: String(rules.round_number_floor),
    dateTolerance: String(rules.date_tolerance_days),
    duplicateWindow: String(rules.duplicate_window_days),
    nearLimitPercent: String(toPercent(rules.near_limit_tolerance)),
    requireSignOff: rules.require_sign_off,
  };
}

/** Form validation, not audit math: the numbers are the auditor's own. */
function parseDraft(draft: RuleDraft): { rules: ClientRuleConfig } | { error: string } {
  const limits: number[] = [];
  for (const raw of draft.limits) {
    const value = Number(raw);
    if (!raw.trim() || !Number.isInteger(value) || value <= 0) {
      return { error: "Every approval limit must be a whole number above zero." };
    }
    limits.push(value);
  }
  if (limits.length === 0) {
    return { error: "Keep at least one approval limit, or the near-limit and structuring rules have nothing to watch." };
  }
  if (limits.length > 12) {
    return { error: "Twelve approval limits is the most a client can carry." };
  }

  const whole = (raw: string, min: number, max: number, name: string) => {
    const value = Number(raw);
    if (!raw.trim() || !Number.isInteger(value) || value < min || value > max) {
      return `${name} must be a whole number between ${min} and ${max}.`;
    }
    return value;
  };

  const roundFloor = whole(draft.roundFloor, 0, 1_000_000_000, "The round-number floor");
  if (typeof roundFloor === "string") return { error: roundFloor };
  const dateTolerance = whole(draft.dateTolerance, 0, 60, "The date tolerance");
  if (typeof dateTolerance === "string") return { error: dateTolerance };
  const duplicateWindow = whole(draft.duplicateWindow, 0, 180, "The duplicate window");
  if (typeof duplicateWindow === "string") return { error: duplicateWindow };

  const percent = Number(draft.nearLimitPercent);
  if (!draft.nearLimitPercent.trim() || Number.isNaN(percent) || percent < 0 || percent > 50) {
    return { error: "The near-limit tolerance must be between 0% and 50%." };
  }

  return {
    rules: {
      approval_limits: limits,
      round_number_floor: roundFloor,
      date_tolerance_days: dateTolerance,
      duplicate_window_days: duplicateWindow,
      // Back to the fraction the contract stores and the engine multiplies by.
      near_limit_tolerance: toFraction(percent),
      require_sign_off: draft.requireSignOff,
    },
  };
}

/**
 * A switch for the one boolean threshold. Local because `components/ui/` has no
 * toggle and this screen needs exactly one; it is a control, not a new
 * primitive for the rest of the app to grow around.
 */
function RuleSwitch({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors",
        checked ? "bg-brand-800" : "bg-slate-200",
        disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
      )}
    >
      <span
        className={cn(
          "h-4 w-4 rounded-full bg-white shadow-sm transition-transform",
          checked ? "translate-x-[18px]" : "translate-x-0.5",
        )}
      />
    </button>
  );
}

/** One threshold: what it is called, what it does to the audit, and its field. */
function RuleField({
  label,
  explanation,
  children,
}: {
  label: string;
  explanation: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 py-4 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
      <div className="min-w-0 sm:max-w-md">
        <p className="text-sm font-medium text-ink-900">{label}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-ink-400">{explanation}</p>
      </div>
      <div className="shrink-0 sm:w-44">{children}</div>
    </div>
  );
}

/** Status tone for a period row. Presentation only; the status is the case's. */
function periodTone(status: CaseStatus): string {
  if (status === "failed") return "bg-rose-50 text-rose-700 ring-rose-200";
  if (status === "ready_for_review") return "bg-emerald-50 text-emerald-700 ring-emerald-200";
  if (status === "approved" || status === "reported")
    return "bg-brand-50 text-brand-800 ring-brand-200";
  return "bg-slate-100 text-ink-600 ring-slate-200";
}

export default function ClientDetailPage() {
  const router = useRouter();
  const params = useParams<{ clientId: string }>();
  const clientId = params.clientId;

  const [client, setClient] = React.useState<ClientSummary | null>(null);
  const [periods, setPeriods] = React.useState<CaseSummary[] | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  const [draft, setDraft] = React.useState<RuleDraft | null>(null);
  const [saveBusy, setSaveBusy] = React.useState(false);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const [saved, setSaved] = React.useState(false);

  const load = React.useCallback(() => {
    setLoadError(null);
    setClient(null);
    setPeriods(null);
    setDraft(null);
    setSaved(false);
    getClient(clientId)
      .then((response) => {
        setClient(response.client);
        setPeriods(response.periods);
        setDraft(draftFrom(response.client.rules));
      })
      .catch((caught) =>
        setLoadError(
          caught instanceof ApiError ? caught.message : "Could not load the client.",
        ),
      );
  }, [clientId]);

  React.useEffect(load, [load]);

  const dirty =
    client !== null &&
    draft !== null &&
    JSON.stringify(draft) !== JSON.stringify(draftFrom(client.rules));

  const editDraft = (patch: Partial<RuleDraft>) => {
    setSaved(false);
    setSaveError(null);
    setDraft((current) => (current ? { ...current, ...patch } : current));
  };

  const submitRules = async () => {
    if (!draft || !client || saveBusy) return;
    const parsed = parseDraft(draft);
    if ("error" in parsed) {
      setSaveError(parsed.error);
      return;
    }
    setSaveBusy(true);
    setSaveError(null);
    try {
      // PATCH takes the whole rule block: the backend replaces it wholesale and
      // names what moved in the client's audit trail.
      const updated = await updateClient(client.client_id, { rules: parsed.rules });
      setClient(updated);
      // Re-seed from the response, not from the form: the backend sorts and
      // de-duplicates the approval limits, and the reader should see what was
      // actually stored.
      setDraft(draftFrom(updated.rules));
      setSaved(true);
    } catch (caught) {
      setSaveError(
        caught instanceof ApiError ? caught.message : "Could not save the thresholds.",
      );
    } finally {
      setSaveBusy(false);
    }
  };

  const openPeriod = (period: CaseSummary) => {
    // Exactly what the header's case switcher does: write the browser's saved
    // selection and let the workspace remount every screen against it.
    setActiveCaseId(period.case_id);
    router.push("/dashboard");
  };

  if (loadError) {
    return (
      <div>
        <Link
          href="/clients"
          className="mb-4 inline-flex items-center gap-1.5 text-xs font-medium text-ink-600 hover:text-brand-700"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
          All clients
        </Link>
        <ErrorState message={loadError} onRetry={load} />
      </div>
    );
  }

  if (!client || !draft || periods === null) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full lg:col-span-2" />
        </div>
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <Link
          href="/clients"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-ink-600 hover:text-brand-700"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
          All clients
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
          <h1 className="text-xl font-bold text-ink-900">{client.name}</h1>
          {client.reference && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-ink-600 ring-1 ring-slate-200">
              {client.reference}
            </span>
          )}
          {client.archived && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-600 ring-1 ring-slate-200">
              Archived
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-ink-600">
          {client.period_count} {client.period_count === 1 ? "period" : "periods"} run
          {client.last_period_end
            ? `, the last ending ${formatDate(client.last_period_end)}`
            : " so far"}
          . {client.pending_items} {client.pending_items === 1 ? "item" : "items"}{" "}
          still waiting on a human decision.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* The relationship's own facts */}
        <Card>
          <CardHeader>
            <CardTitle>Client</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <dl className="space-y-2">
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-xs text-ink-400">Currency</dt>
                <dd className="text-ink-900">{client.currency}</dd>
              </div>
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-xs text-ink-400">Language</dt>
                <dd className="text-ink-900">
                  {client.language === "ur" ? "اردو — Urdu" : "English"}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-xs text-ink-400">Relationship owner</dt>
                <dd className="min-w-0 truncate text-ink-900">
                  {client.relationship_owner ?? "-"}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-xs text-ink-400">Open evidence requests</dt>
                <dd className="text-ink-900 tabular-nums">
                  {client.open_evidence_requests}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-xs text-ink-400">Added</dt>
                <dd className="text-right text-xs text-ink-600">
                  {formatTimestamp(client.created_at)}
                </dd>
              </div>
              {client.last_activity_at && (
                <div className="flex items-baseline justify-between gap-3">
                  <dt className="text-xs text-ink-400">Last activity</dt>
                  <dd className="text-right text-xs text-ink-600">
                    {formatTimestamp(client.last_activity_at)}
                  </dd>
                </div>
              )}
            </dl>
            {client.notes && (
              <div className="border-t border-slate-100 pt-3">
                <p className="text-xs font-medium text-ink-400">Notes</p>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-ink-600">
                  {client.notes}
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* The thresholds this client is audited against */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Red-flag thresholds</CardTitle>
            <p className="mt-1 text-xs leading-relaxed text-ink-600">
              What the deterministic rules engine measures this client against.
              Each one only ever raises a flag for a human to look at; nothing
              here approves, rejects, or decides anything.
            </p>
          </CardHeader>
          <CardContent>
            <div className="divide-y divide-slate-100">
              <RuleField
                label="Approval limits"
                explanation="The amounts this client's own policy requires sign-off at. Entries that sit just under one are flagged as near-limit, and a day's entries that separately stay under one but together pass it are flagged as possible structuring."
              >
                <div className="space-y-2">
                  {draft.limits.map((limit, index) => (
                    <div key={index} className="flex items-center gap-1.5">
                      <Input
                        type="number"
                        min={1}
                        step={1}
                        inputMode="numeric"
                        aria-label={`Approval limit ${index + 1}`}
                        value={limit}
                        onChange={(event) =>
                          editDraft({
                            limits: draft.limits.map((existing, position) =>
                              position === index ? event.target.value : existing,
                            ),
                          })
                        }
                        className="text-right tabular-nums"
                      />
                      <button
                        type="button"
                        onClick={() =>
                          editDraft({
                            limits: draft.limits.filter(
                              (_, position) => position !== index,
                            ),
                          })
                        }
                        aria-label={`Remove approval limit ${index + 1}`}
                        title="Remove this limit"
                        className="rounded-md p-1.5 text-ink-400 transition-colors hover:bg-slate-100 hover:text-rose-600"
                      >
                        <X className="h-3.5 w-3.5" aria-hidden />
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() => editDraft({ limits: [...draft.limits, ""] })}
                    className="inline-flex items-center gap-1 text-xs font-medium text-brand-700 hover:underline"
                  >
                    <Plus className="h-3.5 w-3.5" aria-hidden />
                    Add a limit
                  </button>
                  <p className="text-[11px] text-ink-400">
                    In {client.currency}. Saved sorted, duplicates dropped.
                  </p>
                </div>
              </RuleField>

              <RuleField
                label="Near-limit tolerance"
                explanation="How close beneath an approval limit an amount has to sit before it is flagged as suspiciously just-under. At 2%, an entry of 98,500 against a 100,000 limit is flagged."
              >
                <Input
                  type="number"
                  min={0}
                  max={50}
                  step={0.5}
                  inputMode="decimal"
                  aria-label="Near-limit tolerance, percent"
                  value={draft.nearLimitPercent}
                  onChange={(event) =>
                    editDraft({ nearLimitPercent: event.target.value })
                  }
                  className="text-right tabular-nums"
                  hint="Percent of the limit, 0 to 50."
                />
              </RuleField>

              <RuleField
                label="Round-number floor"
                explanation="At or above this amount, a suspiciously round figure — a whole multiple of 1,000 — is flagged for a look. Below it, round numbers are ordinary and are left alone."
              >
                <Input
                  type="number"
                  min={0}
                  step={1000}
                  inputMode="numeric"
                  aria-label="Round-number floor"
                  value={draft.roundFloor}
                  onChange={(event) => editDraft({ roundFloor: event.target.value })}
                  className="text-right tabular-nums"
                  hint={`In ${client.currency}.`}
                />
              </RuleField>

              <RuleField
                label="Date tolerance"
                explanation="How many days apart a ledger entry and a bank line may fall and still be treated as the same payment. Widen it for a client whose bank posts late; narrow it for tighter matching."
              >
                <Input
                  type="number"
                  min={0}
                  max={60}
                  step={1}
                  inputMode="numeric"
                  aria-label="Date tolerance in days"
                  value={draft.dateTolerance}
                  onChange={(event) => editDraft({ dateTolerance: event.target.value })}
                  className="text-right tabular-nums"
                  hint="Days, 0 to 60."
                />
              </RuleField>

              <RuleField
                label="Duplicate window"
                explanation="Two entries for the same party and the same amount within this many days are flagged as a possible duplicate payment."
              >
                <Input
                  type="number"
                  min={0}
                  max={180}
                  step={1}
                  inputMode="numeric"
                  aria-label="Duplicate window in days"
                  value={draft.duplicateWindow}
                  onChange={(event) =>
                    editDraft({ duplicateWindow: event.target.value })
                  }
                  className="text-right tabular-nums"
                  hint="Days, 0 to 180."
                />
              </RuleField>

              <RuleField
                label="Require sign-off"
                explanation="Maker–checker. With this on, a report cannot be generated for this client until somebody other than the person who decided the items has signed the engagement off."
              >
                <div className="flex items-center gap-2 sm:justify-end">
                  <RuleSwitch
                    checked={draft.requireSignOff}
                    onChange={(next) => editDraft({ requireSignOff: next })}
                    label="Require sign-off before a report"
                    disabled={saveBusy}
                  />
                  <span className="text-xs text-ink-600">
                    {draft.requireSignOff ? "Required" : "Not required"}
                  </span>
                </div>
              </RuleField>
            </div>

            <div className="mt-4 rounded-md bg-slate-50 px-3 py-2.5 text-[11px] leading-relaxed text-ink-600 ring-1 ring-slate-200">
              Thresholds are applied when a period is processed, so a change here
              shapes the <strong className="font-semibold">next</strong> period
              you upload for this client. Periods already run keep the rules they
              were run under and the decisions their auditor recorded; Tarazu
              does not recompute a queue somebody has already reviewed. What you
              changed, and when, is written to the audit trail.
            </div>

            {saveError && (
              <p className="mt-3 rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
                {saveError}
              </p>
            )}

            <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
              {saved && !dirty && (
                <span className="mr-auto text-xs text-emerald-700">
                  Saved. In effect from the next period processed.
                </span>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSaveError(null);
                  setSaved(false);
                  setDraft(draftFrom(client.rules));
                }}
                disabled={saveBusy || !dirty}
              >
                Discard changes
              </Button>
              <Button size="sm" onClick={submitRules} disabled={saveBusy || !dirty}>
                {saveBusy ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                ) : (
                  <Save className="h-3.5 w-3.5" aria-hidden />
                )}
                Save thresholds
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* The relationship as history */}
      <div>
        <div className="mb-2 flex items-end justify-between">
          <div>
            <h2 className="text-base font-semibold text-ink-900">Periods</h2>
            <p className="mt-0.5 text-xs text-ink-600">
              Every engagement run for this client, newest first. Open one to
              point the whole workspace at it.
            </p>
          </div>
          <Link href="/upload">
            <Button size="sm" variant="outline">
              <Upload className="h-3.5 w-3.5" aria-hidden />
              New period
            </Button>
          </Link>
        </div>

        {periods.length === 0 ? (
          <EmptyState
            title="No periods yet"
            message="Upload this client's bank statement, invoices, and ledger to run its first period. It will inherit the thresholds above."
            action={
              <Link href="/upload">
                <Button size="sm">Go to upload</Button>
              </Link>
            }
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
            <table className="w-full min-w-[860px] text-left">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                  <th className="px-4 py-2.5">Period</th>
                  <th className="px-4 py-2.5">Case id</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5 text-right">Items</th>
                  <th className="px-4 py-2.5 text-right">Pending</th>
                  <th className="px-4 py-2.5 text-right">Flagged</th>
                  <th className="px-4 py-2.5">Created</th>
                </tr>
              </thead>
              <tbody>
                {periods.map((period) => (
                  <tr
                    key={period.case_id}
                    onClick={() => openPeriod(period)}
                    className="cursor-pointer border-b border-slate-100 text-sm last:border-0 hover:bg-slate-50/60"
                  >
                    <td className="whitespace-nowrap px-4 py-3 font-medium text-ink-900">
                      {period.period_start && period.period_end
                        ? `${formatDate(period.period_start)} to ${formatDate(period.period_end)}`
                        : "Period not set"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-ink-600">
                      {period.case_id}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <span
                        className={cn(
                          "inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ring-1",
                          periodTone(period.status),
                        )}
                      >
                        {period.status.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                      {period.total_review_items}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                      {period.pending_items}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                      {period.flagged_items}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-ink-600">
                      {formatTimestamp(period.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
