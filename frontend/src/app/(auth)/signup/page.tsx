"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function SignupPage() {
  const { session, signUp } = useAuth();
  const router = useRouter();
  const [organizationName, setOrganizationName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (session) router.replace("/dashboard");
  }, [session, router]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("The passwords do not match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await signUp(email, password, organizationName);
      router.replace("/dashboard");
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 409
          ? "That email is already registered. Sign in instead."
          : caught instanceof ApiError
            ? caught.message
            : "Signup failed. Try again.",
      );
      setBusy(false);
    }
  };

  return (
    <div>
      <h1 className="text-xl font-bold text-ink-900">Create your organization</h1>
      <p className="mt-1 text-sm text-ink-600">
        One signup creates your firm and makes you its owner. Your cases,
        documents, and audit trail belong to your organization alone.
      </p>

      <form onSubmit={submit} className="mt-6 space-y-4">
        <Input
          label="Organization name"
          required
          maxLength={200}
          value={organizationName}
          onChange={(event) => setOrganizationName(event.target.value)}
          placeholder="Lahore Audit Associates"
        />
        <Input
          label="Work email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="partner@lahore-audit.pk"
        />
        <Input
          label="Password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          hint="At least 8 characters."
        />
        <Input
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
        />

        {error && (
          <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
            {error}
          </p>
        )}

        <Button type="submit" size="lg" className="w-full" disabled={busy}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
          Create organization
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-ink-600">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-brand-700 hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
