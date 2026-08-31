/**
 * Tarazu — AI Audit Assistant: the one typed API client.
 *
 * Every screen gets its data from the functions in this file and nothing else.
 * Components never fetch.
 *
 * Two modes, switched by one line of configuration:
 *
 *   - `NEXT_PUBLIC_TARAZU_API_URL` unset  → fixture mode. Responses come from
 *     the JSON files in `src/lib/fixtures/` (copies of `sample-data/fixtures/`,
 *     which the backend validates against the real Pydantic schemas). Approve
 *     and reject mutate an in-memory store so the whole flow is demoable
 *     offline.
 *   - `NEXT_PUBLIC_TARAZU_API_URL` set    → live mode. The same functions call
 *     the FastAPI backend's `/v1/...` routes.
 *
 * The UI never performs matching, math, or rule logic — it displays what the
 * backend computed (frontend/README.md). Approve and reject are only ever
 * triggered by an explicit user click; nothing in this file auto-decides.
 */

import dashboardFixture from "./fixtures/dashboard.json";
import reviewItemsFixture from "./fixtures/review-items.json";
import salesAnalyticsFixture from "./fixtures/sales-analytics.json";
import { answerFromCase, toAssistantAnswer } from "./assistant";
import { clearSession, getStoredSession } from "./auth-storage";
import type {
  ApiKeyListResponse,
  ApiKeyScope,
  ApiKeySummary,
  AssistantAnswer,
  AssistantLanguage,
  AssistantChatResponse,
  AuditRecord,
  AuditTrailResponse,
  CaseListResponse,
  CaseSummary,
  CreatedApiKeyResponse,
  DashboardSummary,
  DecisionResponse,
  DeletedApiKeyResponse,
  DeletedCaseResponse,
  DocumentListResponse,
  InvitationListResponse,
  InvitationSummary,
  MembersResponse,
  OrgRole,
  LoginResponse,
  ReportFormat,
  ReportListResponse,
  ReportSummary,
  ReviewItem,
  ReviewItemFilters,
  ReviewItemsResponse,
  SalesAnalyticsResult,
  SignupResponse,
  UpdateCaseRequest,
  UpdateProfileRequest,
  UploadFiles,
  UploadResponse,
  UserProfile,
} from "./types";

const API_URL = (process.env.NEXT_PUBLIC_TARAZU_API_URL ?? "").replace(/\/+$/, "");
const DEMO_TOKEN = process.env.NEXT_PUBLIC_TARAZU_DEMO_TOKEN ?? "";

/** True when the app is running against fixtures instead of the backend. */
export const FIXTURE_MODE = API_URL === "";

/** The seeded demo auditor. Signup/roles are out of hackathon scope. */
export const DEMO_USER_ID = "user-demo-auditor";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

// --------------------------------------------------------------------------
// Live mode plumbing
// --------------------------------------------------------------------------

/** The signed-in auditor's token first; the env demo token as a fallback. */
function authToken(): string {
  return getStoredSession()?.accessToken ?? DEMO_TOKEN;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = authToken();
  const headers: Record<string, string> = {
    ...(init?.body ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Could not reach the Tarazu backend. Is it running?");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // keep statusText
    }
    // A 401 on a non-auth route while signed in means the token expired or
    // was revoked: the session is dead, so end it rather than error every
    // screen one by one.
    if (
      response.status === 401 &&
      !path.startsWith("/v1/auth/") &&
      getStoredSession() !== null &&
      typeof window !== "undefined"
    ) {
      clearSession();
      window.location.assign("/login");
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

/** A binary GET — a rendered page, a report file — with the same auth. */
async function requestBlob(path: string): Promise<Blob> {
  const token = authToken();
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  } catch {
    throw new ApiError(0, "Could not reach the Tarazu backend. Is it running?");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // keep statusText
    }
    throw new ApiError(response.status, detail);
  }
  return response.blob();
}

/** Hand a blob to the browser as a download. */
function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

// --------------------------------------------------------------------------
// Fixture mode plumbing
// --------------------------------------------------------------------------

/** Simulated network latency so loading states are honest in the demo. */
const FIXTURE_LATENCY_MS = 450;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

/**
 * The in-memory fixture store. Module-level so decisions survive client-side
 * navigation between screens; a full page reload reseeds it from the JSON.
 */
const fixtureStore: {
  items: ReviewItem[];
  audit: AuditRecord[];
  uploaded: boolean;
} = {
  items: clone(reviewItemsFixture.items) as ReviewItem[],
  audit: [],
  uploaded: false,
};

let auditSequence = 0;

function appendFixtureAudit(
  action: AuditRecord["action"],
  itemId: string | null,
  detail: string | null,
): AuditRecord {
  auditSequence += 1;
  const record: AuditRecord = {
    audit_id: `AUD-FIX-${String(auditSequence).padStart(4, "0")}`,
    case_id: reviewItemsFixture.case_id,
    actor_type: "human",
    actor_id: DEMO_USER_ID,
    action,
    item_id: itemId,
    detail,
    occurred_at: new Date().toISOString(),
  };
  // Append-only, like the real trail: nothing in this file edits or removes.
  fixtureStore.audit.push(record);
  return record;
}

function applyFilters(items: ReviewItem[], filters?: ReviewItemFilters): ReviewItem[] {
  let result = items;
  if (filters?.decision) result = result.filter((i) => i.decision === filters.decision);
  if (filters?.match_status)
    result = result.filter((i) => i.match.status === filters.match_status);
  if (filters?.flagged !== undefined)
    result = result.filter((i) => (i.flags.length > 0) === filters.flagged);
  return result;
}

// --------------------------------------------------------------------------
// The active case — which engagement the workspace screens are about
// --------------------------------------------------------------------------

const ACTIVE_CASE_KEY = "tarazu.active-case";

/**
 * Fired on `window` whenever the active case changes — or is refreshed — so
 * mounted screens can pick up the new selection without a page reload. The
 * header's case switcher and the (app) layout's workspace wrapper are the
 * listeners that matter: one re-reads the selection, the other remounts the
 * current page, which refetches against it.
 */
export const ACTIVE_CASE_CHANGED_EVENT = "tarazu:active-case-changed";

/**
 * The case the user selected on the Cases screen, or null for "the most
 * recent" (the backend's default). Per browser; the backend never trusts it
 * beyond its own tenancy check on the id.
 */
export function getActiveCaseId(): string | null {
  try {
    return window.localStorage.getItem(ACTIVE_CASE_KEY);
  } catch {
    return null;
  }
}

export function setActiveCaseId(caseId: string | null): void {
  try {
    const previous = window.localStorage.getItem(ACTIVE_CASE_KEY);
    if (caseId === null) window.localStorage.removeItem(ACTIVE_CASE_KEY);
    else window.localStorage.setItem(ACTIVE_CASE_KEY, caseId);
    if (previous !== caseId) {
      window.dispatchEvent(new Event(ACTIVE_CASE_CHANGED_EVENT));
    }
  } catch {
    // Storage unavailable: every screen falls back to the latest case.
  }
}

/**
 * Ask every mounted screen to refetch: the active case's facts changed (a
 * rename, a corrected period) or the case it was following is gone. Same
 * mechanism a case switch uses — one event, and the workspace remounts
 * against fresh data.
 */
export function refreshWorkspace(): void {
  window.dispatchEvent(new Event(ACTIVE_CASE_CHANGED_EVENT));
}

/** True when a 404 came from the *saved* selection rather than the caller's
 * explicit case id — in which case the selection is stale and gets cleared. */
function staleActiveCase(
  caught: unknown,
  explicitCaseId: string | undefined,
  usedCaseId: string | null,
): boolean {
  if (explicitCaseId || !usedCaseId) return false;
  if (!(caught instanceof ApiError) || caught.status !== 404) return false;
  setActiveCaseId(null);
  return true;
}

// --------------------------------------------------------------------------
// The client — one typed function per screen need
// --------------------------------------------------------------------------

/** GET /v1/review-items — the human review queue. */
export async function getReviewItems(
  filters?: ReviewItemFilters,
): Promise<ReviewItemsResponse> {
  if (!FIXTURE_MODE) {
    const params = new URLSearchParams();
    const caseId = filters?.case_id ?? getActiveCaseId();
    if (caseId) params.set("case_id", caseId);
    if (filters?.decision) params.set("decision", filters.decision);
    if (filters?.match_status) params.set("match_status", filters.match_status);
    if (filters?.flagged !== undefined) params.set("flagged", String(filters.flagged));
    const query = params.toString();
    try {
      return await request<ReviewItemsResponse>(
        `/v1/review-items${query ? `?${query}` : ""}`,
      );
    } catch (caught) {
      // A stale saved selection (case deleted, different login) must not
      // wedge every screen: drop it and fall back to the latest case.
      if (staleActiveCase(caught, filters?.case_id, caseId)) {
        params.delete("case_id");
        const retry = params.toString();
        return request<ReviewItemsResponse>(
          `/v1/review-items${retry ? `?${retry}` : ""}`,
        );
      }
      throw caught;
    }
  }
  await sleep(FIXTURE_LATENCY_MS);
  const items = applyFilters(fixtureStore.items, filters);
  return {
    case_id: reviewItemsFixture.case_id,
    case_status: "ready_for_review",
    total: items.length,
    items: clone(items),
  };
}

/** GET /v1/dashboard — every number counted from deterministic results. */
export async function getDashboard(caseId?: string): Promise<DashboardSummary> {
  if (!FIXTURE_MODE) {
    const effective = caseId ?? getActiveCaseId();
    const query = effective ? `?case_id=${encodeURIComponent(effective)}` : "";
    try {
      return await request<DashboardSummary>(`/v1/dashboard${query}`);
    } catch (caught) {
      if (staleActiveCase(caught, caseId, effective)) {
        return request<DashboardSummary>("/v1/dashboard");
      }
      throw caught;
    }
  }
  await sleep(FIXTURE_LATENCY_MS);
  // Recount the decision figures from the store so approvals made during the
  // demo show up. Counting is display bookkeeping, not audit math — the real
  // numbers always come from the backend in live mode.
  const summary = clone(dashboardFixture) as unknown as DashboardSummary;
  const decisions = { pending: 0, approved: 0, rejected: 0 };
  for (const item of fixtureStore.items) decisions[item.decision] += 1;
  summary.decisions = decisions;
  // Include the sales analytics fixture so the dashboard's Sales Overview renders.
  summary.sales_analytics = clone(salesAnalyticsFixture) as unknown as SalesAnalyticsResult;
  return summary;
}

/**
 * POST /v1/review-items/{id}/approve — records one human approval.
 * Reliability rule 1: only ever called from an explicit user click.
 */
export async function approveReviewItem(
  reviewItemId: string,
  note?: string,
): Promise<DecisionResponse> {
  if (!FIXTURE_MODE) {
    return request<DecisionResponse>(
      `/v1/review-items/${encodeURIComponent(reviewItemId)}/approve`,
      { method: "POST", body: JSON.stringify(note ? { note } : {}) },
    );
  }
  await sleep(FIXTURE_LATENCY_MS);
  const item = fixtureStore.items.find((i) => i.review_item_id === reviewItemId);
  if (!item) throw new ApiError(404, `No review item ${reviewItemId}`);
  if (item.decision !== "pending")
    throw new ApiError(409, "This item already carries a decision.");
  item.decision = "approved";
  item.decided_by = DEMO_USER_ID;
  item.decided_at = new Date().toISOString();
  item.rejection_reason = null;
  const audit = appendFixtureAudit("item_approved", reviewItemId, note ?? null);
  return { review_item: clone(item), audit_record: audit };
}

/**
 * POST /v1/review-items/{id}/reject — records one human rejection.
 * A reason is required by the contract, not just the UI.
 */
export async function rejectReviewItem(
  reviewItemId: string,
  reason: string,
): Promise<DecisionResponse> {
  if (!reason.trim()) throw new ApiError(422, "A rejection needs a reason.");
  if (!FIXTURE_MODE) {
    return request<DecisionResponse>(
      `/v1/review-items/${encodeURIComponent(reviewItemId)}/reject`,
      { method: "POST", body: JSON.stringify({ reason }) },
    );
  }
  await sleep(FIXTURE_LATENCY_MS);
  const item = fixtureStore.items.find((i) => i.review_item_id === reviewItemId);
  if (!item) throw new ApiError(404, `No review item ${reviewItemId}`);
  if (item.decision !== "pending")
    throw new ApiError(409, "This item already carries a decision.");
  item.decision = "rejected";
  item.decided_by = DEMO_USER_ID;
  item.decided_at = new Date().toISOString();
  item.rejection_reason = reason;
  const audit = appendFixtureAudit("item_rejected", reviewItemId, reason);
  return { review_item: clone(item), audit_record: audit };
}

/** GET /v1/review-items/{id}/audit — every recorded action, oldest first. */
export async function getReviewItemAudit(reviewItemId: string): Promise<AuditRecord[]> {
  if (!FIXTURE_MODE) {
    return request<AuditRecord[]>(
      `/v1/review-items/${encodeURIComponent(reviewItemId)}/audit`,
    );
  }
  await sleep(FIXTURE_LATENCY_MS);
  return clone(fixtureStore.audit.filter((r) => r.item_id === reviewItemId));
}

/**
 * The fixture case's editable facts, so rename, delete, and re-upload work
 * offline exactly as they do against the backend.
 */
const fixtureCase: {
  client_name: string;
  period_start: string | null;
  period_end: string | null;
  deleted: boolean;
} = {
  client_name: (dashboardFixture as { client_name: string }).client_name,
  period_start: (dashboardFixture as { period_start: string | null }).period_start,
  period_end: (dashboardFixture as { period_end: string | null }).period_end,
  deleted: false,
};

function fixtureCaseSummary(): CaseSummary | null {
  if (fixtureCase.deleted) return null;
  return {
    case_id: reviewItemsFixture.case_id,
    client_name: fixtureCase.client_name,
    period_start: fixtureCase.period_start,
    period_end: fixtureCase.period_end,
    status: "ready_for_review",
    status_detail: null,
    created_by: DEMO_USER_ID,
    created_at: "2026-06-19T09:00:00Z",
    total_review_items: fixtureStore.items.length,
    pending_items: fixtureStore.items.filter((i) => i.decision === "pending").length,
    flagged_items: fixtureStore.items.filter((i) => i.flags.length > 0).length,
  };
}

/** GET /v1/cases — the organization's engagements, newest first. */
export async function listCases(): Promise<CaseListResponse> {
  if (!FIXTURE_MODE) return request<CaseListResponse>("/v1/cases");
  await sleep(FIXTURE_LATENCY_MS);
  const summary = fixtureCaseSummary();
  return { total: summary ? 1 : 0, cases: summary ? [summary] : [] };
}

/**
 * PATCH /v1/cases/{case_id} — rename the engagement or correct its period.
 * Send only what changes; `null` for a period clears it.
 */
export async function updateCase(
  caseId: string,
  update: UpdateCaseRequest,
): Promise<CaseSummary> {
  if (!FIXTURE_MODE) {
    return request<CaseSummary>(`/v1/cases/${encodeURIComponent(caseId)}`, {
      method: "PATCH",
      body: JSON.stringify(update),
    });
  }
  await sleep(FIXTURE_LATENCY_MS);
  if (fixtureCase.deleted || caseId !== reviewItemsFixture.case_id) {
    throw new ApiError(404, `No case ${caseId}`);
  }
  if (update.client_name !== undefined) {
    const name = update.client_name.trim();
    if (!name) throw new ApiError(422, "The case needs a client name.");
    fixtureCase.client_name = name;
  }
  if (update.period_start !== undefined) fixtureCase.period_start = update.period_start;
  if (update.period_end !== undefined) fixtureCase.period_end = update.period_end;
  const summary = fixtureCaseSummary();
  if (!summary) throw new ApiError(404, `No case ${caseId}`); // unreachable
  return summary;
}

/**
 * DELETE /v1/cases/{case_id} — remove the engagement and its working data.
 * The audit trail and any generated reports are append-only evidence and
 * outlive the case; the deletion itself is the trail's last entry.
 */
export async function deleteCase(caseId: string): Promise<DeletedCaseResponse> {
  if (!FIXTURE_MODE) {
    return request<DeletedCaseResponse>(`/v1/cases/${encodeURIComponent(caseId)}`, {
      method: "DELETE",
    });
  }
  await sleep(FIXTURE_LATENCY_MS);
  if (fixtureCase.deleted || caseId !== reviewItemsFixture.case_id) {
    throw new ApiError(404, `No case ${caseId}`);
  }
  fixtureCase.deleted = true;
  return { case_id: caseId, deleted: true };
}

/** GET /v1/audit-trail — the whole case's immutable trail, oldest first. */
export async function getAuditTrail(caseId?: string): Promise<AuditTrailResponse> {
  if (!FIXTURE_MODE) {
    const effective = caseId ?? getActiveCaseId();
    const query = effective ? `?case_id=${encodeURIComponent(effective)}` : "";
    try {
      return await request<AuditTrailResponse>(`/v1/audit-trail${query}`);
    } catch (caught) {
      if (staleActiveCase(caught, caseId, effective)) {
        return request<AuditTrailResponse>("/v1/audit-trail");
      }
      throw caught;
    }
  }
  await sleep(FIXTURE_LATENCY_MS);
  return {
    case_id: reviewItemsFixture.case_id,
    total: fixtureStore.audit.length,
    records: clone(fixtureStore.audit),
  };
}

/** POST /v1/upload — store, extract, match, flag, and save a case. */
export async function uploadDocuments(files: UploadFiles): Promise<UploadResponse> {
  if (!FIXTURE_MODE) {
    const form = new FormData();
    form.append("bank_statement", files.bankStatement);
    form.append("ledger", files.ledger);
    for (const invoice of files.invoices) form.append("invoices", invoice);
    if (files.salesData) form.append("sales_data", files.salesData);
    if (files.clientName) form.append("client_name", files.clientName);
    const token = authToken();
    const headers: Record<string, string> = token
      ? { Authorization: `Bearer ${token}` }
      : {};
    let response: Response;
    try {
      response = await fetch(`${API_URL}/v1/upload`, {
        method: "POST",
        body: form,
        headers,
      });
    } catch {
      throw new ApiError(0, "Could not reach the Tarazu backend. Is it running?");
    }
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        if (typeof body?.detail === "string") detail = body.detail;
      } catch {
        // keep statusText
      }
      throw new ApiError(response.status, detail);
    }
    return (await response.json()) as UploadResponse;
  }
  // Fixture mode: pretend the synchronous pipeline ran and point the user at
  // the sample case. The extraction takes tens of seconds for real, so the
  // simulated wait is deliberately noticeable.
  await sleep(2600);
  fixtureStore.uploaded = true;
  // A fresh upload re-opens the engagement in fixture mode, exactly as a
  // fresh upload creates a new one against the backend.
  fixtureCase.deleted = false;
  return {
    case_id: reviewItemsFixture.case_id,
    documents: [
      {
        document_id: "DOC-BNK-001",
        document_type: "bank_statement",
        filename: files.bankStatement.name,
        size_bytes: files.bankStatement.size,
        storage_path: `${reviewItemsFixture.case_id}/DOC-BNK-001/${files.bankStatement.name}`,
      },
      {
        document_id: "DOC-LED-001",
        document_type: "ledger",
        filename: files.ledger.name,
        size_bytes: files.ledger.size,
        storage_path: `${reviewItemsFixture.case_id}/DOC-LED-001/${files.ledger.name}`,
      },
      ...files.invoices.map((invoice, index) => ({
        document_id: `DOC-INV-${String(index + 1).padStart(4, "0")}`,
        document_type: "invoice" as const,
        filename: invoice.name,
        size_bytes: invoice.size,
        storage_path: `${reviewItemsFixture.case_id}/DOC-INV-${index + 1}/${invoice.name}`,
      })),
      ...(files.salesData
        ? [
            {
              document_id: "DOC-SLS-001",
              document_type: "sales_data" as const,
              filename: files.salesData.name,
              size_bytes: files.salesData.size,
              storage_path: `${reviewItemsFixture.case_id}/DOC-SLS-001/${files.salesData.name}`,
            },
          ]
        : []),
    ],
    status: "ready_for_review",
    review_item_count: fixtureStore.items.length,
    needs_human_review_count: 1,
    message: `${fixtureStore.items.length} items are ready for review.`,
  };
}

// --------------------------------------------------------------------------
// Reports — generate, list the immutable history, download
// --------------------------------------------------------------------------

/**
 * POST /v1/reports — render the PDF and the Excel workbook from the case as it
 * stands, store both, and record the generation. Every call is a new,
 * immutable report; nothing is ever overwritten.
 */
export async function generateReport(): Promise<ReportSummary> {
  if (!FIXTURE_MODE) {
    const caseId = getActiveCaseId();
    return request<ReportSummary>("/v1/reports", {
      method: "POST",
      body: JSON.stringify(caseId ? { case_id: caseId } : {}),
    });
  }
  await sleep(600);
  throw new ApiError(
    501,
    "Report generation needs the live backend. Set NEXT_PUBLIC_TARAZU_API_URL and sign in to generate a report.",
  );
}

/** GET /v1/reports — every report generated for the case, newest first. */
export async function listReports(): Promise<ReportListResponse> {
  if (!FIXTURE_MODE) {
    const caseId = getActiveCaseId();
    const query = caseId ? `?case_id=${encodeURIComponent(caseId)}` : "";
    try {
      return await request<ReportListResponse>(`/v1/reports${query}`);
    } catch (caught) {
      if (staleActiveCase(caught, undefined, caseId)) {
        return request<ReportListResponse>("/v1/reports");
      }
      throw caught;
    }
  }
  await sleep(FIXTURE_LATENCY_MS / 3);
  return { case_id: reviewItemsFixture.case_id, total: 0, reports: [] };
}

/** GET /v1/reports/{id}/download — fetch one file and hand it to the browser. */
export async function downloadReport(
  report: ReportSummary,
  format: ReportFormat,
): Promise<void> {
  if (FIXTURE_MODE) {
    throw new ApiError(501, "Report downloads need the live backend.");
  }
  const blob = await requestBlob(report.downloads[format]);
  const extension = format === "pdf" ? "pdf" : "xlsx";
  saveBlob(blob, `tarazu-${report.case_id}-${report.report_id}.${extension}`);
}

// --------------------------------------------------------------------------
// Sales analytics — the deterministic readout of a SALES_DATA export
// --------------------------------------------------------------------------

/**
 * The case to analyse: the caller's explicit id, else the saved selection.
 * The analytics routes carry the case in the path, so live mode without one
 * is a hard stop rather than a quiet fetch against the wrong case.
 */
function analyticsCaseId(caseId?: string): string {
  const effective = caseId ?? getActiveCaseId();
  if (!effective) {
    throw new ApiError(422, "Select a case before working with its sales analytics.");
  }
  return effective;
}

/**
 * GET /v1/cases/{case_id}/analytics — the saved sales-analytics readout.
 * Computes nothing and reads no documents: every figure was summed by the
 * backend's pandas when the analysis ran. 404 until it has been run at all.
 */
export async function getSalesAnalytics(
  caseId?: string,
): Promise<SalesAnalyticsResult> {
  if (!FIXTURE_MODE) {
    return request<SalesAnalyticsResult>(
      `/v1/cases/${encodeURIComponent(analyticsCaseId(caseId))}/analytics`,
    );
  }
  await sleep(FIXTURE_LATENCY_MS);
  return clone(salesAnalyticsFixture) as unknown as SalesAnalyticsResult;
}

/**
 * POST /v1/cases/{case_id}/analytics — re-read the stored sales exports and
 * recompute the readout from scratch, replacing what an earlier run saved.
 * Only ever called from an explicit user click, like every mutating route.
 */
export async function runSalesAnalytics(
  caseId?: string,
): Promise<SalesAnalyticsResult> {
  if (!FIXTURE_MODE) {
    return request<SalesAnalyticsResult>(
      `/v1/cases/${encodeURIComponent(analyticsCaseId(caseId))}/analytics`,
      { method: "POST" },
    );
  }
  // Fixture mode: the analysis "runs" against the same sample export, so the
  // deterministic readout comes back identical except for the run timestamp.
  await sleep(1400);
  const result = clone(salesAnalyticsFixture) as unknown as SalesAnalyticsResult;
  return { ...result, generated_at: new Date().toISOString() };
}

// --------------------------------------------------------------------------
// Documents — the uploaded files, and their pages as images
// --------------------------------------------------------------------------

/** GET /v1/documents — the case's uploaded files. Empty in fixture mode. */
export async function listDocuments(): Promise<DocumentListResponse> {
  if (!FIXTURE_MODE) {
    const caseId = getActiveCaseId();
    const query = caseId ? `?case_id=${encodeURIComponent(caseId)}` : "";
    try {
      return await request<DocumentListResponse>(`/v1/documents${query}`);
    } catch (caught) {
      if (staleActiveCase(caught, undefined, caseId)) {
        return request<DocumentListResponse>("/v1/documents");
      }
      throw caught;
    }
  }
  await sleep(FIXTURE_LATENCY_MS / 3);
  return { case_id: reviewItemsFixture.case_id, total: 0, documents: [] };
}

/** Rendered pages, cached per (document, page) as object URLs for this visit. */
const pageUrlCache = new Map<string, Promise<string | null>>();

/**
 * GET /v1/documents/{id}/pages/{page} — the real page as an image, or null when
 * the backend cannot serve it (fixture mode, a ledger, a page out of range).
 * Callers fall back to the schematic render on null.
 */
export function getDocumentPageUrl(documentId: string, page: number): Promise<string | null> {
  if (FIXTURE_MODE) return Promise.resolve(null);
  const key = `${documentId}#${page}`;
  const cached = pageUrlCache.get(key);
  if (cached) return cached;
  const pending = requestBlob(
    `/v1/documents/${encodeURIComponent(documentId)}/pages/${page}`,
  )
    .then((blob) => URL.createObjectURL(blob))
    .catch((caught) => {
      pageUrlCache.delete(key);
      if (caught instanceof ApiError && caught.status === 404) return null;
      throw caught;
    });
  pageUrlCache.set(key, pending);
  return pending;
}

// --------------------------------------------------------------------------
// The assistant — Ask Tarazu
// --------------------------------------------------------------------------

/**
 * POST /v1/assistant/chat — one question about the active case, answered only
 * from its persisted results. In fixture mode the answer is composed
 * client-side from the same review items (`lib/assistant.ts`), which the
 * caller passes in.
 */
export async function askAssistant(
  question: string,
  options: {
    language?: AssistantLanguage;
    fixture?: { items: ReviewItem[]; dashboard: DashboardSummary | null };
  } = {},
): Promise<AssistantAnswer> {
  if (!FIXTURE_MODE) {
    const caseId = getActiveCaseId();
    const body = {
      question,
      ...(caseId ? { case_id: caseId } : {}),
      ...(options.language ? { language: options.language } : {}),
    };
    try {
      const response = await request<AssistantChatResponse>("/v1/assistant/chat", {
        method: "POST",
        body: JSON.stringify(body),
      });
      return response.answer;
    } catch (caught) {
      if (staleActiveCase(caught, undefined, caseId)) {
        const { case_id: _dropped, ...rest } = body;
        void _dropped;
        const response = await request<AssistantChatResponse>("/v1/assistant/chat", {
          method: "POST",
          body: JSON.stringify(rest),
        });
        return response.answer;
      }
      throw caught;
    }
  }
  await sleep(900);
  const reply = answerFromCase(
    question,
    options.fixture?.items ?? [],
    options.fixture?.dashboard ?? null,
  );
  return toAssistantAnswer(question, reply, options.language);
}

// --------------------------------------------------------------------------
// Auth
// --------------------------------------------------------------------------

/**
 * POST /v1/auth/login. In fixture mode any credentials sign in the seeded
 * demo auditor so the whole flow demos offline.
 */
export async function login(email: string, password: string): Promise<LoginResponse> {
  if (!FIXTURE_MODE) {
    return request<LoginResponse>("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  }
  await sleep(FIXTURE_LATENCY_MS);
  if (!email.trim() || !password) {
    throw new ApiError(401, "Invalid email or password.");
  }
  return {
    access_token: "fixture-token",
    token_type: "bearer",
    expires_in: 3600,
    user_id: DEMO_USER_ID,
    email: email.trim(),
  };
}

/**
 * POST /v1/auth/signup. Founds a firm — or, with an invite code from an
 * owner, joins theirs with the role the invitation carries.
 */
export async function signup(
  email: string,
  password: string,
  organizationName: string,
  inviteCode?: string,
): Promise<SignupResponse> {
  if (!FIXTURE_MODE) {
    return request<SignupResponse>("/v1/auth/signup", {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        ...(inviteCode?.trim()
          ? { invite_code: inviteCode.trim() }
          : { organization_name: organizationName }),
      }),
    });
  }
  await sleep(FIXTURE_LATENCY_MS);
  if (password.length < 8) {
    throw new ApiError(422, "Password must be at least 8 characters.");
  }
  return {
    user_id: DEMO_USER_ID,
    email: email.trim(),
    org_id: "ORG-FIXTURE-0001",
    organization_name: organizationName.trim() || "Demo Audit Firm",
    role: "owner",
  };
}

/**
 * POST /v1/auth/change-password. Requires the current password; only a
 * signed-in person can call it (never an API key). In fixture mode the change
 * is simulated so the flow is demoable offline.
 */
export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<{ message: string }> {
  if (!FIXTURE_MODE) {
    return request<{ message: string }>("/v1/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    });
  }
  await sleep(FIXTURE_LATENCY_MS);
  if (!currentPassword) {
    throw new ApiError(400, "The current password is incorrect.");
  }
  if (newPassword.length < 8) {
    throw new ApiError(422, "Password must be at least 8 characters.");
  }
  if (newPassword === currentPassword) {
    throw new ApiError(400, "The new password must be different from the current one.");
  }
  return {
    message:
      "Password changed. Sessions that are already signed in stay valid " +
      "until they expire; new sign-ins need the new password.",
  };
}

// --------------------------------------------------------------------------
// Members and invitations — who is inside the firm, and how people join
// --------------------------------------------------------------------------

/** Fixture invitations, so the members screen works offline too. */
const fixtureInvitations: InvitationSummary[] = [];
let fixtureInviteSequence = 0;

/** GET /v1/members — everyone with access to this organization. */
export async function listMembers(): Promise<MembersResponse> {
  if (!FIXTURE_MODE) return request<MembersResponse>("/v1/members");
  await sleep(FIXTURE_LATENCY_MS);
  return {
    total: 1,
    members: [
      {
        user_id: DEMO_USER_ID,
        email: "demo@tarazu.pk",
        role: "owner",
        created_at: "2026-06-01T09:00:00Z",
      },
    ],
  };
}

/** POST /v1/members/invites — cut a single-use join code. Owner only. */
export async function inviteMember(
  email: string,
  role: OrgRole,
): Promise<InvitationSummary> {
  if (!email.trim()) throw new ApiError(422, "The invitation needs an email.");
  if (!FIXTURE_MODE) {
    return request<InvitationSummary>("/v1/members/invites", {
      method: "POST",
      body: JSON.stringify({ email: email.trim(), role }),
    });
  }
  await sleep(FIXTURE_LATENCY_MS);
  fixtureInviteSequence += 1;
  const invitation: InvitationSummary = {
    invite_id: `INV-fixture${String(fixtureInviteSequence).padStart(4, "0")}`,
    email: email.trim(),
    role,
    code: `TZ-${randomHex(8).toUpperCase()}`,
    created_by: DEMO_USER_ID,
    created_at: new Date().toISOString(),
    accepted_at: null,
    accepted_by: null,
    accepted: false,
  };
  fixtureInvitations.unshift(invitation);
  return clone(invitation);
}

/** GET /v1/members/invites — open and accepted invitations. Owner only. */
export async function listInvitations(): Promise<InvitationListResponse> {
  if (!FIXTURE_MODE) return request<InvitationListResponse>("/v1/members/invites");
  await sleep(FIXTURE_LATENCY_MS / 3);
  return { total: fixtureInvitations.length, invitations: clone(fixtureInvitations) };
}

/** DELETE /v1/members/invites/{id} — revoke; returns the remaining list. */
export async function revokeInvitation(
  inviteId: string,
): Promise<InvitationListResponse> {
  if (!FIXTURE_MODE) {
    return request<InvitationListResponse>(
      `/v1/members/invites/${encodeURIComponent(inviteId)}`,
      { method: "DELETE" },
    );
  }
  await sleep(FIXTURE_LATENCY_MS);
  const index = fixtureInvitations.findIndex((i) => i.invite_id === inviteId);
  if (index === -1) throw new ApiError(404, `No invitation ${inviteId}`);
  fixtureInvitations.splice(index, 1);
  return { total: fixtureInvitations.length, invitations: clone(fixtureInvitations) };
}

// --------------------------------------------------------------------------
// User profile — the signed-in person's editable presentation
// --------------------------------------------------------------------------

/** Fixture profile, per browser via localStorage so edits survive reloads. */
const PROFILE_STORAGE_KEY = "tarazu.fixture-profile";

function readFixtureProfile(): UserProfile {
  const empty: UserProfile = {
    user_id: DEMO_USER_ID,
    full_name: null,
    job_title: null,
    phone: null,
    avatar: null,
    gender: null,
    date_of_birth: null,
    location: null,
    license_number: null,
    language: null,
    notify_case_ready: true,
    notify_high_severity: true,
    notify_weekly_digest: false,
  };
  try {
    const raw = window.localStorage.getItem(PROFILE_STORAGE_KEY);
    return raw ? { ...empty, ...(JSON.parse(raw) as UserProfile) } : empty;
  } catch {
    return empty;
  }
}

/** GET /v1/profile — the caller's own profile; all-null when never saved. */
export async function getProfile(): Promise<UserProfile> {
  if (!FIXTURE_MODE) return request<UserProfile>("/v1/profile");
  await sleep(FIXTURE_LATENCY_MS / 3);
  return readFixtureProfile();
}

/** PUT /v1/profile — full replacement; omitted or blank fields are cleared. */
export async function saveProfile(update: UpdateProfileRequest): Promise<UserProfile> {
  if (!FIXTURE_MODE) {
    return request<UserProfile>("/v1/profile", {
      method: "PUT",
      body: JSON.stringify(update),
    });
  }
  await sleep(FIXTURE_LATENCY_MS);
  const profile: UserProfile = {
    user_id: DEMO_USER_ID,
    full_name: update.full_name?.trim() || null,
    job_title: update.job_title?.trim() || null,
    phone: update.phone?.trim() || null,
    avatar: update.avatar || null,
    gender: update.gender?.trim() || null,
    date_of_birth: update.date_of_birth || null,
    location: update.location?.trim() || null,
    license_number: update.license_number?.trim() || null,
    language: update.language || null,
    notify_case_ready: update.notify_case_ready ?? true,
    notify_high_severity: update.notify_high_severity ?? true,
    notify_weekly_digest: update.notify_weekly_digest ?? false,
  };
  try {
    window.localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profile));
  } catch {
    // Storage unavailable: the profile still holds for this visit.
  }
  return profile;
}

// --------------------------------------------------------------------------
// API keys — how an organization's own tooling reaches Tarazu
// --------------------------------------------------------------------------

/** Fixture keys, seeded with one so the settings screen has something real. */
const fixtureApiKeys: ApiKeySummary[] = [
  {
    key_id: "AK-fixture0001",
    name: "n8n integration",
    key_prefix: "trz_live_a1b2c3d4",
    scopes: ["read"],
    created_by: DEMO_USER_ID,
    created_at: "2026-08-20T09:15:00Z",
    last_used_at: "2026-08-24T07:02:11Z",
    revoked_at: null,
    revoked: false,
  },
];

let fixtureKeySequence = 1;

const randomHex = (length: number) =>
  Array.from({ length }, () => "0123456789abcdef"[Math.floor(Math.random() * 16)]).join("");

/** GET /v1/api-keys — the organization's keys, revoked ones included. */
export async function listApiKeys(): Promise<ApiKeyListResponse> {
  if (!FIXTURE_MODE) return request<ApiKeyListResponse>("/v1/api-keys");
  await sleep(FIXTURE_LATENCY_MS);
  return { total: fixtureApiKeys.length, keys: clone(fixtureApiKeys) };
}

/** POST /v1/api-keys — the only response that ever carries the raw key. */
export async function createApiKey(
  name: string,
  scopes: ApiKeyScope[],
): Promise<CreatedApiKeyResponse> {
  if (!name.trim()) throw new ApiError(422, "The key needs a name.");
  if (scopes.length === 0) throw new ApiError(422, "Pick at least one scope.");
  if (!FIXTURE_MODE) {
    return request<CreatedApiKeyResponse>("/v1/api-keys", {
      method: "POST",
      body: JSON.stringify({ name: name.trim(), scopes }),
    });
  }
  await sleep(FIXTURE_LATENCY_MS);
  fixtureKeySequence += 1;
  const raw = `trz_live_${randomHex(32)}`;
  const key: ApiKeySummary = {
    key_id: `AK-fixture${String(fixtureKeySequence).padStart(4, "0")}`,
    name: name.trim(),
    key_prefix: raw.slice(0, 17),
    scopes,
    created_by: DEMO_USER_ID,
    created_at: new Date().toISOString(),
    last_used_at: null,
    revoked_at: null,
    revoked: false,
  };
  fixtureApiKeys.unshift(key);
  return {
    api_key: raw,
    key: clone(key),
    message:
      "Save this key now: it is shown once and cannot be retrieved again. " +
      "Store it in your integration's secret store, never in source control.",
  };
}

/**
 * DELETE /v1/api-keys/{key_id} — revoke. The row stays, so the audit trail's
 * `api-key:<prefix>` entries remain resolvable. There is no un-revoke.
 */
export async function revokeApiKey(keyId: string): Promise<ApiKeySummary> {
  if (!FIXTURE_MODE) {
    return request<ApiKeySummary>(`/v1/api-keys/${encodeURIComponent(keyId)}`, {
      method: "DELETE",
    });
  }
  await sleep(FIXTURE_LATENCY_MS);
  const key = fixtureApiKeys.find((candidate) => candidate.key_id === keyId);
  if (!key) throw new ApiError(404, `No API key ${keyId}`);
  if (!key.revoked) {
    key.revoked = true;
    key.revoked_at = new Date().toISOString();
  }
  return clone(key);
}

/** PATCH /v1/api-keys/{key_id} — rename. The one editable thing about a key. */
export async function renameApiKey(keyId: string, name: string): Promise<ApiKeySummary> {
  if (!name.trim()) throw new ApiError(422, "The key needs a name.");
  if (!FIXTURE_MODE) {
    return request<ApiKeySummary>(`/v1/api-keys/${encodeURIComponent(keyId)}`, {
      method: "PATCH",
      body: JSON.stringify({ name: name.trim() }),
    });
  }
  await sleep(FIXTURE_LATENCY_MS);
  const key = fixtureApiKeys.find((candidate) => candidate.key_id === keyId);
  if (!key) throw new ApiError(404, `No API key ${keyId}`);
  key.name = name.trim();
  return clone(key);
}

/**
 * DELETE /v1/api-keys/{key_id}/record — permanently remove the key's row,
 * active or revoked. Deleting an active key stops it immediately: the backend
 * authenticates keys by hash, and the hash goes with the row.
 */
export async function deleteApiKey(keyId: string): Promise<DeletedApiKeyResponse> {
  if (!FIXTURE_MODE) {
    return request<DeletedApiKeyResponse>(
      `/v1/api-keys/${encodeURIComponent(keyId)}/record`,
      { method: "DELETE" },
    );
  }
  await sleep(FIXTURE_LATENCY_MS);
  const index = fixtureApiKeys.findIndex((candidate) => candidate.key_id === keyId);
  if (index === -1) throw new ApiError(404, `No API key ${keyId}`);
  fixtureApiKeys.splice(index, 1);
  return { key_id: keyId, deleted: true };
}
