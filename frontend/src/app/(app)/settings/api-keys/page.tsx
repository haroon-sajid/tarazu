"use client";

/**
 * Developers → API keys. Fully live against /v1/api-keys. The rules come from
 * the contract: the raw key appears exactly once, read is the default scope,
 * and each row offers exactly two actions — rename (the one editable thing
 * about a key) and permanent delete, which stops an active key immediately.
 *
 * One dense table carries everything known about a key — status, id, secret
 * prefix, scopes, dates, creator — with a search box and status chips above
 * it. Filtering is display-only and client-side; the list itself always
 * arrives complete from the backend, revoked keys included.
 */

import * as React from "react";
import { Check, Copy, Loader2, Plus, Search, ShieldAlert, SquarePen, Trash2 } from "lucide-react";
import { ApiError, createApiKey, deleteApiKey, listApiKeys, renameApiKey } from "@/lib/api";
import type { ApiKeyScope, ApiKeySummary, CreatedApiKeyResponse } from "@/lib/types";
import { formatTimestamp } from "@/lib/format";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { cn } from "@/lib/utils";
import { ScopePill, SectionHeader, StatePill } from "../_components/shared";

type StatusFilter = "all" | "active" | "revoked";

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "revoked", label: "Revoked" },
];

export default function ApiKeysSettingsPage() {
  const { session } = useAuth();
  const [keys, setKeys] = React.useState<ApiKeySummary[] | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  const [query, setQuery] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState<StatusFilter>("all");

  const [creating, setCreating] = React.useState(false);
  const [newName, setNewName] = React.useState("");
  const [newScopes, setNewScopes] = React.useState<ApiKeyScope[]>(["read"]);
  const [createBusy, setCreateBusy] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);
  const [created, setCreated] = React.useState<CreatedApiKeyResponse | null>(null);
  const [copied, setCopied] = React.useState(false);

  const [editing, setEditing] = React.useState<ApiKeySummary | null>(null);
  const [editName, setEditName] = React.useState("");
  const [editBusy, setEditBusy] = React.useState(false);
  const [editError, setEditError] = React.useState<string | null>(null);

  const [deleting, setDeleting] = React.useState<ApiKeySummary | null>(null);
  const [deleteBusy, setDeleteBusy] = React.useState(false);
  const [deleteError, setDeleteError] = React.useState<string | null>(null);

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

  const filtered = React.useMemo(() => {
    if (keys === null) return null;
    const needle = query.trim().toLowerCase();
    return keys.filter((key) => {
      if (statusFilter === "active" && key.revoked) return false;
      if (statusFilter === "revoked" && !key.revoked) return false;
      if (!needle) return true;
      return (
        key.name.toLowerCase().includes(needle) ||
        key.key_id.toLowerCase().includes(needle) ||
        key.key_prefix.toLowerCase().includes(needle)
      );
    });
  }, [keys, query, statusFilter]);

  const createdBy = (userId: string) =>
    session?.userId === userId ? (
      "You"
    ) : (
      <span className="font-mono text-xs" title={userId}>
        {userId.slice(0, 8)}…
      </span>
    );

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

  const submitEdit = async () => {
    if (!editing || editBusy || !editName.trim()) return;
    setEditBusy(true);
    setEditError(null);
    try {
      const updated = await renameApiKey(editing.key_id, editName);
      setKeys((current) =>
        current
          ? current.map((key) => (key.key_id === updated.key_id ? updated : key))
          : current,
      );
      setEditing(null);
    } catch (caught) {
      setEditError(
        caught instanceof ApiError ? caught.message : "Could not rename the key.",
      );
    } finally {
      setEditBusy(false);
    }
  };

  const submitDelete = async () => {
    if (!deleting || deleteBusy) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      const gone = await deleteApiKey(deleting.key_id);
      setKeys((current) =>
        current ? current.filter((key) => key.key_id !== gone.key_id) : current,
      );
      setDeleting(null);
    } catch (caught) {
      setDeleteError(
        caught instanceof ApiError ? caught.message : "Could not delete the key.",
      );
    } finally {
      setDeleteBusy(false);
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
    <div>
      <SectionHeader
        title="API keys"
        description="API keys authenticate requests from external tools and automation workflows. Each key is scoped to this organization and can be renamed or deleted at any time."
        action={
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="h-3.5 w-3.5" aria-hidden />
            Create key
          </Button>
        }
      />

      {loadError ? (
        <ErrorState message={loadError} onRetry={load} />
      ) : filtered === null ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-12 w-full" />
          ))}
        </div>
      ) : keys !== null && keys.length === 0 ? (
        <EmptyState
          title="No API keys yet"
          message="Create a key to authenticate external tools and automation workflows. Read-only is the default scope."
        />
      ) : (
        <div>
          {/* Toolbar: search, status chips, result count */}
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-400"
                aria-hidden
              />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search keys…"
                aria-label="Search API keys"
                className={cn(
                  "h-8 w-56 rounded-full border border-slate-300 bg-white pl-8 pr-3 text-sm text-ink-900",
                  "placeholder:text-ink-400",
                  "focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600",
                )}
              />
            </div>
            <div className="flex gap-1" role="group" aria-label="Filter by status">
              {STATUS_FILTERS.map(({ value, label }) => (
                <button
                  key={value}
                  onClick={() => setStatusFilter(value)}
                  className={cn(
                    "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                    statusFilter === value
                      ? "bg-brand-800 text-white"
                      : "bg-slate-100 text-ink-600 hover:bg-slate-200 hover:text-ink-900",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <span className="text-xs text-ink-400">
              {filtered.length} {filtered.length === 1 ? "result" : "results"}
            </span>
          </div>

          {filtered.length === 0 ? (
            <EmptyState
              title="No keys match"
              message="No API key matches the current search and filter."
            />
          ) : (
            <div>
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-slate-200 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                    <th className="py-2 pr-4">Name</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="hidden py-2 pr-4 lg:table-cell">Key id</th>
                    <th className="hidden py-2 pr-4 md:table-cell">Secret key</th>
                    <th className="py-2 pr-4">Permissions</th>
                    <th className="hidden py-2 pr-4 sm:table-cell">Created</th>
                    <th className="hidden py-2 pr-4 lg:table-cell">Last used</th>
                    <th className="hidden py-2 pr-4 xl:table-cell">Created by</th>
                    <th className="py-2 text-right" aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((key) => (
                    <tr
                      key={key.key_id}
                      className={cn(
                        "border-b border-slate-100 text-sm last:border-0",
                        key.revoked && "opacity-60",
                      )}
                    >
                      <td className="py-2.5 pr-4 font-medium text-ink-900">{key.name}</td>
                      <td className="py-2.5 pr-4">
                        {key.revoked ? (
                          <StatePill
                            tone="negative"
                            title={
                              key.revoked_at
                                ? `Revoked ${formatTimestamp(key.revoked_at)}`
                                : undefined
                            }
                          >
                            Revoked
                          </StatePill>
                        ) : (
                          <StatePill tone="positive">Active</StatePill>
                        )}
                      </td>
                      <td className="hidden break-all py-2.5 pr-4 font-mono text-xs text-ink-600 lg:table-cell">
                        {key.key_id}
                      </td>
                      <td className="hidden break-all py-2.5 pr-4 font-mono text-xs text-ink-600 md:table-cell">
                        {key.key_prefix}…
                      </td>
                      <td className="py-2.5 pr-4">
                        <span className="flex flex-wrap gap-1">
                          {key.scopes.map((scope) => (
                            <ScopePill key={scope} scope={scope} />
                          ))}
                        </span>
                      </td>
                      <td className="hidden py-2.5 pr-4 text-xs text-ink-600 sm:table-cell">
                        {formatTimestamp(key.created_at)}
                      </td>
                      <td className="hidden py-2.5 pr-4 text-xs text-ink-600 lg:table-cell">
                        {key.last_used_at ? formatTimestamp(key.last_used_at) : "Never"}
                      </td>
                      <td className="hidden break-words py-2.5 pr-4 text-xs text-ink-600 xl:table-cell">
                        {createdBy(key.created_by)}
                      </td>
                      <td className="py-2.5 text-right">
                        <span className="inline-flex items-center gap-1">
                          <button
                            onClick={() => {
                              setEditError(null);
                              setEditName(key.name);
                              setEditing(key);
                            }}
                            title={`Rename “${key.name}”`}
                            aria-label={`Rename ${key.name}`}
                            className="rounded-md p-1.5 text-ink-600 transition-colors hover:bg-slate-100 hover:text-ink-900"
                          >
                            <SquarePen className="h-4 w-4" aria-hidden />
                          </button>
                          <button
                            onClick={() => {
                              setDeleteError(null);
                              setDeleting(key);
                            }}
                            title={`Delete “${key.name}” permanently`}
                            aria-label={`Delete ${key.name}`}
                            className="rounded-md p-1.5 text-red-500 transition-colors hover:bg-rose-50 hover:text-red-600"
                          >
                            <Trash2 className="h-4 w-4" aria-hidden />
                          </button>
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Create key */}
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
            placeholder="Automation workflow"
            hint="A label that identifies where this key will be used."
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
                    Read access to review items, the dashboard, and audit history.
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
                    Upload documents and record decisions. Keys can never manage
                    other keys.
                  </span>
                </span>
              </label>
            </div>
            {newScopes.includes("write") && (
              <p className="mt-2 flex items-start gap-1.5 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 ring-1 ring-amber-200">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                A key with write scope can record decisions. Each of those
                actions is attributed to this key in the audit trail. Grant
                write scope only when automation is intended.
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

      {/* Created key, shown exactly once */}
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
              Send this key in the <span className="font-mono">X-API-Key</span>{" "}
              request header. Tarazu stores only a hash, so a lost key must be
              replaced with a new one.
            </p>
            <div className="flex justify-end">
              <Button size="sm" onClick={() => setCreated(null)}>
                I saved it
              </Button>
            </div>
          </div>
        )}
      </Dialog>

      {/* Rename */}
      <Dialog
        open={editing !== null}
        onClose={() => !editBusy && setEditing(null)}
        title={`Edit “${editing?.name ?? ""}”`}
      >
        <div className="space-y-4">
          <Input
            label="Name"
            autoFocus
            maxLength={100}
            value={editName}
            onChange={(event) => setEditName(event.target.value)}
            placeholder="Automation workflow"
            hint="The label shown here and in the audit trail alongside the key prefix."
          />
          <div>
            <p className="mb-1.5 text-xs font-medium text-ink-600">Permissions</p>
            <span className="flex gap-1">
              {editing?.scopes.map((scope) => <ScopePill key={scope} scope={scope} />)}
            </span>
            <p className="mt-1.5 text-xs text-ink-400">
              Permissions are fixed for a key's lifetime. To change them, create
              a new key and delete this one.
            </p>
          </div>
          {editError && (
            <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
              {editError}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEditing(null)}
              disabled={editBusy}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={submitEdit}
              disabled={editBusy || !editName.trim()}
            >
              {editBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
              Save
            </Button>
          </div>
        </div>
      </Dialog>

      {/* Delete confirmation — permanent, effective immediately */}
      <Dialog
        open={deleting !== null}
        onClose={() => !deleteBusy && setDeleting(null)}
        title={`Delete “${deleting?.name ?? ""}” permanently?`}
      >
        <p className="text-sm text-ink-600">
          {deleting?.revoked
            ? "This removes the key's record from Tarazu for good."
            : "The key stops working immediately and its record is removed for good."}{" "}
          Audit trail entries stay in the trail, but the ones naming{" "}
          <span className="font-mono text-xs">{deleting?.key_prefix}…</span>{" "}
          will no longer resolve to this key's name or creator.
        </p>
        {deleteError && (
          <p className="mt-3 rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
            {deleteError}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setDeleting(null)}
            disabled={deleteBusy}
          >
            Cancel
          </Button>
          <Button variant="danger" size="sm" onClick={submitDelete} disabled={deleteBusy}>
            {deleteBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
            Delete permanently
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
