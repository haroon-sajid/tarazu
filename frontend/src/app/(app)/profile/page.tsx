"use client";

/**
 * The signed-in auditor's profile: the identity every decision is recorded
 * against, and the organization scope every request resolves to.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { Building2, CircleUserRound, LogOut, ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { FIXTURE_MODE } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatTimestamp } from "@/lib/format";

function FactRow({ label, value, mono = false }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <dt className="text-sm text-ink-400">{label}</dt>
      <dd className={mono ? "font-mono text-xs text-ink-900" : "text-sm font-medium text-ink-900"}>
        {value ?? "—"}
      </dd>
    </div>
  );
}

export default function ProfilePage() {
  const { session, signOut } = useAuth();
  const router = useRouter();

  if (!session) return null; // the (app) layout guard is redirecting

  const organizationName =
    session.organizationName ?? (FIXTURE_MODE ? "Demo Audit Firm" : null);
  const role = session.role ?? (FIXTURE_MODE ? "owner" : null);

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-xl font-bold text-ink-900">Profile</h1>
        <p className="mt-1 text-sm text-ink-600">
          Every approval and rejection you record lands in the immutable audit
          trail under this identity.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CircleUserRound className="h-4 w-4 text-brand-700" aria-hidden />
            Account
          </CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="divide-y divide-slate-100">
            <FactRow label="Email" value={session.email} />
            <FactRow label="User id" value={session.userId} mono />
            <FactRow
              label="Session expires"
              value={formatTimestamp(new Date(session.expiresAt).toISOString())}
            />
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="h-4 w-4 text-brand-700" aria-hidden />
            Organization
          </CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="divide-y divide-slate-100">
            <FactRow label="Name" value={organizationName} />
            <FactRow label="Organization id" value={session.orgId ?? (FIXTURE_MODE ? "ORG-FIXTURE-0001" : null)} mono />
            <FactRow
              label="Your role"
              value={
                role ? (
                  <span className="inline-flex items-center gap-1 capitalize">
                    <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" aria-hidden />
                    {role}
                  </span>
                ) : null
              }
            />
          </dl>
          <p className="mt-3 text-xs leading-relaxed text-ink-400">
            Your organization is resolved from your membership on every request
            — never from anything the browser sends. Another firm&apos;s cases
            do not exist from where you stand.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sign out</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-3 text-sm text-ink-600">
            Signing out clears the session from this browser. Decisions already
            recorded stay in the audit trail — nothing ever removes them.
          </p>
          <Button
            variant="danger"
            onClick={() => {
              signOut();
              router.replace("/login");
            }}
          >
            <LogOut className="h-4 w-4" aria-hidden />
            Sign out
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
