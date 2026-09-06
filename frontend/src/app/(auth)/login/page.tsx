"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, Clock, Loader2, Lock, Mail } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError, FIXTURE_MODE } from "@/lib/api";
import { consumeSessionEndReason } from "@/lib/auth-storage";
import { Button } from "@/components/ui/button";
import { AuthField, AuthPasswordField } from "../auth-field";

export default function LoginPage() {
  return (
    <React.Suspense>
      <LoginScreen />
    </React.Suspense>
  );
}

/**
 * Where to go after signing in: the page the person was on when their session
 * ended, if the URL says so, else the dashboard. Only a path on this site is
 * honoured — never a full URL, so a crafted link cannot send anyone elsewhere.
 */
function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/login")) {
    return "/dashboard";
  }
  return raw;
}

function LoginScreen() {
  const { session, signIn } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = safeNext(searchParams.get("next"));
  const [email, setEmail] = React.useState(FIXTURE_MODE ? "demo@tarazu.pk" : "");
  const [password, setPassword] = React.useState(FIXTURE_MODE ? "demo-pass-123" : "");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [sessionEnded, setSessionEnded] = React.useState(false);

  // Arrived here because the session ran out, not by choice: say so once.
  React.useEffect(() => {
    if (consumeSessionEndReason() === "expired") setSessionEnded(true);
  }, []);

  // Already signed in? Straight to work.
  React.useEffect(() => {
    if (session) router.replace(next);
  }, [session, router, next]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
      router.replace(next);
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 401
          ? "Invalid email or password."
          : caught instanceof ApiError
            ? caught.message
            : "Sign in failed. Try again.",
      );
      setBusy(false);
    }
  };

  return (
    <div>
      <h1 className="text-xl font-bold text-ink-900">Sign in</h1>
      <p className="mt-1 text-sm text-ink-600">
        Decisions are recorded against your identity. Sign in to review.
      </p>

      {sessionEnded && (
        <p className="mt-4 flex items-start gap-2 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 ring-1 ring-amber-200">
          <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          <span>
            Your session ended, so Tarazu signed you out. Nothing you had
            already saved is lost. Sign in again to pick up where you left off.
          </span>
        </p>
      )}

      {FIXTURE_MODE && (
        <p className="mt-4 rounded-md bg-sky-50 px-3 py-2 text-xs text-sky-800 ring-1 ring-sky-200">
          Fixture mode: the demo credentials below sign in the seeded auditor.
          No backend needed.
        </p>
      )}

      <form onSubmit={submit} className="mt-6 space-y-5">
        <AuthField
          label="Email"
          icon={Mail}
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="partner@lahore-audit.pk"
        />
        <AuthPasswordField
          label="Password"
          icon={Lock}
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Enter your password..."
        />

        {error && (
          <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
            {error}
          </p>
        )}

        <Button
          type="submit"
          size="lg"
          className="h-12 w-full rounded-xl"
          disabled={busy}
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : null}
          Sign in
          {!busy && <ArrowRight className="h-4 w-4" aria-hidden />}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-ink-600">
        New firm?{" "}
        <Link href="/signup" className="font-medium text-brand-700 hover:underline">
          Create an organization
        </Link>
      </p>
    </div>
  );
}
