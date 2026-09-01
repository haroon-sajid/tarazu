"use client";

/**
 * User profile — the identity every decision is recorded against. One card:
 * who this is at the top, then their details as read-only fields in two
 * columns. Editing happens on Settings → Profile; this screen only shows what
 * the backend holds.
 */

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut, Pencil } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { FIXTURE_MODE, getProfile } from "@/lib/api";
import type { UserProfile } from "@/lib/types";
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
          "flex min-h-[42px] items-center rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-ink-900",
          mono && "font-mono text-xs",
          empty && "text-ink-400",
        )}
      >
        {empty ? "—" : value}
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
      <div className="grid grid-cols-1 gap-x-4 gap-y-5 sm:grid-cols-2">{children}</div>
    </section>
  );
}

export default function ProfilePage() {
  const { session, signOut } = useAuth();
  const router = useRouter();
  const [profile, setProfile] = React.useState<UserProfile | null>(null);

  React.useEffect(() => {
    let cancelled = false;
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
  const subtitle = profile?.job_title ?? (role ? `${role} · ${organizationName ?? "Tarazu"}` : session.email);

  return (
    <div className="max-w-3xl">
      <Card>
        <CardContent className="p-6">
          {/* Card header */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h1 className="text-lg font-semibold text-ink-900">Profile Information</h1>
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

          {/* Who */}
          <div className="mt-5 flex items-center gap-4 pb-6">
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
              <p className="truncate text-xs capitalize text-ink-500">{subtitle}</p>
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
            </Section>

            <Section title="Account">
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
              <Field label="User id" value={session.userId} mono />
              <Field
                label="Session expires"
                value={formatTimestamp(new Date(session.expiresAt).toISOString())}
              />
            </Section>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
