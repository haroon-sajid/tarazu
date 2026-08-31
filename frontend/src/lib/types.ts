/**
 * Tarazu — AI Audit Assistant: frontend copies of the shared data contracts.
 *
 * These interfaces mirror `backend/app/shared/schemas.py` and the shapes in
 * `docs/api-contracts.md`. If a contract changes there, it changes here in the
 * same commit.
 *
 * The most important rule of the contract is kept structurally: extraction
 * confidence (how sure the AI is that it *read* a value) and match strength
 * (how well two rows *line up*, computed by deterministic pandas) are separate
 * types on separate fields. There is deliberately no field named plain
 * `confidence` anywhere in this file.
 */

/** How sure the AI is that it read a value correctly. AI output only. */
export type Confidence = "high" | "medium" | "low";

/** How well two rows line up. Computed by deterministic code, never by AI. */
export type MatchStrength = "high" | "medium" | "low";

export type MatchStatus = "matched" | "partial" | "unmatched";
export type Severity = "high" | "medium" | "low";
export type ReviewDecision = "pending" | "approved" | "rejected";
export type ActorType = "human" | "ai" | "system";
export type DocumentType = "bank_statement" | "invoice" | "ledger" | "sales_data";

export type CaseStatus =
  | "uploaded"
  | "extracting"
  | "awaiting_matching"
  | "ready_for_review"
  | "failed";

export type AuditAction =
  | "case_created"
  | "case_updated"
  | "case_deleted"
  | "document_uploaded"
  | "extraction_completed"
  | "second_opinion_completed"
  | "matching_completed"
  | "flag_raised"
  | "item_approved"
  | "item_rejected"
  | "report_generated"
  | "assistant_question_asked"
  | "assistant_answered"
  | "sales_analytics_run";

/** Normalised [x0, y0, x1, y1] in 0..1 page space, origin top-left. */
export type BoundingBox = [number, number, number, number];

export type RawValue = string | number | boolean | null;

/**
 * Where a value came from. Documents locate by `page` + `bbox`/`text_snippet`
 * (what the evidence viewer highlights); spreadsheets locate by `row_number`.
 */
export interface Provenance {
  document_id: string;
  page?: number | null;
  row_number?: number | null;
  bbox?: BoundingBox | number[] | null;
  text_snippet?: string | null;
}

export interface ExtractedField {
  field: string;
  value: RawValue;
  extraction_confidence: Confidence;
  source: Provenance;
  unreadable: boolean;
}

export interface LedgerEntry {
  ledger_row_id: string;
  date: string; // YYYY-MM-DD
  amount: number;
  party_name: string;
  description?: string | null;
  account_code?: string | null;
  currency: string;
  source: Provenance;
}

export interface BankTransaction {
  bank_row_id: string;
  date: string;
  amount: number;
  description: string;
  balance?: number | null;
  currency: string;
  source: Provenance;
}

export interface Invoice {
  invoice_id: string;
  invoice_number: string;
  date: string;
  amount: number;
  party_name: string;
  currency: string;
  source: Provenance;
}

/** Produced by `modules/matching/` with pandas only — never by AI. */
export interface MatchResult {
  ledger_row_id: string;
  bank_row_id: string | null;
  invoice_id: string | null;
  status: MatchStatus;
  match_strength: MatchStrength;
  /** Plain English, shown verbatim to the auditor. */
  reason: string;
  rule_id: string;
}

/** A red flag raised by `modules/rules/`. A suggestion, never a verdict. */
export interface Flag {
  flag_id: string;
  rule_id: string;
  severity: Severity;
  explanation: string;
  source_row_id: string;
  related_row_ids: string[];
  source?: Provenance | null;
}

export interface AuditRecord {
  audit_id: string;
  case_id: string;
  actor_type: ActorType;
  actor_id: string;
  action: AuditAction;
  item_id?: string | null;
  detail?: string | null;
  occurred_at: string; // RFC 3339 UTC
}

/** One row of the review screen: the unit a human approves or rejects. */
export interface ReviewItem {
  review_item_id: string;
  case_id: string;
  ledger_entry: LedgerEntry;
  bank_transaction: BankTransaction | null;
  invoice: Invoice | null;
  match: MatchResult;
  flags: Flag[];
  /** The AI's, rolled up as the weakest reading behind this item. */
  extraction_confidence: Confidence;
  evidence: ExtractedField[];
  decision: ReviewDecision;
  decided_by: string | null;
  decided_at: string | null;
  rejection_reason: string | null;
}

export interface ReviewItemsResponse {
  case_id: string;
  case_status?: CaseStatus;
  total: number;
  items: ReviewItem[];
}

export interface ReviewItemFilters {
  case_id?: string;
  decision?: ReviewDecision;
  match_status?: MatchStatus;
  flagged?: boolean;
}

/** Response of POST .../approve and .../reject. */
export interface DecisionResponse {
  review_item: ReviewItem;
  audit_record: AuditRecord;
}

// --------------------------------------------------------------------------
// Dashboard
// --------------------------------------------------------------------------

export interface StatusBreakdown {
  matched: number;
  partial: number;
  unmatched: number;
}

export interface DecisionBreakdown {
  pending: number;
  approved: number;
  rejected: number;
}

export interface ConfidenceBreakdown {
  high: number;
  medium: number;
  low: number;
}

export interface SeverityBreakdown {
  high: number;
  medium: number;
  low: number;
}

export interface ReadinessComponent {
  percent: number;
  count: number;
  total: number;
}

export interface AuditReadiness {
  score: number;
  matched: ReadinessComponent;
  flags_reviewed: ReadinessComponent;
  completeness: ReadinessComponent;
}

export interface NextBestAction {
  action: string;
  severity: Severity;
  rule_id: string;
  review_item_id: string;
  party_name: string;
}

export interface BenfordDigit {
  digit: number;
  observed_count: number;
  observed_frequency: number;
  expected_frequency: number;
  deviation: number;
}

export interface BenfordResult {
  sample_size: number;
  digits: BenfordDigit[];
  chi_square: number;
  degrees_of_freedom: number;
  deviates_significantly: boolean;
}

export interface DashboardSummary {
  case_id: string;
  client_name: string;
  period_start: string | null;
  period_end: string | null;
  total_review_items: number;
  match_status: StatusBreakdown;
  decisions: DecisionBreakdown;
  extraction_confidence: ConfidenceBreakdown;
  flagged_item_count: number;
  total_flags: number;
  flags_by_severity: SeverityBreakdown;
  benford: BenfordResult | null;
  audit_readiness_score: AuditReadiness;
  data_confidence: string;
  next_best_actions: NextBestAction[];
  estimated_hours_saved: number;
  /** Present when a SALES_DATA document was uploaded and analytics ran. */
  sales_analytics: SalesAnalyticsResult | null;
}

// --------------------------------------------------------------------------
// Sales analytics — deterministic pandas over a SALES_DATA export
// --------------------------------------------------------------------------

/** One sale row read out of a SALES_DATA export (Excel or CSV), no AI. */
export interface SalesRecord {
  sales_row_id: string;
  date: string; // YYYY-MM-DD
  amount: number;
  customer_name: string;
  product: string;
  /** null in exports that carry no region column; such rows stay out of sales_by_region. */
  region: string | null;
  currency: string;
  source: Provenance;
}

/** Revenue for one calendar month. Months are unique and ascending. */
export interface MonthlyRevenue {
  month: string; // YYYY-MM
  revenue: number;
  transaction_count: number;
}

/** One product's revenue over the whole period, highest revenue first. */
export interface ProductRevenue {
  product: string;
  revenue: number;
  transaction_count: number;
  /** Percent of total revenue, rounded to two decimals. */
  share: number;
}

/** One customer's revenue over the whole period. The top five, ranked. */
export interface CustomerSummary {
  customer_name: string;
  revenue: number;
  transaction_count: number;
  share: number;
}

/** One region's revenue over the whole period; region-carrying rows only. */
export interface RegionSummary {
  region: string;
  revenue: number;
  transaction_count: number;
  share: number;
}

/**
 * A pattern in the sales data worth a human's attention. Like a `Flag`, a
 * suggestion and never a verdict: `kind` is one of the module's rule ids
 * (`negative-amount`, `duplicate-transaction`, `revenue-spike`,
 * `large-transaction`), and row-level anomalies name their row in
 * `source_row_id` while month-level ones name the month instead.
 */
export interface SalesAnomaly {
  anomaly_id: string;
  kind: string;
  explanation: string;
  source_row_id: string | null;
  related_row_ids: string[];
  month: string | null; // YYYY-MM
  source: Provenance | null;
}

/** The whole sales-analytics readout for one case. Pure arithmetic, no AI. */
export interface SalesAnalyticsResult {
  record_count: number;
  period_start: string | null;
  period_end: string | null;
  total_revenue: number;
  monthly_revenue: MonthlyRevenue[];
  revenue_by_product: ProductRevenue[];
  top_customers: CustomerSummary[];
  sales_by_region: RegionSummary[];
  anomalies: SalesAnomaly[];
  /** The documents the records were read from, so the readout names its sources. */
  document_ids: string[];
  generated_at: string; // RFC 3339 UTC
}

// --------------------------------------------------------------------------
// Cases and the case-wide audit trail
// --------------------------------------------------------------------------

/** GET /v1/cases — one engagement plus its working counts. */
export interface CaseSummary {
  case_id: string;
  client_name: string;
  period_start: string | null;
  period_end: string | null;
  status: CaseStatus;
  status_detail: string | null;
  created_by: string;
  created_at: string;
  total_review_items: number;
  pending_items: number;
  flagged_items: number;
}

export interface CaseListResponse {
  total: number;
  cases: CaseSummary[];
}

/**
 * PATCH /v1/cases/{case_id} — send only what changes. A field left out keeps
 * its current value; `null` for a period clears it; the client name cannot
 * be cleared.
 */
export interface UpdateCaseRequest {
  client_name?: string;
  period_start?: string | null;
  period_end?: string | null;
}

/**
 * DELETE /v1/cases/{case_id} — the engagement's working data is gone.
 * Generated reports and the audit trail are append-only evidence and outlive
 * the case; the deletion itself is the trail's last entry naming it.
 */
export interface DeletedCaseResponse {
  case_id: string;
  deleted: boolean;
}

/** GET /v1/audit-trail — one case's full immutable trail, oldest first. */
export interface AuditTrailResponse {
  case_id: string;
  total: number;
  records: AuditRecord[];
}

// --------------------------------------------------------------------------
// Reports — the deliverable, and the append-only history of generating it
// --------------------------------------------------------------------------

export type ReportFormat = "pdf" | "excel";

export interface ReportDownloads {
  pdf: string;
  excel: string;
}

/** One generated report. Immutable: regenerating adds a new one. */
export interface ReportSummary {
  report_id: string;
  case_id: string;
  generated_by: string;
  generated_at: string;
  item_count: number;
  approved_count: number;
  rejected_count: number;
  /** Counted and named as pending in the report; never listed as findings. */
  pending_count: number;
  flag_count: number;
  audit_record_count: number;
  pdf_sha256: string;
  excel_sha256: string;
  downloads: ReportDownloads;
}

export interface ReportListResponse {
  case_id: string;
  total: number;
  reports: ReportSummary[];
}

// --------------------------------------------------------------------------
// Documents — the uploaded files, and their pages as images
// --------------------------------------------------------------------------

export interface DocumentSummary {
  document_id: string;
  document_type: DocumentType;
  filename: string;
  size_bytes: number;
  /** null for the ledger, which has rows rather than pages. */
  page_count: number | null;
  needs_human_review: boolean;
  file_url: string;
  /** `{page}` is 1-based; null for the ledger. */
  page_url_template: string | null;
}

export interface DocumentListResponse {
  case_id: string;
  total: number;
  documents: DocumentSummary[];
}

// --------------------------------------------------------------------------
// The assistant — Ask Tarazu
// --------------------------------------------------------------------------

export type AssistantLanguage = "en" | "ur";

export type AssistantIntent =
  | "summary"
  | "matches"
  | "unmatched"
  | "missing_evidence"
  | "flags"
  | "rule"
  | "duplicates"
  | "party"
  | "item"
  | "invoices"
  | "bank"
  | "ledger"
  | "confidence"
  | "totals"
  | "top_vendors"
  | "largest"
  | "compare_months"
  | "search_amount"
  | "search_date"
  | "benford"
  | "case_info"
  | "cases"
  | "documents"
  | "extractions"
  | "decisions"
  | "reports"
  | "history"
  | "concept"
  | "help"
  | "unsupported"
  | "unknown";

export interface AssistantCitation {
  document_id: string;
  page?: number | null;
  row_number?: number | null;
  text_snippet?: string | null;
  review_item_id?: string | null;
}

/** One computed figure the answer was written from. */
export interface AssistantFact {
  label: string;
  value: string;
}

/**
 * An answer. `answer_confidence` is the module's confidence that the text is
 * a faithful readout of the case data; it is deliberately not named
 * `confidence` (see types.ts header). `grounded: false` is a refusal.
 */
export interface AssistantAnswer {
  question: string;
  language: AssistantLanguage;
  intent: AssistantIntent;
  text: string;
  answer_confidence: Confidence;
  grounded: boolean;
  citations: AssistantCitation[];
  facts: AssistantFact[];
  /** "assistant.deterministic", or the model that rephrased the facts. */
  composed_by: string;
}

export interface AssistantChatResponse {
  case_id: string;
  answer: AssistantAnswer;
  audit_record: AuditRecord;
}

// --------------------------------------------------------------------------
// Upload
// --------------------------------------------------------------------------

export interface UploadedDocument {
  document_id: string;
  document_type: DocumentType;
  filename: string;
  size_bytes: number;
  storage_path: string;
}

export interface UploadResponse {
  case_id: string;
  documents: UploadedDocument[];
  status: CaseStatus;
  review_item_count: number;
  needs_human_review_count: number;
  message: string;
}

export interface UploadFiles {
  bankStatement: File;
  ledger: File;
  invoices: File[];
  /** Optional: a sales data export (Excel or CSV). */
  salesData?: File;
  clientName?: string;
}

// --------------------------------------------------------------------------
// Auth
// --------------------------------------------------------------------------

export type OrgRole = "owner" | "member";

/** POST /v1/auth/login response. */
export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  email: string | null;
}

/** POST /v1/auth/signup response. No token comes back — sign in next. */
export interface SignupResponse {
  user_id: string;
  email: string;
  org_id: string;
  organization_name: string;
  role: OrgRole;
}

/** What the frontend holds about the signed-in auditor. */
export interface Session {
  accessToken: string;
  /** Unix ms after which the token is stale and the user must sign in again. */
  expiresAt: number;
  userId: string;
  email: string;
  orgId: string | null;
  organizationName: string | null;
  role: OrgRole | null;
}

// --------------------------------------------------------------------------
// API keys
// --------------------------------------------------------------------------

export type ApiKeyScope = "read" | "write";

/** One key, as anybody is ever allowed to read it back. No hash, no raw key. */
export interface ApiKeySummary {
  key_id: string;
  name: string;
  key_prefix: string;
  scopes: ApiKeyScope[];
  created_by: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
  revoked: boolean;
}

/** POST /v1/api-keys — the only response that ever carries the raw key. */
export interface CreatedApiKeyResponse {
  api_key: string;
  key: ApiKeySummary;
  message: string;
}

export interface ApiKeyListResponse {
  total: number;
  keys: ApiKeySummary[];
}

/** DELETE /v1/api-keys/{key_id}/record — the row is gone for good. */
export interface DeletedApiKeyResponse {
  key_id: string;
  deleted: boolean;
}

// --------------------------------------------------------------------------
// Members and invitations
// --------------------------------------------------------------------------

/** GET /v1/members — one person with access to the organization. */
export interface MemberSummary {
  user_id: string;
  email: string | null;
  role: OrgRole;
  created_at: string;
}

export interface MembersResponse {
  total: number;
  members: MemberSummary[];
}

/** An invitation as the owner sees it — the join code included. */
export interface InvitationSummary {
  invite_id: string;
  email: string;
  role: OrgRole;
  code: string;
  created_by: string;
  created_at: string;
  accepted_at: string | null;
  accepted_by: string | null;
  accepted: boolean;
}

export interface InvitationListResponse {
  total: number;
  invitations: InvitationSummary[];
}

// --------------------------------------------------------------------------
// User profile
// --------------------------------------------------------------------------

/**
 * GET/PUT /v1/profile — the signed-in person's editable profile. Presentation
 * only: nothing here feeds authentication, tenancy, or the audit trail.
 * `avatar` is a size-capped data:image/... URL.
 */
export interface UserProfile {
  user_id: string;
  full_name: string | null;
  job_title: string | null;
  phone: string | null;
  avatar: string | null;
  gender: string | null;
  date_of_birth: string | null; // YYYY-MM-DD
  location: string | null;
  /** Practicing license or institute membership number (ICAP, ACCA, ...). */
  license_number: string | null;
  /** Preferred language for explanations: "en" or "ur". */
  language: string | null;
  notify_case_ready: boolean;
  notify_high_severity: boolean;
  notify_weekly_digest: boolean;
}

/** PUT /v1/profile body — a full replacement; omitted fields are cleared. */
export interface UpdateProfileRequest {
  full_name?: string | null;
  job_title?: string | null;
  phone?: string | null;
  avatar?: string | null;
  gender?: string | null;
  date_of_birth?: string | null;
  location?: string | null;
  license_number?: string | null;
  language?: string | null;
  notify_case_ready?: boolean;
  notify_high_severity?: boolean;
  notify_weekly_digest?: boolean;
}
