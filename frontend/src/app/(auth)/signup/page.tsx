"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input, PasswordInput } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type Mode = "create" | "join";

export default function SignupPage() {
  const { session, signUp } = useAuth();
  const router = useRouter();
  const [mode, setMode] = React.useState<Mode>("create");
  const [organizationName, setOrganizationName] = React.useState("");
  const [inviteCode, setInviteCode] = React.useState("");
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
      await signUp(
        email,
        password,
        organizationName,
        mode === "join" ? inviteCode : undefined,
      );
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
      <h1 className="text-xl font-bold text-ink-900">
        {mode === "create" ? "Create your organization" : "Join your firm"}
      </h1>
      <p className="mt-1 text-sm text-ink-600">
        {mode === "create"
          ? "One signup creates your firm and makes you its owner. Your cases, documents, and audit trail belong to your organization alone."
          : "Got an invite code from your firm's owner? It joins you to their workspace: same cases, same audit trail, your own identity."}
      </p>

      {/* Found a firm, or join one by invitation */}
      <div className="mt-4 flex gap-1 rounded-lg bg-slate-100 p-1">
        {(
          [
            { key: "create", label: "Create a firm" },
            { key: "join", label: "I have an invite code" },
          ] as { key: Mode; label: string }[]
        ).map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setMode(key)}
            className={cn(
              "flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              mode === key
                ? "bg-white text-ink-900 shadow-sm"
                : "text-ink-600 hover:text-ink-900",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <form onSubmit={submit} className="mt-5 space-y-4">
        {mode === "create" ? (
          <Input
            label="Organization name"
            required
            maxLength={200}
            value={organizationName}
            onChange={(event) => setOrganizationName(event.target.value)}
            placeholder="Lahore Audit Associates"
          />
        ) : (
          <Input
            label="Invite code"
            required
            maxLength={40}
            value={inviteCode}
            onChange={(event) => setInviteCode(event.target.value.toUpperCase())}
            placeholder="TZ-1A2B3C4D"
            hint="Single-use, from your workspace owner (Settings → Members)."
          />
        )}
        <Input
          label="Work email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="partner@lahore-audit.pk"
        />
        <PasswordInput
          label="Password"
          autoComplete="new-password"
          required
          minLength={8}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          hint="At least 8 characters."
        />
        <PasswordInput
          label="Confirm password"
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
          {mode === "create" ? "Create organization" : "Join workspace"}
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
