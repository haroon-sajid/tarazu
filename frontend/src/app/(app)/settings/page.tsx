"use client";

/**
 * Settings: API keys and workspace facts.
 *
 * The key rules come from the contract, and the UI keeps them visible:
 * the raw key appears exactly once (in the create response), a key is revoked
 * never deleted, and `read` is the default scope — a key that can approve
 * has to say so.
 */

import * as React from "react";
import {
  Check,
  Copy,
  KeyRound,
  Loader2,
  Plus,
  ShieldAlert,
  Ban,
} from "lucide-react";
import {
  ApiError,
  createApiKey,
  FIXTURE_MODE,
  listApiKeys,
  revokeApiKey,
} from "@/lib/api";
import type { ApiKeyScope, ApiKeySummary, CreatedApiKeyResponse } from "@/lib/types";
import { formatTimestamp } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { cn } from "@/lib/utils";

function ScopePill({ scope }: { scope: ApiKeyScope }) {
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

export default function SettingsPage() {
  const [keys, setKeys] = React.useState<ApiKeySummary[] | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  // Create-key dialog state
  const [creating, setCreating] = React.useState(false);
  const [newName, setNewName] = React.useState("");
  const [newScopes, setNewScopes] = React.useState<ApiKeyScope[]>(["read"]);
  const [createBusy, setCreateBusy] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);
  const [created, setCreated] = React.useState<CreatedApiKeyResponse | null>(null);
  const [copied, setCopied] = React.useState(false);

  // Revoke state
  const [revoking, setRevoking] = React.useState<ApiKeySummary | null>(null);
  const [revokeBusy, setRevokeBusy] = React.useState(false);
  const [revokeError, setRevokeError] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    setLoadError(null);
    setKeys(null);
    listApiKeys()
      .then((response) => setKeys(response.keys))
      .catch((caught) =>
        setLoadError(
          caught instanceof ApiError && caught.status === 403
            ? "API keys are managed by a signed-in person, not by a key."
            : caught instanceof ApiError
              ? caught.message
              : "Could not load the API keys.",
        ),
      );
  }, []);

  React.useEffect(load, [load]);

  const toggleScope = (scope: ApiKeyScope) =>
    setNewScopes((current) =>
      current.includes(scope)
        ? current.filter((candidate) => candidate !== scope)
        : [...current, scope],
    );

  const submitCreate = async () => {
    if (createBusy || !newName.trim() || newScopes.length === 0) return;
    setCreateBusy(true);
    setCreateError(null);
    try {
      const response = await createApiKey(newName, newScopes);
      setCreated(response);
      setKeys((current) => (current ? [response.key, ...current] : [response.key]));
      setCreating(false);
      setNewName("");
      setNewScopes(["read"]);
    } catch (caught) {
      setCreateError(
        caught instanceof ApiError ? caught.message : "Could not create the key.",
      );
    } finally {
      setCreateBusy(false);
    }
  };

  const submitRevoke = async () => {
    if (!revoking || revokeBusy) return;
    setRevokeBusy(true);
    setRevokeError(null);
    try {
      const updated = await revokeApiKey(revoking.key_id);
      setKeys((current) =>
        current
          ? current.map((key) => (key.key_id === updated.key_id ? updated : key))
          : current,
      );
      setRevoking(null);
    } catch (caught) {
      setRevokeError(
        caught instanceof ApiError ? caught.message : "Could not revoke the key.",
      );
    } finally {
      setRevokeBusy(false);
    }
  };

  const copyKey = async () => {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.api_key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard can be blocked; the key is still visible to select manually.
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-xl font-bold text-ink-900">Settings</h1>
        <p className="mt-1 text-sm text-ink-600">
          API keys let your own tooling — n8n, Zapier, a script — reach Tarazu
          without a person signing in. A key reaches exactly what its creator
          could reach, and nothing in another organization.
        </p>
      </div>

      {/* API keys */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-brand-700" aria-hidden />
            API keys
          </CardTitle>
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="h-3.5 w-3.5" aria-hidden />
            Create key
          </Button>
        </CardHeader>
        <CardContent>
          {loadError ? (
            <ErrorState message={loadError} onRetry={load} />
          ) : keys === null ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-12 w-full" />
              ))}
            </div>
          ) : keys.length === 0 ? (
            <EmptyState
              title="No API keys yet"
              message="Create a key to connect n8n, Zapier, or your own scripts. Read-only is the default scope."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left">
                <thead>
                  <tr className="border-b border-slate-200 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                    <th className="py-2 pr-4">Name</th>
                    <th className="py-2 pr-4">Key</th>
                    <th className="py-2 pr-4">Scopes</th>
                    <th className="py-2 pr-4">Created</th>
                    <th className="py-2 pr-4">Last used</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {keys.map((key) => (
                    <tr
                      key={key.key_id}
                      className={cn(
                        "border-b border-slate-100 text-sm last:border-0",
                        key.revoked && "opacity-60",
                      )}
                    >
                      <td className="py-2.5 pr-4 font-medium text-ink-900">
                        {key.name}
                      </td>
                      <td className="py-2.5 pr-4 font-mono text-xs text-ink-600">
                        {key.key_prefix}…
                      </td>
                      <td className="py-2.5 pr-4">
                        <span className="flex gap-1">
                          {key.scopes.map((scope) => (
                            <ScopePill key={scope} scope={scope} />
                          ))}
                        </span>
                      </td>
                      <td className="whitespace-nowrap py-2.5 pr-4 text-xs text-ink-600">
                        {formatTimestamp(key.created_at)}
                      </td>
                      <td className="whitespace-nowrap py-2.5 pr-4 text-xs text-ink-600">
                        {key.last_used_at ? formatTimestamp(key.last_used_at) : "Never"}
                      </td>
                      <td className="py-2.5 pr-4">
                        {key.revoked ? (
                          <span
                            className="text-xs font-medium text-rose-600"
                            title={
                              key.revoked_at
                                ? `Revoked ${formatTimestamp(key.revoked_at)}`
                                : undefined
                            }
                          >
                            Revoked
                          </span>
                        ) : (
                          <span className="text-xs font-medium text-emerald-600">
                            Active
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 text-right">
                        {!key.revoked && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setRevokeError(null);
                              setRevoking(key);
                            }}
                          >
                            <Ban className="h-3.5 w-3.5" aria-hidden />
                            Revoke
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Connection */}
      <Card>
        <CardHeader>
          <CardTitle>Connection</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-ink-400">Data source</dt>
              <dd className="font-medium text-ink-900">
                {FIXTURE_MODE ? "Fixture data (offline demo)" : "Live backend"}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-ink-400">Backend URL</dt>
              <dd className="font-mono text-xs text-ink-900">
                {process.env.NEXT_PUBLIC_TARAZU_API_URL || "— not set —"}
              </dd>
            </div>
          </dl>
          {FIXTURE_MODE && (
            <p className="mt-3 text-xs text-ink-400">
              Set <span className="font-mono">NEXT_PUBLIC_TARAZU_API_URL</span> in{" "}
              <span className="font-mono">.env.local</span> and restart the dev
              server to switch every screen to the live API.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Create key dialog */}
      <Dialog
        open={creating}
        onClose={() => !createBusy && setCreating(false)}
        title="Create an API key"
      >
        <div className="space-y-4">
          <Input
            label="Name"
            autoFocus
            maxLength={100}
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            placeholder="n8n integration"
            hint="So it can be recognised months later and revoked with confidence."
          />
          <div>
            <p className="mb-1.5 text-xs font-medium text-ink-600">Scopes</p>
            <div className="space-y-2">
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 accent-teal-700"
                  checked={newScopes.includes("read")}
                  onChange={() => toggleScope("read")}
                />
                <span>
                  <span className="font-medium text-ink-900">read</span>
                  <span className="block text-xs text-ink-400">
                    The review queue, the dashboard, an item&apos;s audit trail.
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 accent-teal-700"
                  checked={newScopes.includes("write")}
                  onChange={() => toggleScope("write")}
                />
                <span>
                  <span className="font-medium text-ink-900">write</span>
                  <span className="block text-xs text-ink-400">
                    Upload, approve, reject. Never key management.
                  </span>
                </span>
              </label>
            </div>
            {newScopes.includes("write") && (
              <p className="mt-2 flex items-start gap-1.5 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 ring-1 ring-amber-200">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                A write key can record decisions. Every such action lands in the
                audit trail as api-key:&lt;prefix&gt; — grant write only when
                automation is the intent.
              </p>
            )}
          </div>

          {createError && (
            <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
              {createError}
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCreating(false)}
              disabled={createBusy}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={submitCreate}
              disabled={createBusy || !newName.trim() || newScopes.length === 0}
            >
              {createBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
              Create key
            </Button>
          </div>
        </div>
      </Dialog>

      {/* Created key — shown exactly once */}
      <Dialog
        open={created !== null}
        onClose={() => setCreated(null)}
        title="Save this key now"
        className="max-w-lg"
      >
        {created && (
          <div className="space-y-3">
            <p className="text-xs text-ink-600">{created.message}</p>
            <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
              <code className="min-w-0 flex-1 break-all font-mono text-xs text-ink-900">
                {created.api_key}
              </code>
              <Button size="sm" variant="outline" onClick={copyKey}>
                {copied ? (
                  <Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden />
                ) : (
                  <Copy className="h-3.5 w-3.5" aria-hidden />
                )}
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <p className="text-xs text-ink-400">
              Send it as <span className="font-mono">X-API-Key</span> on any{" "}
              <span className="font-mono">/v1/…</span> endpoint. Losing it means
              creating a new one — Tarazu stores only a hash.
            </p>
            <div className="flex justify-end">
              <Button size="sm" onClick={() => setCreated(null)}>
                I saved it
              </Button>
            </div>
          </div>
        )}
      </Dialog>

      {/* Revoke confirmation */}
      <Dialog
        open={revoking !== null}
        onClose={() => !revokeBusy && setRevoking(null)}
        title={`Revoke “${revoking?.name ?? ""}”?`}
      >
        <p className="text-sm text-ink-600">
          The key stops working immediately. There is no un-revoke — a key that
          was turned off may have been turned off because it leaked. The row
          stays, so the audit trail&apos;s{" "}
          <span className="font-mono text-xs">{revoking?.key_prefix}…</span>{" "}
          entries remain traceable.
        </p>
        {revokeError && (
          <p className="mt-3 rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
            {revokeError}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setRevoking(null)}
            disabled={revokeBusy}
          >
            Cancel
          </Button>
          <Button variant="danger" size="sm" onClick={submitRevoke} disabled={revokeBusy}>
            {revokeBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
            Revoke key
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
