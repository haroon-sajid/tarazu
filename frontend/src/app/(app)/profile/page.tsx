"use client";

/**
 * User profile — the identity every decision is recorded against. One card:
 * who this is at the top with their working record (decisions made, items
 * awaiting them, straight from the review items the backend serves), then
 * every fact the backend holds about them as read-only fields in a grid.
 * Editing happens on Settings → Profile; this screen only shows.
 */

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, KeyRound, LogOut, Pencil, ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError, FIXTURE_MODE, getProfile, getReviewItems } from "@/lib/api";
import type { ReviewItem, UserProfile } from "@/lib/types";
import { formatDate, formatTimestamp } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

/** A read-only field: label above, value in an input-shaped box. */
function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  const empty = value === null || value === undefined || value === "";
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium text-ink-600">{label}</p>
      <div
        className={cn(
          "flex min-h-[42px] items-center rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm wrap-anywhere text-ink-900",
          mono && "break-all font-mono text-xs",
          empty && "text-ink-400",
        )}
      >
        {empty ? "-" : value}
      </div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-slate-200 pt-6">
      <h3 className="mb-4 text-base font-semibold text-ink-900">{title}</h3>
      <div className="grid grid-cols-1 gap-x-4 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
        {children}
      </div>
    </section>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-[7.5rem] rounded-lg border border-slate-200 bg-slate-50 px-4 py-2.5 text-center">
      <p className="text-xl font-bold text-ink-900 tabular-nums">{value}</p>
      <p className="text-[11px] text-ink-500">{label}</p>
    </div>
  );
}

/** The phone/tablet stat card: uppercase label, big value, a divided sub-line. */
function MobileStat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 pb-3.5 pt-4">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-400">{label}</p>
      <p className="text-3xl font-bold leading-none text-ink-900 tabular-nums max-[400px]:text-2xl">
        {value}
      </p>
      <p className="mt-3 border-t border-slate-200 pt-2 text-xs text-ink-500">{sub}</p>
    </div>
  );
}

export default function ProfilePage() {
  const { session, signOut } = useAuth();
  const router = useRouter();
  const [items, setItems] = React.useState<ReviewItem[] | null>(null);
  const [profile, setProfile] = React.useState<UserProfile | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    getReviewItems()
      .then((response) => !cancelled && setItems(response.items))
      .catch((caught) => {
        // No case yet is fine — the counters just read zero.
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

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-ink-900">User profile</h1>
        <p className="mt-1 text-sm text-ink-600">
          Every approval and rejection you record lands in the immutable audit
          trail under this identity.
        </p>
      </div>

      <Card>
        <CardContent className="p-6">
          {/* Phones and tablets: the compact card top. Desktop keeps its own below. */}
          <div className="mb-6 lg:hidden">
            <h2 className="text-xl font-bold tracking-tight text-ink-900">
              Profile Information
            </h2>

            <div className="mt-5 flex items-center gap-3.5 max-[400px]:gap-2.5">
              {profile?.avatar ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={profile.avatar}
                  alt="Your profile picture"
                  className="h-[52px] w-[52px] shrink-0 rounded-full object-cover"
                />
              ) : (
                <span className="flex h-[52px] w-[52px] shrink-0 items-center justify-center rounded-full bg-brand-800 text-xl font-bold text-white">
                  {initial}
                </span>
              )}
              <div className="min-w-0 flex-1">
                <p className="text-lg font-semibold tracking-tight text-ink-900">{displayName}</p>
                <p className="mt-0.5 break-all text-sm text-ink-500">{session.email}</p>
              </div>
              <Link href="/settings/profile" className="shrink-0">
                <Button size="md">
                  <Pencil className="h-4 w-4" aria-hidden />
                  Edit
                </Button>
              </Link>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-4">
              <MobileStat
                label="Decisions made"
                value={items === null ? "…" : String(decided.length)}
                sub="in this case"
              />
              <MobileStat
                label="Awaiting you"
                value={items === null ? "…" : String(pending.length)}
                sub="pending review"
              />
            </div>

          </div>

          {/* Desktop: card header and working record, unchanged. */}
          <div className="hidden lg:block">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-ink-900">Profile Information</h2>
              <div className="flex items-center gap-2">
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
                <Link href="/settings/profile">
                  <Button size="sm">
                    <Pencil className="h-3.5 w-3.5" aria-hidden />
                    Edit
                  </Button>
                </Link>
              </div>
            </div>

            {/* Who, and their working record */}
            <div className="mt-5 flex flex-wrap items-center justify-between gap-4 pb-6">
              <div className="flex items-center gap-4">
                {profile?.avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={profile.avatar}
                    alt="Your profile picture"
                    className="h-14 w-14 shrink-0 rounded-full object-cover ring-1 ring-slate-200"
                  />
                ) : (
                  <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-brand-800 text-xl font-bold text-white">
                    {initial}
                  </span>
                )}
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-ink-900">{displayName}</p>
                  <p className="truncate text-xs text-ink-500">
                    {profile?.job_title ?? session.email}
                  </p>
                  {role && (
                    <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium capitalize text-emerald-700 ring-1 ring-emerald-200">
                      <ShieldCheck className="h-3 w-3" aria-hidden />
                      {role}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <StatTile
                  label="Decisions made"
                  value={items === null ? "…" : String(decided.length)}
                />
                <StatTile
                  label="Awaiting you"
                  value={items === null ? "…" : String(pending.length)}
                />
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <Section title="Personal Details">
              <Field label="Full name" value={profile?.full_name ?? displayName} />
              <Field label="Email address" value={session.email} />
              <Field label="Phone" value={profile?.phone} />
              <Field
                label="Gender"
                value={
                  profile?.gender ? (
                    <span className="capitalize">{profile.gender}</span>
                  ) : null
                }
              />
              <Field
                label="Date of birth"
                value={profile?.date_of_birth ? formatDate(profile.date_of_birth) : null}
              />
              <Field label="Location" value={profile?.location} />
              <Field label="Job title" value={profile?.job_title} />
              <Field
                label="License / membership no."
                value={profile?.license_number}
                mono
              />
              <Field
                label="Language"
                value={
                  profile?.language === "ur"
                    ? "اردو (Urdu)"
                    : profile?.language === "en"
                      ? "English"
                      : null
                }
              />
            </Section>

            <Section title="Account & Organization">
              <Field label="Organization" value={organizationName} />
              <Field
                label="Organization id"
                value={session.orgId ?? (FIXTURE_MODE ? "ORG-FIXTURE-0001" : null)}
                mono
              />
              <Field
                label="Role"
                value={role ? <span className="capitalize">{role}</span> : null}
              />
              <Field label="User id" value={session.userId} mono />
              <Field
                label="Session expires"
                value={formatTimestamp(new Date(session.expiresAt).toISOString())}
              />
              <Field
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

            <Section title="Security">
              <Field
                label="Password"
                value={
                  <Link
                    href="/settings/account"
                    className="inline-flex items-center gap-1 font-medium text-brand-700 hover:underline"
                  >
                    Change password <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                  </Link>
                }
              />
              <Field
                label="API keys"
                value={
                  <Link
                    href="/settings/api-keys"
                    className="inline-flex items-center gap-1 font-medium text-brand-700 hover:underline"
                  >
                    <KeyRound className="h-3.5 w-3.5" aria-hidden /> Manage keys
                  </Link>
                }
              />
            </Section>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
