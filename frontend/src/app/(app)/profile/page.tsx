"use client";

/**
 * User profile — the identity every decision is recorded against. The top
 * card states who this is and which organization scopes their requests; the
 * table below is their working record: every approve and reject in this
 * case, straight from the review items the backend serves.
 */

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Building2,
  CircleUserRound,
  KeyRound,
  LogOut,
  ShieldCheck,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError, FIXTURE_MODE, getProfile, getReviewItems } from "@/lib/api";
import type { ReviewItem, UserProfile } from "@/lib/types";
import { formatDate, formatMoney, formatTimestamp } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { DecisionBadge, MatchStrengthBadge, StatusBadge } from "@/components/ui/badge";

type Tab = "decisions" | "pending";

function FactRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <dt className="text-sm text-ink-400">{label}</dt>
      <dd
        className={
          mono ? "font-mono text-xs text-ink-900" : "text-sm font-medium text-ink-900"
        }
      >
        {value ?? "-"}
      </dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-slate-100 pb-4 last:border-0 last:pb-0">
      <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
        {title}
      </h3>
      <dl className="divide-y divide-slate-50">{children}</dl>
    </section>
  );
}

export default function ProfilePage() {
  const { session, signOut } = useAuth();
  const router = useRouter();
  const [items, setItems] = React.useState<ReviewItem[] | null>(null);
  const [profile, setProfile] = React.useState<UserProfile | null>(null);
  const [tab, setTab] = React.useState<Tab>("decisions");

  React.useEffect(() => {
    let cancelled = false;
    getReviewItems()
      .then((response) => !cancelled && setItems(response.items))
      .catch((caught) => {
        // No case yet is fine — the activity table just stays empty.
        if (!cancelled && caught instanceof ApiError) setItems([]);
      });
    getProfile()
      .then((loaded) => !cancelled && setProfile(loaded))
      .catch(() => {
        // An unfilled profile is a normal state; the fallbacks stand in.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!session) return null; // the (app) layout guard is redirecting

  const organizationName =
    session.organizationName ?? (FIXTURE_MODE ? "Demo Audit Firm" : null);
  const role = session.role ?? (FIXTURE_MODE ? "owner" : null);
  const localPart = session.email.split("@")[0] ?? "auditor";
  const displayName =
    profile?.full_name ?? localPart.charAt(0).toUpperCase() + localPart.slice(1);
  const initial = (session.email[0] ?? "A").toUpperCase();

  const decided = (items ?? []).filter((item) => item.decision !== "pending");
  const pending = (items ?? []).filter((item) => item.decision === "pending");
  const visible = tab === "decisions" ? decided : pending;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-ink-900">User profile</h1>
        <p className="mt-1 text-sm text-ink-600">
          Every approval and rejection you record lands in the immutable audit
          trail under this identity.
        </p>
      </div>

      {/* Identity card */}
      <Card>
        <CardContent className="grid grid-cols-[16rem_minmax(0,1fr)] gap-8 p-6">
          {/* Left: the person */}
          <div className="flex flex-col items-center border-r border-slate-100 pr-8 text-center">
            {profile?.avatar ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={profile.avatar}
                alt="Your profile picture"
                className="h-24 w-24 rounded-full object-cover ring-1 ring-slate-200"
              />
            ) : (
              <span className="flex h-24 w-24 items-center justify-center rounded-full bg-brand-800 text-4xl font-bold text-white">
                {initial}
              </span>
            )}
            <p className="mt-4 text-lg font-bold text-ink-900">{displayName}</p>
            {profile?.job_title && (
              <p className="text-xs font-medium text-ink-600">{profile.job_title}</p>
            )}
            <p className="text-xs text-ink-400">{session.email}</p>
            {role && (
              <span className="mt-2 inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium capitalize text-emerald-700 ring-1 ring-emerald-200">
                <ShieldCheck className="h-3 w-3" aria-hidden />
                {role}
              </span>
            )}
            <div className="mt-5 grid w-full grid-cols-2 gap-2">
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <p className="text-xl font-bold text-ink-900 tabular-nums">
                  {items === null ? "…" : decided.length}
                </p>
                <p className="text-[10px] text-ink-400">Decisions made</p>
              </div>
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <p className="text-xl font-bold text-ink-900 tabular-nums">
                  {items === null ? "…" : pending.length}
                </p>
                <p className="text-[10px] text-ink-400">Awaiting you</p>
              </div>
            </div>
          </div>

          {/* Right: the facts */}
          <div className="space-y-4">
            <Section title="Account">
              <FactRow label="Email" value={session.email} />
              <FactRow label="User id" value={session.userId} mono />
              <FactRow
                label="Session expires"
                value={formatTimestamp(new Date(session.expiresAt).toISOString())}
              />
            </Section>
            <Section title="Personal">
              <FactRow
                label="Gender"
                value={
                  profile?.gender ? (
                    <span className="capitalize">{profile.gender}</span>
                  ) : null
                }
              />
              <FactRow
                label="Date of birth"
                value={profile?.date_of_birth ? formatDate(profile.date_of_birth) : null}
              />
              <FactRow label="Location" value={profile?.location} />
              <FactRow label="Phone" value={profile?.phone} />
            </Section>
            <Section title="Professional">
              <FactRow label="Job title" value={profile?.job_title} />
              <FactRow
                label="License / membership no."
                value={profile?.license_number}
                mono
              />
            </Section>
            <Section title="Preferences">
              <FactRow
                label="Language"
                value={
                  profile?.language === "ur"
                    ? "اردو (Urdu)"
                    : profile?.language === "en"
                      ? "English"
                      : null
                }
              />
              <FactRow
                label="Notifications"
                value={
                  profile
                    ? [
                        profile.notify_case_ready && "Case ready",
                        profile.notify_high_severity && "High severity",
                        profile.notify_weekly_digest && "Weekly summary",
                      ]
                        .filter(Boolean)
                        .join(" · ") || "Off"
                    : null
                }
              />
            </Section>
            <Section title="Organization">
              <FactRow
                label="Name"
                value={
                  <span className="inline-flex items-center gap-1.5">
                    <Building2 className="h-3.5 w-3.5 text-ink-400" aria-hidden />
                    {organizationName ?? "-"}
                  </span>
                }
              />
              <FactRow
                label="Organization id"
                value={session.orgId ?? (FIXTURE_MODE ? "ORG-FIXTURE-0001" : null)}
                mono
              />
            </Section>
            <Section title="Security">
              <FactRow
                label="Password"
                value={
                  <Link
                    href="/settings/account"
                    className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline"
                  >
                    Change password <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                  </Link>
                }
              />
              <FactRow
                label="API keys"
                value={
                  <Link
                    href="/settings/api-keys"
                    className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline"
                  >
                    <KeyRound className="h-3.5 w-3.5" aria-hidden /> Manage keys
                  </Link>
                }
              />
            </Section>
            <div className="flex justify-end gap-2">
              <Link href="/settings/profile">
                <Button size="sm">Edit profile</Button>
              </Link>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  signOut();
                  router.replace("/login");
                }}
              >
                <LogOut className="h-3.5 w-3.5" aria-hidden />
                Sign out
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Activity */}
      <Card className="mt-5">
        <CardHeader className="border-b border-slate-100">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <CircleUserRound className="h-4 w-4 text-brand-700" aria-hidden />
              Your activity
            </CardTitle>
            <div className="flex gap-1">
              {(
                [
                  { key: "decisions", label: `Decisions (${decided.length})` },
                  { key: "pending", label: `Awaiting you (${pending.length})` },
                ] as { key: Tab; label: string }[]
              ).map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setTab(key)}
                  className={cn(
                    "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                    tab === key
                      ? "bg-brand-800 text-white"
                      : "bg-slate-100 text-ink-600 hover:bg-slate-200 hover:text-ink-900",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {items === null ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-10 w-full" />
              ))}
            </div>
          ) : visible.length === 0 ? (
            <p className="px-5 py-8 text-center text-sm text-ink-400">
              {tab === "decisions"
                ? "No decisions recorded yet. Every verdict you give on the review screen appears here."
                : "Nothing is waiting on you. Every item has a decision."}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[880px] text-left">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                    <th className="px-5 py-2.5">Decision</th>
                    <th className="px-4 py-2.5">When</th>
                    <th className="px-4 py-2.5">Party</th>
                    <th className="px-4 py-2.5 text-right">Amount</th>
                    <th className="px-4 py-2.5">Match</th>
                    <th className="px-4 py-2.5">Description</th>
                    <th className="px-4 py-2.5 text-right" aria-label="Open" />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((item) => (
                    <tr
                      key={item.review_item_id}
                      className="border-b border-slate-100 text-sm last:border-0 hover:bg-slate-50/60"
                    >
                      <td className="whitespace-nowrap px-5 py-3">
                        <DecisionBadge decision={item.decision} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-ink-600">
                        {item.decided_at
                          ? formatTimestamp(item.decided_at)
                          : formatDate(item.ledger_entry.date)}
                      </td>
                      <td className="max-w-48 truncate px-4 py-3 font-medium text-ink-900">
                        {item.ledger_entry.party_name}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                        {formatMoney(item.ledger_entry.amount, item.ledger_entry.currency)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span className="inline-flex items-center gap-1.5">
                          <StatusBadge status={item.match.status} />
                          <MatchStrengthBadge strength={item.match.match_strength} />
                        </span>
                      </td>
                      <td className="max-w-80 px-4 py-3">
                        <span className="block truncate text-xs text-ink-600">
                          {item.rejection_reason ?? item.match.reason}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        <Link
                          href={`/review?item=${encodeURIComponent(item.review_item_id)}`}
                          className="inline-flex items-center gap-1 font-mono text-[10px] text-brand-700 hover:underline"
                        >
                          {item.review_item_id}
                          <ArrowRight className="h-3 w-3" aria-hidden />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
