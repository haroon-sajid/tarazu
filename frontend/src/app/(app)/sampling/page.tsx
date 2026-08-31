"use client";

/**
 * Sampling — substantive testing you can defend six months later.
 *
 * An auditor rarely tests a whole population; they test a sample and say
 * exactly how it was drawn. That second half is the part that usually goes
 * missing, and it is the part a reviewer asks about: *why these twenty items?*
 * So this screen is built around the answer rather than the list — the seed,
 * the method note in working-paper language, and a per-item reason travel with
 * every draw.
 *
 * Nothing here computes. The selection, the totals, the coverage, and the note
 * are all produced by the backend's deterministic sampling module (reliability
 * rule 2) — a sample a model picked would be a sample nobody could reproduce.
 * This page collects three inputs, shows what came back, and links each row to
 * the review screen where a human still decides.
 *
 * The seed is given the prominence it deserves: supplying the same seed, method,
 * and size over the same population reproduces this exact sample. That is what
 * makes the selection evidence instead of an anecdote.
 */

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  Check,
  Copy,
  Dices,
  Info,
  Loader2,
  TriangleAlert,
} from "lucide-react";
import { ApiError, drawSample } from "@/lib/api";
import type { MatchStatus, SampleResponse, SamplingMethod } from "@/lib/types";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/badge";
import { EmptyState, ErrorState } from "@/components/ui/states";

/**
 * One line per method, and precise about what each one does and does not
 * support. The wording matters: presenting a judgemental pick as a statistical
 * sample overstates the evidence in the file.
 */
const METHODS: {
  value: SamplingMethod;
  label: string;
  line: string;
  statistical: boolean;
}[] = [
  {
    value: "monetary_unit",
    label: "Monetary-unit (probability proportional to size)",
    line:
      "The sampling unit is one rupee, not one row, so an item's chance of selection is proportional to its amount — and any item larger than the sampling interval is near-certain to be picked, which is how you test the money rather than the rows. Items with a zero or negative amount are excluded; the note says how many.",
    statistical: true,
  },
  {
    value: "random",
    label: "Random (simple, without replacement)",
    line:
      "Every item is equally likely, whatever it is worth. That is its virtue and its limit: it says something about the population's rows and very little about its money, since a population where one payment is most of the value will usually not include it.",
    statistical: true,
  },
  {
    value: "high_value",
    label: "High value (largest amounts)",
    line:
      "The largest amounts, in descending order. Legitimate, targeted work — and not a statistical sample: the items were chosen because they are large, so nothing observed in them may be projected over the items that were not chosen.",
    statistical: false,
  },
];

const METHOD_LABEL: Record<SamplingMethod, string> = {
  random: "Random",
  monetary_unit: "Monetary-unit",
  high_value: "High value",
};

const KNOWN_STATUSES: MatchStatus[] = ["matched", "partial", "unmatched"];

function MatchCell({ status }: { status: string }) {
  const known = KNOWN_STATUSES.find((candidate) => candidate === status);
  if (known) return <StatusBadge status={known} />;
  return <span className="text-xs text-ink-600">{status}</span>;
}

/** Copy one value to the clipboard. Page-local affordance, no new primitive. */
function CopyValue({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = React.useState(false);
  return (
    <Button
      size="sm"
      variant="outline"
      aria-label={`Copy ${label}`}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1800);
        } catch {
          // The clipboard can be blocked; the value stays selectable on screen.
        }
      }}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden />
      ) : (
        <Copy className="h-3.5 w-3.5" aria-hidden />
      )}
      {copied ? "Copied" : "Copy seed"}
    </Button>
  );
}

function Stat({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <Card>
      <CardContent className="px-3.5 py-3.5 sm:px-5 sm:py-4">
        <p className="text-xs font-medium leading-tight text-ink-400">{label}</p>
        <p className="mt-1 break-words text-xl font-bold tabular-nums text-ink-900 sm:text-2xl">
          {value}
        </p>
        {detail && (
          <p className="mt-0.5 text-[11px] leading-snug text-ink-400">{detail}</p>
        )}
      </CardContent>
    </Card>
  );
}

export default function SamplingPage() {
  const [method, setMethod] = React.useState<SamplingMethod>("monetary_unit");
  const [size, setSize] = React.useState("10");
  const [seed, setSeed] = React.useState("");

  const [busy, setBusy] = React.useState(false);
  const [sample, setSample] = React.useState<SampleResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  /** A 501 is "this needs the live backend", not a failure to explain away. */
  const [unavailable, setUnavailable] = React.useState<string | null>(null);

  const chosen = METHODS.find((entry) => entry.value === method) ?? METHODS[0];
  const parsedSize = Number.parseInt(size, 10);
  const sizeValid = Number.isFinite(parsedSize) && parsedSize >= 1 && parsedSize <= 500;
  const parsedSeed = seed.trim() === "" ? null : Number.parseInt(seed.trim(), 10);
  const seedValid =
    parsedSeed === null ||
    (Number.isFinite(parsedSeed) && parsedSeed >= 0 && parsedSeed <= 2147483647);

  const submit = async () => {
    if (busy || !sizeValid || !seedValid) return;
    setBusy(true);
    setError(null);
    setUnavailable(null);
    try {
      setSample(
        await drawSample({
          method,
          size: parsedSize,
          ...(parsedSeed === null ? {} : { seed: parsedSeed }),
        }),
      );
    } catch (caught) {
      setSample(null);
      if (caught instanceof ApiError && caught.status === 501) {
        setUnavailable(caught.message);
      } else {
        setError(
          caught instanceof ApiError ? caught.message : "Could not draw the sample.",
        );
      }
    } finally {
      setBusy(false);
    }
  };

  // The currency the backend put on the selected rows. Used as a label only;
  // no amount on this page is added up or converted here.
  const currency = sample?.items[0]?.currency ?? "";
  const money = (amount: string) => (currency ? `${currency} ${amount}` : amount);

  return (
    <div className="pb-20 md:pb-0">
      <div className="mb-5">
        <h1 className="text-xl font-bold text-ink-900">Sampling</h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-600">
          Draw a subset of the case's population for substantive testing, and
          keep the record of how it was drawn. The selection, the totals, and
          the coverage are computed by deterministic code — never by a model —
          and every draw comes back with the seed that reproduces it.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        {/* The three inputs */}
        <Card className="h-fit">
          <CardContent className="space-y-4 px-4 py-4 sm:px-5 sm:py-5">
            <Select
              label="Method"
              value={method}
              onChange={(event) => setMethod(event.target.value as SamplingMethod)}
            >
              {METHODS.map((entry) => (
                <option key={entry.value} value={entry.value}>
                  {entry.label}
                </option>
              ))}
            </Select>
            <p
              className={cn(
                "rounded-md px-3 py-2 text-[11px] leading-relaxed ring-1",
                chosen.statistical
                  ? "bg-slate-50 text-ink-600 ring-slate-200"
                  : "bg-amber-50 text-amber-900 ring-amber-300",
              )}
            >
              {!chosen.statistical && (
                <TriangleAlert
                  className="mr-1 inline h-3.5 w-3.5 align-[-2px]"
                  aria-hidden
                />
              )}
              {chosen.line}
            </p>

            <Input
              label="Sample size"
              type="number"
              min={1}
              max={500}
              value={size}
              onChange={(event) => setSize(event.target.value)}
              hint="1 to 500. A size at or above the population tests all of it — a census, and the note will say so."
            />
            <Input
              label="Seed (optional)"
              type="number"
              min={0}
              max={2147483647}
              value={seed}
              onChange={(event) => setSeed(event.target.value)}
              placeholder="Leave blank to generate one"
              hint="Paste the seed from an earlier draw to reproduce it exactly. Left blank, one is generated and returned."
            />

            {!sizeValid && size.trim() !== "" && (
              <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
                The sample size must be a whole number between 1 and 500.
              </p>
            )}
            {!seedValid && (
              <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
                A seed must be a whole number between 0 and 2,147,483,647.
              </p>
            )}

            <Button
              className="w-full"
              onClick={submit}
              disabled={busy || !sizeValid || !seedValid}
            >
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <Dices className="h-4 w-4" aria-hidden />
              )}
              {busy ? "Drawing" : "Draw sample"}
            </Button>
            <p className="text-[11px] leading-relaxed text-ink-400">
              Drawing a sample decides nothing. It says which items a person
              should look at; the person still looks, and still approves or
              rejects each one on the review screen.
            </p>
          </CardContent>
        </Card>

        {/* What came back */}
        <div className="min-w-0">
          {unavailable ? (
            <div className="rounded-lg border border-sky-200 bg-sky-50/70 px-5 py-8 text-center">
              <Info className="mx-auto h-8 w-8 text-sky-500" aria-hidden />
              <p className="mt-3 text-sm font-semibold text-sky-900">
                Sampling needs the live backend
              </p>
              <p className="mx-auto mt-1 max-w-md text-sm text-sky-800">{unavailable}</p>
              <p className="mx-auto mt-2 max-w-md text-xs text-sky-700">
                A sample has to be drawn from the case's real population by the
                deterministic sampling module. Inventing one in the browser
                would produce a selection nobody could reproduce or defend, so
                this screen waits for the backend instead.
              </p>
            </div>
          ) : error ? (
            <ErrorState message={error} onRetry={submit} />
          ) : busy ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
                {Array.from({ length: 4 }).map((_, index) => (
                  <Skeleton key={index} className="h-24" />
                ))}
              </div>
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-64 w-full" />
            </div>
          ) : sample === null ? (
            <EmptyState
              title="No sample drawn yet"
              message="Pick a method and a size on the left, then draw. The seed that produced the sample comes back with it, so the same draw can be repeated and defended later."
            />
          ) : (
            <div className="space-y-4">
              {/* Figures, all counted by the backend */}
              <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
                <Stat
                  label="Population"
                  value={String(sample.population_size)}
                  detail={`${money(sample.population_amount)} in the case`}
                />
                <Stat
                  label="Sample"
                  value={String(sample.sample_size)}
                  detail={`${money(sample.sample_amount)} selected`}
                />
                <Stat
                  label="Coverage"
                  value={`${sample.coverage_percent}%`}
                  detail="Share of the population's value tested"
                />
                <Stat
                  label="Method"
                  value={METHOD_LABEL[sample.method]}
                  detail={
                    sample.method === "high_value"
                      ? "Judgemental — not a statistical sample"
                      : "Statistical selection"
                  }
                />
              </div>

              {/* The seed. The single thing that makes this defensible. */}
              <Card className="border-brand-200 bg-brand-50/50">
                <CardContent className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-4 sm:px-5">
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-ink-400">Seed used</p>
                    <p className="mt-0.5 break-all font-mono text-xl font-bold text-brand-900">
                      {sample.seed}
                    </p>
                    <p className="mt-1 max-w-lg text-[11px] leading-relaxed text-ink-600">
                      Put this seed back in the field on the left, with the same
                      method and size, and the same population returns this
                      exact sample. That reproducibility is what makes the
                      selection defensible rather than an anecdote — record it
                      in the working paper.
                    </p>
                  </div>
                  <CopyValue value={String(sample.seed)} label="the seed" />
                </CardContent>
              </Card>

              {/* The note, verbatim: this is the working-paper wording */}
              <Card>
                <CardContent className="px-4 py-4 sm:px-5">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                    How this sample was drawn
                  </p>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-ink-900">
                    {sample.method_note}
                  </p>
                  <p className="mt-2 text-[11px] text-ink-400">
                    Written by the sampling module and shown word for word —
                    this is the paragraph that belongs in the file.
                  </p>
                </CardContent>
              </Card>

              {/* The selected items */}
              {sample.items.length === 0 ? (
                <EmptyState
                  title="Nothing was selected"
                  message="The draw returned no items. The note above says why — usually an empty population, or a monetary-unit draw over a population with no positive amounts."
                />
              ) : (
                <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
                  <table className="w-full min-w-[960px] text-left">
                    <thead>
                      <tr className="border-b border-slate-200 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                        <th className="px-4 py-2.5">Item</th>
                        <th className="px-4 py-2.5">Party</th>
                        <th className="px-4 py-2.5">Date</th>
                        <th className="px-4 py-2.5 text-right">Amount</th>
                        <th className="px-4 py-2.5">Match</th>
                        <th className="px-4 py-2.5 text-right">Flags</th>
                        <th className="px-4 py-2.5">Why it was selected</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sample.items.map((item) => (
                        <tr
                          key={item.review_item_id}
                          className="border-b border-slate-100 align-top text-sm last:border-0 hover:bg-slate-50/60"
                        >
                          <td className="whitespace-nowrap px-4 py-3">
                            <Link
                              href={`/review?item=${encodeURIComponent(item.review_item_id)}`}
                              className="inline-flex items-center gap-1 font-mono text-xs text-brand-700 hover:underline"
                            >
                              {item.review_item_id}
                              <ArrowRight className="h-3 w-3" aria-hidden />
                            </Link>
                          </td>
                          <td className="px-4 py-3 font-medium text-ink-900">
                            {item.party_name}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3 text-xs text-ink-600">
                            {formatDate(item.date)}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                            {item.currency} {item.amount}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3">
                            <MatchCell status={item.match_status} />
                          </td>
                          <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                            {item.flag_count}
                          </td>
                          <td className="max-w-md px-4 py-3 text-xs leading-relaxed text-ink-600">
                            {item.reason}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <p className="text-[11px] leading-relaxed text-ink-400">
                Case {sample.case_id}. The draw is recorded in the case's
                immutable audit trail as {sample.audit_record.audit_id}, so the
                file shows when this sample was taken and by whom.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
