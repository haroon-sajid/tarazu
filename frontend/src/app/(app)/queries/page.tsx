"use client";

/**
 * Evidence requests — the chase list.
 *
 * An audit stalls on missing paper: the invoice behind an unmatched payment,
 * the explanation for a weekend entry, the contract a round number is supposed
 * to sit under. Firms track that in somebody's inbox, where it is invisible six
 * months later. Here the ask lives on the case: who asked, for what, when it was
 * due, what came back, and who was satisfied by it.
 *
 * A request is a *question*, never a verdict. Recording an answer approves
 * nothing, rejects nothing, and re-matches nothing — the item is still decided
 * by a person on the review screen (reliability rule 1). The copy on this page
 * says so out loud, because a screen that let "answered" read as "settled" would
 * quietly undo that rule in the auditor's head.
 *
 * Every number shown is the backend's. `open_total` — the outstanding figure at
 * the top — counts open *and* answered requests, because an answer nobody has
 * read yet is still work; this page displays it rather than recomputing it.
 *
 * A resolved or cancelled request is terminal: the backend answers 409 to any
 * further transition, so the row simply offers no action rather than offering
 * one that is guaranteed to fail.
 */

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  Ban,
  CheckCircle2,
  Loader2,
  MessageSquarePlus,
  Plus,
  Reply,
} from "lucide-react";
import {
  ApiError,
  actOnEvidenceRequest,
  createEvidenceRequest,
  FIXTURE_MODE,
  listEvidenceRequests,
} from "@/lib/api";
import type {
  EvidenceRequest,
  EvidenceRequestListResponse,
  EvidenceRequestStatus,
} from "@/lib/types";
import { formatDate, formatTimestamp } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";

type StatusFilter = EvidenceRequestStatus | "all";

const STATUS_STYLE: Record<
  EvidenceRequestStatus,
  { label: string; className: string; note: string }
> = {
  open: {
    label: "Open",
    className: "bg-amber-50 text-amber-800 ring-amber-300",
    note: "Asked, nothing back yet",
  },
  answered: {
    label: "Answered",
    className: "bg-sky-50 text-sky-700 ring-sky-200",
    note: "Something came back; an auditor still has to read it",
  },
  resolved: {
    label: "Resolved",
    className: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    note: "An auditor read it and was satisfied",
  },
  cancelled: {
    label: "Cancelled",
    className: "bg-slate-100 text-ink-600 ring-slate-200",
    note: "Withdrawn without a response",
  },
};

/** Resolved and cancelled are terminal; the backend refuses to reopen either. */
const isClosed = (status: EvidenceRequestStatus) =>
  status === "resolved" || status === "cancelled";

const FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "open", label: "Open" },
  { value: "answered", label: "Answered" },
  { value: "resolved", label: "Resolved" },
  { value: "cancelled", label: "Cancelled" },
];

function StatusPill({ status }: { status: EvidenceRequestStatus }) {
  const style = STATUS_STYLE[status];
  return (
    <span
      title={style.note}
      className={cn(
        "inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ring-1",
        style.className,
      )}
    >
      {style.label}
    </span>
  );
}

/** "who, when" as the trail would read it, or a dash. */
function Attribution({ who, when }: { who: string | null; when: string | null }) {
  if (!who && !when) return <span className="text-ink-400">-</span>;
  return (
    <span className="block">
      <span className="block font-mono text-[11px] text-ink-900">{who ?? "-"}</span>
      {when && (
        <span className="mt-0.5 block text-[11px] text-ink-400">
          {formatTimestamp(when)}
        </span>
      )}
    </span>
  );
}

const textareaClass =
  "w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-ink-900 " +
  "placeholder:text-ink-400 focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600";

export default function EvidenceRequestsPage() {
  const [data, setData] = React.useState<EvidenceRequestListResponse | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [filter, setFilter] = React.useState<StatusFilter>("all");

  // Raise a new ask
  const [creating, setCreating] = React.useState(false);
  const [newTitle, setNewTitle] = React.useState("");
  const [newDetail, setNewDetail] = React.useState("");
  const [newDueDate, setNewDueDate] = React.useState("");
  const [newItemId, setNewItemId] = React.useState("");
  const [createBusy, setCreateBusy] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);

  // Record what came back
  const [responding, setResponding] = React.useState<EvidenceRequest | null>(null);
  const [responseNote, setResponseNote] = React.useState("");
  const [respondBusy, setRespondBusy] = React.useState(false);
  const [respondError, setRespondError] = React.useState<string | null>(null);

  // Close it out — resolve (satisfied) or cancel (withdrawn)
  const [closing, setClosing] = React.useState<{
    request: EvidenceRequest;
    action: "resolve" | "cancel";
  } | null>(null);
  const [closeBusy, setCloseBusy] = React.useState(false);
  const [closeError, setCloseError] = React.useState<string | null>(null);

  /** `soft` keeps the current rows on screen while the refetch runs, so an
   *  action does not blink the whole table back to skeletons. */
  const load = React.useCallback((soft = false) => {
    setLoadError(null);
    if (!soft) setData(null);
    listEvidenceRequests()
      .then(setData)
      .catch((caught) =>
        setLoadError(
          caught instanceof ApiError
            ? caught.message
            : "Could not load the evidence requests.",
        ),
      );
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  const openCreate = () => {
    setCreateError(null);
    setNewTitle("");
    setNewDetail("");
    setNewDueDate("");
    setNewItemId("");
    setCreating(true);
  };

  const submitCreate = async () => {
    if (createBusy || !newTitle.trim()) return;
    setCreateBusy(true);
    setCreateError(null);
    try {
      await createEvidenceRequest({
        title: newTitle.trim(),
        detail: newDetail.trim() || null,
        due_date: newDueDate || null,
        review_item_id: newItemId.trim() || null,
      });
      setCreating(false);
      // Refetch rather than splice the new row in: `total` and `open_total`
      // are the backend's figures, and this screen never recounts them.
      load(true);
    } catch (caught) {
      setCreateError(
        caught instanceof ApiError ? caught.message : "Could not raise the request.",
      );
    } finally {
      setCreateBusy(false);
    }
  };

  const openRespond = (request: EvidenceRequest) => {
    setRespondError(null);
    setResponseNote(request.response_note ?? "");
    setResponding(request);
  };

  const submitRespond = async () => {
    if (!responding || respondBusy || !responseNote.trim()) return;
    setRespondBusy(true);
    setRespondError(null);
    try {
      await actOnEvidenceRequest(responding.request_id, "respond", responseNote.trim());
      setResponding(null);
      load(true);
    } catch (caught) {
      setRespondError(
        caught instanceof ApiError ? caught.message : "Could not record the response.",
      );
    } finally {
      setRespondBusy(false);
    }
  };

  const submitClose = async () => {
    if (!closing || closeBusy) return;
    setCloseBusy(true);
    setCloseError(null);
    try {
      await actOnEvidenceRequest(closing.request.request_id, closing.action);
      setClosing(null);
      load(true);
    } catch (caught) {
      setCloseError(
        caught instanceof ApiError
          ? caught.message
          : "Could not close the request.",
      );
    } finally {
      setCloseBusy(false);
    }
  };

  const requests = data?.requests ?? [];
  const shown =
    filter === "all" ? requests : requests.filter((item) => item.status === filter);

  return (
    <div className="pb-20 md:pb-0">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-bold text-ink-900">Evidence requests</h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-600">
            What you are still waiting on from the client, kept on the case
            instead of in an inbox. Each request is one thing to chase, and it
            carries who asked, what came back, and who was satisfied by it.
          </p>
        </div>
        <Button size="sm" onClick={openCreate}>
          <Plus className="h-3.5 w-3.5" aria-hidden />
          New request
        </Button>
      </div>

      <p className="mb-5 rounded-md bg-slate-50 px-3 py-2 text-xs leading-relaxed text-ink-600 ring-1 ring-slate-200">
        An evidence request is a <strong className="font-semibold">question</strong>,
        not a decision. Recording an answer approves nothing, rejects nothing,
        and re-matches nothing. The item behind it is still approved or
        rejected by a person on the review screen. Documents the client actually
        sends belong on the upload screen, where they get extracted, matched,
        and given provenance like every other document.
      </p>

      {FIXTURE_MODE && (
        <p className="mb-5 rounded-md bg-sky-50 px-3 py-2 text-xs text-sky-800 ring-1 ring-sky-200">
          Fixture mode: requests are read from the backend, so this list stays
          empty and raising one is unavailable. Set
          <code className="mx-1 font-mono">NEXT_PUBLIC_TARAZU_API_URL</code>
          and sign in to work the chase list.
        </p>
      )}

      {loadError ? (
        <ErrorState message={loadError} onRetry={() => load()} />
      ) : data === null ? (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-20" />
            ))}
          </div>
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-16 w-full" />
          ))}
        </div>
      ) : (
        <>
          {/* The outstanding figure is the backend's `open_total`: open *and*
              answered, because an answer nobody has read is still work. */}
          <div className="mb-5 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3">
            <Card>
              <CardContent className="px-3.5 py-3.5 sm:px-5 sm:py-4">
                <p className="text-xs font-medium leading-tight text-ink-400">
                  Outstanding
                </p>
                <p className="mt-1 text-2xl font-bold tabular-nums text-ink-900 sm:text-3xl">
                  {data.open_total}
                </p>
                <p className="mt-0.5 text-[11px] leading-snug text-ink-400">
                  Open or answered; answered still needs an auditor to read it
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="px-3.5 py-3.5 sm:px-5 sm:py-4">
                <p className="text-xs font-medium leading-tight text-ink-400">
                  Raised on this case
                </p>
                <p className="mt-1 text-2xl font-bold tabular-nums text-ink-900 sm:text-3xl">
                  {data.total}
                </p>
                <p className="mt-0.5 text-[11px] leading-snug text-ink-400">
                  Every ask, closed ones included
                </p>
              </CardContent>
            </Card>
            <Card className="col-span-2 lg:col-span-1">
              <CardContent className="px-3.5 py-3.5 sm:px-5 sm:py-4">
                <p className="text-xs font-medium leading-tight text-ink-400">Case</p>
                <p className="mt-1 break-all font-mono text-sm text-ink-900">
                  {data.case_id}
                </p>
                <p className="mt-0.5 text-[11px] leading-snug text-ink-400">
                  Requests stay with the engagement that raised them
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Filter chips. Counting the rows already on screen is display
              bookkeeping, not audit math — the figure that matters is above. */}
          <nav className="-mx-1 mb-4 flex gap-1 overflow-x-auto px-1 pb-1">
            {FILTERS.map(({ value, label }) => {
              const count =
                value === "all"
                  ? requests.length
                  : requests.filter((item) => item.status === value).length;
              const active = filter === value;
              return (
                <button
                  key={value}
                  onClick={() => setFilter(value)}
                  aria-pressed={active}
                  className={cn(
                    "shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                    active
                      ? "bg-brand-800 text-white"
                      : "bg-slate-100 text-ink-600 hover:bg-slate-200 hover:text-ink-900",
                  )}
                >
                  {label}
                  <span className="ml-1.5 tabular-nums opacity-70">{count}</span>
                </button>
              );
            })}
          </nav>

          {requests.length === 0 ? (
            <EmptyState
              title="Nothing outstanding"
              message="No evidence has been requested on this case. Raise one when a document or an explanation is missing. The ask, the answer, and who closed it are all recorded on the case."
              action={
                <Button size="sm" onClick={openCreate}>
                  <MessageSquarePlus className="h-3.5 w-3.5" aria-hidden />
                  New request
                </Button>
              }
            />
          ) : shown.length === 0 ? (
            <EmptyState
              title={`No ${filter} requests`}
              message="Nothing on this case is in that state. Switch the filter to see the rest."
              action={
                <Button size="sm" variant="outline" onClick={() => setFilter("all")}>
                  Show all requests
                </Button>
              }
            />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
              <table className="w-full min-w-[1080px] text-left">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                    <th className="px-4 py-2.5">Request</th>
                    <th className="px-4 py-2.5">Status</th>
                    <th className="px-4 py-2.5">Due</th>
                    <th className="px-4 py-2.5">Asked by</th>
                    <th className="px-4 py-2.5">Response</th>
                    <th className="px-4 py-2.5 text-right" aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {shown.map((request) => {
                    const closed = isClosed(request.status);
                    return (
                      <tr
                        key={request.request_id}
                        className="border-b border-slate-100 align-top text-sm last:border-0"
                      >
                        <td className="max-w-md px-4 py-3">
                          <p className="font-medium text-ink-900">{request.title}</p>
                          {request.detail && (
                            <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-ink-600">
                              {request.detail}
                            </p>
                          )}
                          <p className="mt-1 font-mono text-[10px] text-ink-400">
                            {request.request_id}
                          </p>
                          {request.review_item_id && (
                            <Link
                              href={`/review?item=${encodeURIComponent(request.review_item_id)}`}
                              className="mt-1 inline-flex items-center gap-1 font-mono text-[10px] text-brand-700 hover:underline"
                            >
                              {request.review_item_id}
                              <ArrowRight className="h-3 w-3" aria-hidden />
                            </Link>
                          )}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3">
                          <StatusPill status={request.status} />
                          {closed && (
                            <p className="mt-1.5 text-[11px] text-ink-400">
                              by{" "}
                              <span className="font-mono text-ink-600">
                                {request.closed_by ?? "-"}
                              </span>
                              {request.closed_at && (
                                <>
                                  <br />
                                  {formatTimestamp(request.closed_at)}
                                </>
                              )}
                            </p>
                          )}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-xs text-ink-600">
                          {request.due_date ? formatDate(request.due_date) : "-"}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3">
                          <Attribution
                            who={request.requested_by}
                            when={request.requested_at}
                          />
                        </td>
                        <td className="max-w-sm px-4 py-3">
                          {request.response_note ? (
                            <>
                              <p className="whitespace-pre-wrap text-xs leading-relaxed text-ink-900">
                                {request.response_note}
                              </p>
                              <div className="mt-1.5">
                                <Attribution
                                  who={request.responded_by}
                                  when={request.responded_at}
                                />
                              </div>
                            </>
                          ) : (
                            <span className="text-xs text-ink-400">
                              Nothing recorded yet
                            </span>
                          )}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-right">
                          {closed ? (
                            <span
                              className="text-[11px] text-ink-400"
                              title="Resolved and cancelled are terminal: the backend does not reopen a closed request. Raise a new one instead."
                            >
                              Closed
                            </span>
                          ) : (
                            <span className="inline-flex flex-wrap justify-end gap-1.5">
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => openRespond(request)}
                              >
                                <Reply className="h-3.5 w-3.5" aria-hidden />
                                {request.status === "answered"
                                  ? "Update response"
                                  : "Respond"}
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => {
                                  setCloseError(null);
                                  setClosing({ request, action: "resolve" });
                                }}
                              >
                                <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
                                Resolve
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => {
                                  setCloseError(null);
                                  setClosing({ request, action: "cancel" });
                                }}
                              >
                                <Ban className="h-3.5 w-3.5" aria-hidden />
                                Cancel
                              </Button>
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Raise one ask */}
      <Dialog
        open={creating}
        onClose={() => !createBusy && setCreating(false)}
        title="Ask the client for something"
        className="max-w-lg"
      >
        <div className="space-y-4">
          <Input
            label="What do you need?"
            autoFocus
            maxLength={200}
            value={newTitle}
            onChange={(event) => setNewTitle(event.target.value)}
            placeholder="The invoice behind the 12 June payment to Al-Karam Mills"
            hint="One request is one thing to chase, so each can be answered and closed on its own."
          />
          <div>
            <label
              htmlFor="evidence-detail"
              className="mb-1 block text-xs font-medium text-ink-600"
            >
              Detail (optional)
            </label>
            <textarea
              id="evidence-detail"
              rows={3}
              maxLength={2000}
              value={newDetail}
              onChange={(event) => setNewDetail(event.target.value)}
              placeholder="Why it is needed, and what would settle the question."
              className={textareaClass}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label="Due date (optional)"
              type="date"
              value={newDueDate}
              onChange={(event) => setNewDueDate(event.target.value)}
            />
            <Input
              label="Review item (optional)"
              maxLength={100}
              value={newItemId}
              onChange={(event) => setNewItemId(event.target.value)}
              placeholder="RVI-0007"
              hint="The item that raised the question. It must belong to this case."
            />
          </div>
          <p className="text-[11px] leading-relaxed text-ink-400">
            The ask is recorded against you and written to the case's immutable
            audit trail. It decides nothing about the item.
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
              disabled={createBusy || !newTitle.trim()}
            >
              {createBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
              Raise request
            </Button>
          </div>
        </div>
      </Dialog>

      {/* Record what came back */}
      <Dialog
        open={responding !== null}
        onClose={() => !respondBusy && setResponding(null)}
        title={`Response: ${responding?.title ?? ""}`}
        className="max-w-lg"
      >
        <p className="mb-2 text-xs leading-relaxed text-ink-600">
          Write down what the client said or sent, in their terms. The request
          stays outstanding: an answer is not a settlement, and it approves,
          rejects, and re-matches nothing. Resolve it once you have read what
          arrived and it satisfies the question.
        </p>
        <textarea
          autoFocus
          rows={4}
          maxLength={2000}
          value={responseNote}
          onChange={(event) => setResponseNote(event.target.value)}
          placeholder="What came back, and how."
          className={textareaClass}
        />
        <p className="mt-2 text-[11px] text-ink-400">
          Recorded verbatim against your identity in the immutable audit trail.
          Files the client sends belong on the upload screen, not here.
        </p>
        {respondError && (
          <p className="mt-3 rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
            {respondError}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setResponding(null)}
            disabled={respondBusy}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={submitRespond}
            disabled={respondBusy || !responseNote.trim()}
          >
            {respondBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
            Record response
          </Button>
        </div>
      </Dialog>

      {/* Close it out */}
      <Dialog
        open={closing !== null}
        onClose={() => !closeBusy && setClosing(null)}
        title={
          closing?.action === "cancel"
            ? `Cancel “${closing?.request.title ?? ""}”?`
            : `Resolve “${closing?.request.title ?? ""}”?`
        }
      >
        <p className="text-sm leading-relaxed text-ink-600">
          {closing?.action === "cancel"
            ? "The request is withdrawn without a response. The client was still asked, and that stays on the record: the row keeps “cancelled” and the trail keeps both events."
            : "You are saying a person read what came back and is satisfied by it. Your name goes on the close. This settles the question, not the item: the review item behind it is still approved or rejected on the review screen."}
        </p>
        <p className="mt-2 text-[11px] text-ink-400">
          Closed requests are not reopened. If the question comes back, raise a
          new request.
        </p>
        {closeError && (
          <p className="mt-3 rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
            {closeError}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setClosing(null)}
            disabled={closeBusy}
          >
            Back
          </Button>
          <Button
            size="sm"
            variant={closing?.action === "cancel" ? "danger" : "success"}
            onClick={submitClose}
            disabled={closeBusy}
          >
            {closeBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
            {closing?.action === "cancel" ? "Cancel request" : "Resolve request"}
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
