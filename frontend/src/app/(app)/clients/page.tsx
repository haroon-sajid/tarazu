"use client";

/**
 * Clients — the firm's recurring relationships, which is what an accounting
 * practice actually has. A case is one month's work; a client is the business
 * that comes back next month with another month of it (ADR 0005). This screen
 * is the directory: who the firm audits, how many periods have been run for
 * each, and how much of that work is still outstanding.
 *
 * Every count in the table — periods run, items pending, open evidence
 * requests — is counted by the backend from decided items and open requests.
 * Nothing on this page is summed, averaged, or derived in the browser.
 *
 * Archiving is the only action here that looks destructive and is not:
 * it takes a client out of the pickers and deletes nothing. Its periods,
 * decisions, reports, and audit trail are evidence, and evidence outlives the
 * relationship. The confirming dialog says so in as many words.
 */

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Archive, ArchiveRestore, Loader2, Plus } from "lucide-react";
import {
  ApiError,
  archiveClient,
  createClient,
  listClients,
  restoreClient,
} from "@/lib/api";
import type { AssistantLanguage, ClientSummary } from "@/lib/types";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";

/** The currencies the pilot firms bill in. The backend accepts any code. */
const CURRENCIES = ["PKR", "USD", "AED", "GBP", "EUR", "SAR"];

export default function ClientsPage() {
  const router = useRouter();

  const [clients, setClients] = React.useState<ClientSummary[] | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [showArchived, setShowArchived] = React.useState(false);

  const [creating, setCreating] = React.useState(false);
  const [newName, setNewName] = React.useState("");
  const [newReference, setNewReference] = React.useState("");
  const [newCurrency, setNewCurrency] = React.useState("PKR");
  const [newLanguage, setNewLanguage] = React.useState<AssistantLanguage>("en");
  const [newNotes, setNewNotes] = React.useState("");
  const [createBusy, setCreateBusy] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);

  const [confirming, setConfirming] = React.useState<ClientSummary | null>(null);
  const [confirmBusy, setConfirmBusy] = React.useState(false);
  const [confirmError, setConfirmError] = React.useState<string | null>(null);

  const load = React.useCallback((includeArchived: boolean) => {
    setLoadError(null);
    setClients(null);
    listClients(includeArchived)
      .then((response) => setClients(response.clients))
      .catch((caught) =>
        setLoadError(
          caught instanceof ApiError ? caught.message : "Could not load the clients.",
        ),
      );
  }, []);

  React.useEffect(() => {
    load(showArchived);
  }, [load, showArchived]);

  const openCreate = () => {
    setCreateError(null);
    setNewName("");
    setNewReference("");
    setNewCurrency("PKR");
    setNewLanguage("en");
    setNewNotes("");
    setCreating(true);
  };

  const submitCreate = async () => {
    if (createBusy || !newName.trim()) return;
    setCreateBusy(true);
    setCreateError(null);
    try {
      const created = await createClient({
        name: newName.trim(),
        reference: newReference.trim() || null,
        currency: newCurrency,
        language: newLanguage,
        notes: newNotes.trim() || null,
      });
      setCreating(false);
      // The new client carries the firm's default thresholds; its own are
      // tuned on its page, which is where the reader is going next anyway.
      router.push(`/clients/${encodeURIComponent(created.client_id)}`);
    } catch (caught) {
      setCreateError(
        caught instanceof ApiError ? caught.message : "Could not add the client.",
      );
    } finally {
      setCreateBusy(false);
    }
  };

  const submitConfirm = async () => {
    if (!confirming || confirmBusy) return;
    setConfirmBusy(true);
    setConfirmError(null);
    const wasArchived = confirming.archived;
    try {
      const updated = wasArchived
        ? await restoreClient(confirming.client_id)
        : await archiveClient(confirming.client_id);
      setConfirming(null);
      setClients((current) => {
        if (!current) return current;
        // An archived client only belongs in the table while archived ones are
        // being shown; otherwise the row leaves with the relationship.
        if (updated.archived && !showArchived) {
          return current.filter((item) => item.client_id !== updated.client_id);
        }
        return current.map((item) =>
          item.client_id === updated.client_id ? updated : item,
        );
      });
    } catch (caught) {
      setConfirmError(
        caught instanceof ApiError
          ? caught.message
          : `Could not ${wasArchived ? "restore" : "archive"} the client.`,
      );
    } finally {
      setConfirmBusy(false);
    }
  };

  return (
    <div>
      <div className="mb-5 flex items-end justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink-900">Clients</h1>
          <p className="mt-1 text-sm text-ink-600">
            The businesses your firm audits, period after period. Open one to
            see its history and tune the red-flag thresholds it is audited
            against.
          </p>
        </div>
        <Button size="sm" onClick={openCreate}>
          <Plus className="h-3.5 w-3.5" aria-hidden />
          New client
        </Button>
      </div>

      <div className="mb-3 flex items-center justify-between gap-3">
        <label className="flex cursor-pointer items-center gap-2 text-xs text-ink-600">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(event) => setShowArchived(event.target.checked)}
            className="h-3.5 w-3.5 rounded border-slate-300 text-brand-700 focus:ring-brand-600"
          />
          Show archived clients
        </label>
        {clients !== null && (
          <p className="text-[11px] text-ink-400 tabular-nums">
            {clients.length} {clients.length === 1 ? "client" : "clients"}
          </p>
        )}
      </div>

      {loadError ? (
        <ErrorState message={loadError} onRetry={() => load(showArchived)} />
      ) : clients === null ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-14 w-full" />
          ))}
        </div>
      ) : clients.length === 0 ? (
        <EmptyState
          title="No clients yet"
          message={
            showArchived
              ? "Nothing here, archived or otherwise. Add the first business your firm audits and every period you run for it will collect under it."
              : "Add the first business your firm audits. Every period you run for it collects under the client, along with the thresholds it is audited against."
          }
          action={
            <Button size="sm" onClick={openCreate}>
              <Plus className="h-3.5 w-3.5" aria-hidden />
              New client
            </Button>
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
          <table className="w-full min-w-[920px] text-left">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                <th className="px-4 py-2.5">Client</th>
                <th className="px-4 py-2.5 text-right">Periods run</th>
                <th className="px-4 py-2.5 text-right">Items pending</th>
                <th className="px-4 py-2.5 text-right">Evidence open</th>
                <th className="px-4 py-2.5">Last period end</th>
                <th className="px-4 py-2.5">Currency</th>
                <th className="px-4 py-2.5" aria-label="Archived" />
                <th className="px-4 py-2.5 text-right" aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {clients.map((client) => (
                <tr
                  key={client.client_id}
                  onClick={() =>
                    router.push(`/clients/${encodeURIComponent(client.client_id)}`)
                  }
                  className={cn(
                    "cursor-pointer border-b border-slate-100 text-sm last:border-0",
                    client.archived ? "bg-slate-50/60" : "hover:bg-slate-50/60",
                  )}
                >
                  <td className="px-4 py-3">
                    <span className="block font-medium text-ink-900">
                      {client.name}
                    </span>
                    {client.reference && (
                      <span className="block font-mono text-[11px] text-ink-400">
                        {client.reference}
                      </span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                    {client.period_count}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                    {client.pending_items}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-900">
                    {client.open_evidence_requests}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-ink-600">
                    {client.last_period_end ? formatDate(client.last_period_end) : "-"}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-ink-600">
                    {client.currency}
                    <span className="ml-1.5 uppercase text-ink-400">
                      {client.language}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    {client.archived && (
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-600 ring-1 ring-slate-200">
                        Archived
                      </span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <button
                      onClick={(event) => {
                        event.stopPropagation();
                        setConfirmError(null);
                        setConfirming(client);
                      }}
                      title={
                        client.archived
                          ? `Restore “${client.name}” to the pickers`
                          : `Archive “${client.name}” — nothing is deleted`
                      }
                      aria-label={
                        client.archived
                          ? `Restore ${client.name}`
                          : `Archive ${client.name}`
                      }
                      className="rounded-md p-1.5 text-ink-600 transition-colors hover:bg-slate-100 hover:text-ink-900"
                    >
                      {client.archived ? (
                        <ArchiveRestore className="h-4 w-4" aria-hidden />
                      ) : (
                        <Archive className="h-4 w-4" aria-hidden />
                      )}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-3 text-[11px] text-ink-400">
        A period is uploaded against a client so it inherits that client&apos;s
        thresholds. A case with no client stays a valid one-off engagement and
        lives on the{" "}
        <Link href="/cases" className="text-brand-700 hover:underline">
          Cases
        </Link>{" "}
        screen.
      </p>

      {/* Add a recurring client */}
      <Dialog
        open={creating}
        onClose={() => !createBusy && setCreating(false)}
        title="New client"
      >
        <div className="space-y-4">
          <Input
            label="Client name"
            autoFocus
            maxLength={200}
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            placeholder="Haroon Textiles"
            hint="The business you audit. It appears on every period and report."
          />
          <Input
            label="Reference (optional)"
            maxLength={100}
            value={newReference}
            onChange={(event) => setNewReference(event.target.value)}
            placeholder="HT-2026"
            hint="Your own client code, if your practice uses one."
          />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Select
              label="Currency"
              value={newCurrency}
              onChange={(event) => setNewCurrency(event.target.value)}
              hint="What this client's books are denominated in."
            >
              {CURRENCIES.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </Select>
            <Select
              label="Language"
              value={newLanguage}
              onChange={(event) =>
                setNewLanguage(event.target.value as AssistantLanguage)
              }
              hint="The language explanations are written in for this client."
            >
              <option value="en">English</option>
              <option value="ur">اردو — Urdu</option>
            </Select>
          </div>
          <div>
            <label
              htmlFor="new-client-notes"
              className="mb-1 block text-xs font-medium text-ink-600"
            >
              Notes (optional)
            </label>
            <textarea
              id="new-client-notes"
              rows={3}
              maxLength={2000}
              value={newNotes}
              onChange={(event) => setNewNotes(event.target.value)}
              placeholder="Textile exporter, Faisalabad. Quarterly review, two bank accounts."
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-ink-900 placeholder:text-ink-400 focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
            />
            <p className="mt-1 text-[11px] text-ink-400">
              Context for whoever picks the engagement up next. Not shown to the
              client.
            </p>
          </div>
          <p className="text-[11px] text-ink-400">
            The client starts on your firm&apos;s default red-flag thresholds.
            Tune them on the client&apos;s own page; they take effect from the
            next period you process.
          </p>
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
              disabled={createBusy || !newName.trim()}
            >
              {createBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
              Add client
            </Button>
          </div>
        </div>
      </Dialog>

      {/* Archive / restore — reversible, and it deletes nothing */}
      <Dialog
        open={confirming !== null}
        onClose={() => !confirmBusy && setConfirming(null)}
        title={
          confirming?.archived
            ? `Restore “${confirming?.name ?? ""}”?`
            : `Archive “${confirming?.name ?? ""}”?`
        }
      >
        <p className="text-sm text-ink-600">
          {confirming?.archived
            ? "The client comes back into the pickers and can have new periods uploaded against it again. Its history never went anywhere."
            : "Archiving deletes nothing. Every period run for this client, every decision an auditor recorded, every report generated, and the whole audit trail stay exactly where they are. The client simply leaves the pickers and the default view, and you can restore it at any time."}
        </p>
        {confirmError && (
          <p className="mt-3 rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
            {confirmError}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setConfirming(null)}
            disabled={confirmBusy}
          >
            Cancel
          </Button>
          <Button size="sm" onClick={submitConfirm} disabled={confirmBusy}>
            {confirmBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
            {confirming?.archived ? "Restore client" : "Archive client"}
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
