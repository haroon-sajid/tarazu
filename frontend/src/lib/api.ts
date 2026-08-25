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
import { clearSession, getStoredSession } from "./auth-storage";
import type {
  ApiKeyListResponse,
  ApiKeyScope,
  ApiKeySummary,
  AuditRecord,
  CreatedApiKeyResponse,
  DashboardSummary,
  DecisionResponse,
  LoginResponse,
  ReviewItem,
  ReviewItemFilters,
  ReviewItemsResponse,
  SignupResponse,
  UploadFiles,
  UploadResponse,
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
// The client — one typed function per screen need
// --------------------------------------------------------------------------

/** GET /v1/review-items — the human review queue. */
export async function getReviewItems(
  filters?: ReviewItemFilters,
): Promise<ReviewItemsResponse> {
  if (!FIXTURE_MODE) {
    const params = new URLSearchParams();
    if (filters?.case_id) params.set("case_id", filters.case_id);
    if (filters?.decision) params.set("decision", filters.decision);
    if (filters?.match_status) params.set("match_status", filters.match_status);
    if (filters?.flagged !== undefined) params.set("flagged", String(filters.flagged));
    const query = params.toString();
    return request<ReviewItemsResponse>(`/v1/review-items${query ? `?${query}` : ""}`);
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
    const query = caseId ? `?case_id=${encodeURIComponent(caseId)}` : "";
    return request<DashboardSummary>(`/v1/dashboard${query}`);
  }
  await sleep(FIXTURE_LATENCY_MS);
  // Recount the decision figures from the store so approvals made during the
  // demo show up. Counting is display bookkeeping, not audit math — the real
  // numbers always come from the backend in live mode.
  const summary = clone(dashboardFixture) as unknown as DashboardSummary;
  const decisions = { pending: 0, approved: 0, rejected: 0 };
  for (const item of fixtureStore.items) decisions[item.decision] += 1;
  summary.decisions = decisions;
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

/** POST /v1/upload — store, extract, match, flag, and save a case. */
export async function uploadDocuments(files: UploadFiles): Promise<UploadResponse> {
  if (!FIXTURE_MODE) {
    const form = new FormData();
    form.append("bank_statement", files.bankStatement);
    form.append("ledger", files.ledger);
    for (const invoice of files.invoices) form.append("invoices", invoice);
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
    ],
    status: "ready_for_review",
    review_item_count: fixtureStore.items.length,
    needs_human_review_count: 1,
    message: `${fixtureStore.items.length} items are ready for review.`,
  };
}

/**
 * POST /v1/reports — not defined in the contract yet (`docs/api-contracts.md`
 * lists it "To be defined"). The report page calls this and renders the error
 * state honestly rather than faking a download.
 */
export async function generateReport(kind: "pdf" | "excel"): Promise<never> {
  if (!FIXTURE_MODE) {
    return request<never>(`/v1/reports`, {
      method: "POST",
      body: JSON.stringify({ format: kind }),
    });
  }
  await sleep(600);
  throw new ApiError(
    501,
    "Report generation needs the live backend — POST /v1/reports is not implemented yet.",
  );
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

/** POST /v1/auth/signup. Creates the user, their firm, and their membership. */
export async function signup(
  email: string,
  password: string,
  organizationName: string,
): Promise<SignupResponse> {
  if (!FIXTURE_MODE) {
    return request<SignupResponse>("/v1/auth/signup", {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        organization_name: organizationName,
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
      "Save this key now — it is shown once and cannot be retrieved again. " +
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
