"use client";

/**
 * Small pieces shared by the settings panels. Not a route.
 *
 * The panels follow one flat pattern: a large panel title (SectionHeader),
 * bold sub-sections (SettingsSection), and hairline-divided rows with the
 * control right-aligned (SettingRow). No boxed cards.
 */

import * as React from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ApiKeyScope } from "@/lib/types";

/** The large title a panel opens with, plus an optional primary action. */
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
    <div className="mb-6 flex flex-wrap items-start justify-between gap-x-6 gap-y-3 border-b border-slate-200 pb-4">
      <div className="max-w-xl">
        <h2 className="text-xl font-semibold tracking-tight text-ink-900">
          {title}
        </h2>
        {description && (
          <p className="mt-1 text-sm leading-relaxed text-ink-600">{description}</p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

/** A bold sub-section within a panel: heading, optional intro, divided rows. */
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
    <section className={cn("mb-10 last:mb-0", className)}>
      <h3 className="text-base font-semibold text-ink-900">{title}</h3>
      {description && <p className="mt-1 text-sm text-ink-600">{description}</p>}
      <div className="mt-2 divide-y divide-slate-100">{children}</div>
    </section>
  );
}

/** A flat settings row: name and purpose on the left, control on the right. */
export function SettingRow({
  name,
  description,
  value,
  action,
}: {
  name: string;
  description: string;
  value?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-6 py-4">
      <div className="min-w-0 max-w-md">
        <p className="text-sm font-medium text-ink-900">{name}</p>
        <p className="mt-0.5 text-xs text-ink-400">{description}</p>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        {value !== undefined && (
          <div className="text-right text-sm text-ink-900">{value}</div>
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

/** A disabled toggle for controls whose delivery has not shipped yet. */
export function DeadToggle({ title }: { title: string }) {
  return (
    <span
      className="relative inline-flex h-5 w-9 shrink-0 cursor-not-allowed items-center rounded-full bg-slate-200 opacity-60"
      title={title}
      aria-disabled
    >
      <span className="ml-0.5 h-4 w-4 rounded-full bg-white shadow-sm" />
    </span>
  );
}
