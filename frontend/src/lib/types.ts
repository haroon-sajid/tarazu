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
  /** Legacy: the pipeline no longer produces it, old rows still carry it. */
  | "awaiting_matching"
  | "matching"
  | "ready_for_review"
  /** Every item carries an explicit human decision. */
  | "approved"
  /** A report has been generated for the case. */
  | "reported"
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
  | "value_corrected"
  | "case_signed_off"
  | "evidence_requested"
  | "evidence_answered"
  | "evidence_resolved"
  | "evidence_cancelled"
  | "client_created"
  | "client_updated"
  | "client_archived"
  | "job_queued"
  | "job_failed"
  | "sample_drawn"
  | "bundle_exported"
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

/**
 * How one sales export was read and cleaned — which sheet and header row it
 * came from, how the client's own columns were mapped, and which rows were
 * skipped and why. One per export, carried on the readout so that nothing
 * about the cleaning is silent.
 */
export interface SourceReadReport {
  document_id: string;
  filename: string;
  format: string; // csv | tsv | excel | ods | json
  sheet: string | null;
  encoding: string | null;
  delimiter: string | null;
  /** The spreadsheet row (1-based) the header was found on. */
  header_row: number;
  /** Canonical field → the client's own column header it was read from. */
  columns: Record<string, string>;
  /** True when the amount was computed as quantity × unit price. */
  amount_derived: boolean;
  rows_seen: number;
  rows_used: number;
  rows_skipped: number;
  /** Reason → count: blank, total_row, no_date, no_amount. */
  skipped: Record<string, number>;
  /** Field → how many rows were filed under "Unspecified" for it. */
  filled_defaults: Record<string, number>;
  warnings: string[];
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
  /** One read report per export; absent on readouts saved before the reader reported. */
  data_quality?: SourceReadReport[];
  generated_at: string; // RFC 3339 UTC
}

// --------------------------------------------------------------------------
// Cases and the case-wide audit trail
// --------------------------------------------------------------------------

/** GET /v1/cases — one engagement plus its working counts. */
export interface CaseSummary {
  case_id: string;
  client_name: string;
  /** The recurring client this period belongs to (ADR 0005), if any. */
  client_id?: string | null;
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
  /** Attach the period to a recurring client, or detach it with `null`. */
  client_id?: string | null;
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
  /** Present when the work was queued. Poll `getJob(job_id)`. */
  job_id?: string | null;
}

export interface UploadFiles {
  bankStatement: File;
  ledger: File;
  invoices: File[];
  clientName?: string;
  /** Run this period against a recurring client's own rule thresholds. */
  clientId?: string;
  /** Queue the processing and return a job to poll instead of blocking. */
  background?: boolean;
}

/** Metadata for a sales data export uploaded separately from audit documents. */
export interface SalesDataUploadSummary {
  sales_data_id: string;
  case_id: string;
  filename: string;
  size_bytes: number;
  uploaded_by: string;
  uploaded_at: string; // RFC 3339 UTC
}

// --------------------------------------------------------------------------
// Auth
// --------------------------------------------------------------------------

/** `viewer` is the read-only role from ADR 0005 — the audited business's owner. */
export type OrgRole = "owner" | "member" | "viewer";

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

// --------------------------------------------------------------------------
// Clients and periods (ADR 0005)
//
// A firm audits a business every month or quarter, not a case once. The client
// carries what outlives a period: its rule thresholds, its currency, and the
// language its owner reads.
// --------------------------------------------------------------------------

/** One client's own red-flag thresholds. The firm's rules, not the product's. */
export interface ClientRuleConfig {
  approval_limits: number[];
  round_number_floor: number;
  date_tolerance_days: number;
  duplicate_window_days: number;
  near_limit_tolerance: number;
  /** Maker-checker: a report needs a second person's signature first. */
  require_sign_off: boolean;
}

export interface ClientSummary {
  client_id: string;
  name: string;
  reference: string | null;
  rules: ClientRuleConfig;
  currency: string;
  language: AssistantLanguage;
  relationship_owner: string | null;
  notes: string | null;
  created_by: string;
  created_at: string;
  archived_at: string | null;
  archived: boolean;
  period_count: number;
  pending_items: number;
  open_evidence_requests: number;
  last_period_end: string | null;
  last_activity_at: string | null;
}

export interface ClientListResponse {
  total: number;
  clients: ClientSummary[];
}

export interface ClientDetailResponse {
  client: ClientSummary;
  periods: CaseSummary[];
}

export interface CreateClientRequest {
  name: string;
  reference?: string | null;
  rules?: ClientRuleConfig;
  currency?: string;
  language?: AssistantLanguage;
  relationship_owner?: string | null;
  notes?: string | null;
}

/** PATCH /v1/clients/{id} — only what the request names changes. */
export type UpdateClientRequest = Partial<CreateClientRequest>;

// --------------------------------------------------------------------------
// Background jobs
// --------------------------------------------------------------------------

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

/**
 * How far a queued upload has got. Presentation only — every result comes from
 * the case, the queue, and the trail, exactly as in the synchronous path.
 */
export interface JobSummary {
  job_id: string;
  case_id: string;
  status: JobStatus;
  progress: number;
  step: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  finished: boolean;
}

export interface JobListResponse {
  total: number;
  jobs: JobSummary[];
}

// --------------------------------------------------------------------------
// Value corrections
// --------------------------------------------------------------------------

/**
 * What a human says a misread value actually is. Both readings are kept: the
 * extraction is never overwritten, and recording one does not re-run matching.
 */
export interface ValueCorrection {
  correction_id: string;
  case_id: string;
  review_item_id: string;
  document_id: string;
  field: string;
  ai_value: string | null;
  corrected_value: string;
  note: string | null;
  corrected_by: string;
  corrected_at: string;
}

export interface CreateCorrectionRequest {
  document_id: string;
  field: string;
  ai_value?: string | null;
  corrected_value: string;
  note?: string | null;
}

export interface CorrectionResponse {
  correction: ValueCorrection;
  audit_record: AuditRecord;
}

export interface CorrectionListResponse {
  case_id: string;
  total: number;
  corrections: ValueCorrection[];
}

// --------------------------------------------------------------------------
// Evidence requests — what the auditor still needs from the client
// --------------------------------------------------------------------------

export type EvidenceRequestStatus = "open" | "answered" | "resolved" | "cancelled";

export interface EvidenceRequest {
  request_id: string;
  case_id: string;
  review_item_id: string | null;
  title: string;
  detail: string | null;
  status: EvidenceRequestStatus;
  due_date: string | null;
  requested_by: string;
  requested_at: string;
  response_note: string | null;
  responded_by: string | null;
  responded_at: string | null;
  cancellation_note: string | null;
  closed_by: string | null;
  closed_at: string | null;
}

export interface CreateEvidenceRequestRequest {
  title: string;
  detail?: string | null;
  case_id?: string | null;
  review_item_id?: string | null;
  due_date?: string | null;
}

export interface EvidenceRequestResponse {
  request: EvidenceRequest;
  audit_record: AuditRecord;
}

export interface EvidenceRequestListResponse {
  case_id: string;
  total: number;
  /** Open or answered: the work still outstanding. */
  open_total: number;
  requests: EvidenceRequest[];
}

// --------------------------------------------------------------------------
// Sign-off (maker-checker)
// --------------------------------------------------------------------------

export interface SignOff {
  sign_off_id: string;
  case_id: string;
  signed_by: string;
  signed_at: string;
  note: string | null;
  item_count: number;
  approved_count: number;
  rejected_count: number;
}

export interface SignOffResponse {
  sign_off: SignOff;
  audit_record: AuditRecord;
}

export interface SignOffListResponse {
  case_id: string;
  total: number;
  sign_offs: SignOff[];
  /** Whether this case's client requires a signature before a report. */
  required: boolean;
  satisfied: boolean;
}

// --------------------------------------------------------------------------
// The firm's letterhead
// --------------------------------------------------------------------------

export interface OrgProfileResponse {
  org_id: string;
  name: string;
  legal_name: string | null;
  address: string | null;
  contact_email: string | null;
  phone: string | null;
  website: string | null;
  registration_number: string | null;
  logo: string | null;
  report_footer: string | null;
  updated_at: string | null;
}

/** PATCH /v1/organization — rename the workspace. */
export interface UpdateOrganizationRequest {
  name: string;
}

/** PUT /v1/org-profile — a full replacement; omitted fields are cleared. */
export interface UpdateOrgProfileRequest {
  legal_name?: string | null;
  address?: string | null;
  contact_email?: string | null;
  phone?: string | null;
  website?: string | null;
  registration_number?: string | null;
  logo?: string | null;
  report_footer?: string | null;
}

// --------------------------------------------------------------------------
// Insights and period comparison
//
// Counted across the firm's cases from the same deterministic results the
// dashboard shows. Nothing here is modelled, scored, or estimated.
// --------------------------------------------------------------------------

/**
 * One party and what the rules have said about it. Deliberately *not* a risk
 * score: Tarazu flags what needs review and never claims fraud detection.
 */
export interface VendorAttention {
  party_name: string;
  flag_count: number;
  high: number;
  medium: number;
  low: number;
  rules: string[];
  case_count: number;
  item_count: number;
  total_amount: string;
  currency: string;
}

export interface RuleFrequency {
  rule_id: string;
  count: number;
  severity: Severity;
  /** Of those, how many sit on an item somebody has already decided. */
  reviewed: number;
}

export interface MonthlyPoint {
  month: string; // YYYY-MM
  item_count: number;
  flag_count: number;
  total_amount: string;
  currency: string;
}

export interface InsightsResponse {
  case_count: number;
  client_count: number;
  total_review_items: number;
  pending_items: number;
  total_flags: number;
  unreviewed_flags: number;
  open_evidence_requests: number;
  estimated_hours_saved: number;
  vendors: VendorAttention[];
  rules: RuleFrequency[];
  months: MonthlyPoint[];
}

/** `GET /v1/business-summary` — the engagement as the audited owner sees it. */
export interface BusinessSummary {
  case_id: string;
  client_name: string;
  period_start: string | null;
  period_end: string | null;
  status: CaseStatus;
  total_review_items: number;
  matched: number;
  partial: number;
  unmatched: number;
  approved: number;
  rejected: number;
  pending: number;
  flag_count: number;
  high_severity: number;
  medium_severity: number;
  low_severity: number;
  total_amount: string;
  currency: string;
  owner_summary: string;
  urdu_summary: string | null;
  sign_off_required: boolean;
  sign_off_satisfied: boolean;
  latest_report: ReportSummary | null;
  generated_at: string | null;
}

export interface PeriodDelta {
  label: string;
  left: string;
  right: string;
  change: string;
  notable: boolean;
}

export interface CompareResponse {
  left: CaseSummary;
  right: CaseSummary;
  deltas: PeriodDelta[];
  new_parties: string[];
  dropped_parties: string[];
}

// --------------------------------------------------------------------------
// Sampling — substantive testing, reproducible from its seed
// --------------------------------------------------------------------------

export type SamplingMethod = "random" | "monetary_unit" | "high_value";

export interface SampleRequest {
  case_id?: string | null;
  method?: SamplingMethod;
  size?: number;
  /** Supply one to repeat an earlier draw exactly. */
  seed?: number | null;
}

export interface SampleItem {
  review_item_id: string;
  party_name: string;
  date: string;
  amount: string;
  currency: string;
  match_status: string;
  flag_count: number;
  reason: string;
}

export interface SampleResponse {
  case_id: string;
  method: SamplingMethod;
  seed: number;
  population_size: number;
  population_amount: string;
  sample_size: number;
  sample_amount: string;
  coverage_percent: number;
  items: SampleItem[];
  /** How the sample was drawn, in working-paper language. */
  method_note: string;
  audit_record: AuditRecord;
}
