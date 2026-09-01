"use client";

/**
 * Small pieces shared by the settings panels. Not a route.
 *
 * The panels follow one pattern: the panel title under the layout's group
 * eyebrow (SectionHeader), then boxed white cards (SettingsSection) holding
 * hairline-divided rows with the control right-aligned (SettingRow) — or,
 * for wide controls, stacked under their label.
 */

import * as React from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ApiKeyScope } from "@/lib/types";

/** The panel title that sits under the group eyebrow, plus an optional primary action. */
export function SectionHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
      <div className="max-w-3xl">
        <h2 className="text-2xl font-bold tracking-tight text-ink-900">{title}</h2>
        {description && (
          <p className="mt-1.5 text-sm leading-relaxed text-ink-600">{description}</p>
        )}
      </div>
      {action && <div className="shrink-0 pt-1">{action}</div>}
    </div>
  );
}

/** A boxed card within a panel: heading, optional intro, divided rows. */
export function SettingsSection({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "mb-5 rounded-xl border border-slate-200 bg-white px-4 py-5 shadow-sm last:mb-0 md:px-6",
        className,
      )}
    >
      <h3 className="text-[15px] font-semibold text-ink-900">{title}</h3>
      {description && <p className="mt-1 text-[13px] text-ink-500">{description}</p>}
      <div className="mt-3 divide-y divide-slate-100">{children}</div>
    </section>
  );
}

/**
 * One setting: name and purpose, then its control. Right-aligned by default;
 * `stacked` puts a wide control (a select, an input) under the label instead.
 *
 * Below md the default row is allowed to wrap: a narrow control (a toggle, a
 * badge) stays beside the label, a wide one (a button, a long value) moves
 * under it, and a long unbreakable value (an id, a URL) breaks rather than
 * pushing the card wider than the screen. From md up the row is unchanged.
 */
export function SettingRow({
  name,
  description,
  value,
  action,
  stacked = false,
}: {
  name: string;
  description: string;
  value?: React.ReactNode;
  action?: React.ReactNode;
  stacked?: boolean;
}) {
  if (stacked) {
    return (
      <div className="py-4">
        <p className="text-[13px] font-semibold text-ink-900">{name}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-ink-500">{description}</p>
        {value !== undefined && (
          <div className="mt-2.5 text-sm text-ink-900">{value}</div>
        )}
        {action && <div className="mt-2.5">{action}</div>}
      </div>
    );
  }
  return (
    <div className="flex items-center justify-between gap-6 py-4 max-md:flex-wrap max-md:gap-y-3">
      <div className="min-w-0 max-w-2xl max-md:grow max-md:basis-40">
        <p className="text-[13px] font-semibold text-ink-900">{name}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-ink-500">{description}</p>
      </div>
      <div className="flex shrink-0 items-center gap-3 max-md:min-w-0 max-md:shrink">
        {value !== undefined && (
          <div className="text-right text-sm text-ink-900 max-md:min-w-0 max-md:break-words max-md:text-left">
            {value}
          </div>
        )}
        {action}
      </div>
    </div>
  );
}

export function PlannedBadge() {
  return (
    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-400 ring-1 ring-slate-200">
      Planned
    </span>
  );
}

/** Active / Revoked / neutral status pill, shared by the members and API-key tables. */
export function StatePill({
  tone,
  children,
  title,
}: {
  tone: "positive" | "negative" | "neutral";
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-semibold",
        tone === "positive" && "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
        tone === "negative" && "bg-rose-50 text-rose-700 ring-1 ring-rose-200",
        tone === "neutral" && "bg-slate-100 text-ink-600 ring-1 ring-slate-200",
      )}
    >
      {children}
    </span>
  );
}

export function ScopePill({ scope }: { scope: ApiKeyScope }) {
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        scope === "write"
          ? "bg-amber-50 text-amber-700 ring-1 ring-amber-300"
          : "bg-slate-100 text-ink-600 ring-1 ring-slate-200",
      )}
    >
      {scope}
    </span>
  );
}

export function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = React.useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1800);
        } catch {
          // Clipboard can be blocked; the value stays selectable on screen.
        }
      }}
      className="inline-flex items-center gap-1 text-xs font-medium text-brand-700 hover:underline"
      aria-label={`Copy ${label}`}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden />
      ) : (
        <Copy className="h-3.5 w-3.5" aria-hidden />
      )}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

/** A working switch, visually identical to DeadToggle when off. */
export function Toggle({
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
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2",
        checked ? "bg-emerald-500" : "bg-slate-300",
        disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
      )}
    >
      <span
        className={cn(
          "h-5 w-5 rounded-full bg-white shadow-sm transition-transform",
          checked ? "translate-x-[22px]" : "translate-x-0.5",
        )}
      />
    </button>
  );
}

/** A disabled toggle for controls whose delivery has not shipped yet. */
export function DeadToggle({ title }: { title: string }) {
  return (
    <span
      className="relative inline-flex h-6 w-11 shrink-0 cursor-not-allowed items-center rounded-full bg-slate-300 opacity-60"
      title={title}
      aria-disabled
    >
      <span className="ml-0.5 h-5 w-5 rounded-full bg-white shadow-sm" />
    </span>
  );
}
