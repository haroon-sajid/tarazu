"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError, FIXTURE_MODE } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input, PasswordInput } from "@/components/ui/input";

export default function LoginPage() {
  const { session, signIn } = useAuth();
  const router = useRouter();
  const [email, setEmail] = React.useState(FIXTURE_MODE ? "demo@tarazu.pk" : "");
  const [password, setPassword] = React.useState(FIXTURE_MODE ? "demo-pass-123" : "");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Already signed in? Straight to work.
  React.useEffect(() => {
    if (session) router.replace("/dashboard");
  }, [session, router]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
      router.replace("/dashboard");
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
        Decisions are recorded against your identity — sign in to review.
      </p>

      {FIXTURE_MODE && (
        <p className="mt-4 rounded-md bg-sky-50 px-3 py-2 text-xs text-sky-800 ring-1 ring-sky-200">
          Fixture mode: the demo credentials below sign in the seeded auditor.
          No backend needed.
        </p>
      )}

      <form onSubmit={submit} className="mt-6 space-y-4">
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="partner@lahore-audit.pk"
        />
        <PasswordInput
          label="Password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="••••••••"
        />

        {error && (
          <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
            {error}
          </p>
        )}

        <Button type="submit" size="lg" className="w-full" disabled={busy}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
          Sign in
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
