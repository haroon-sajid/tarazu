"""Tarazu — AI Audit Assistant: the public HTTP request and response envelopes.

`schemas.py` holds the domain contracts that cross module boundaries. This file
holds the thin envelopes wrapping them for the `/v1/...` API, so that the
frontend has one typed shape per endpoint. It contains no logic — only shapes.

The endpoints these envelopes serve are documented, with example payloads, in
[docs/api-contracts.md](../../../docs/api-contracts.md). Change one and change
the other in the same commit.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from datetime import date, datetime

from enum import Enum

from app.shared.schemas import (
    ApiKeyRecord,
    ApiKeyScope,
    AssistantAnswer,
    AssistantLanguage,
    AuditRecord,
    CaseStatus,
    Client,
    ClientRuleConfig,
    DashboardSummary,
    DocumentType,
    EvidenceRequest,
    EvidenceRequestStatus,
    JobRecord,
    JobStatus,
    OrgInvitation,
    OrgProfile,
    OrgRole,
    ReportRecord,
    ReviewItem,
    SalesDataUpload,
    Severity,
    SignOff,
    TarazuModel,
    UserProfile,
    ValueCorrection,
)

__all__ = [
    "ApiKeyListResponse",
    "ApiKeySummary",
    "ApproveRequest",
    "BusinessSummaryResponse",
    "ClientDetailResponse",
    "ClientListResponse",
    "ClientSummary",
    "CompareResponse",
    "CorrectionListResponse",
    "CorrectionResponse",
    "CreateClientRequest",
    "CreateCorrectionRequest",
    "CreateEvidenceRequestRequest",
    "CreateSignOffRequest",
    "EvidenceRequestListResponse",
    "EvidenceRequestResponse",
    "InsightsResponse",
    "JobResponse",
    "JobSummary",
    "MonthlyPoint",
    "OrgProfileResponse",
    "PeriodComparison",
    "PeriodDelta",
    "RespondEvidenceRequestRequest",
    "RuleFrequency",
    "SampleItem",
    "SampleRequest",
    "SampleResponse",
    "SamplingMethod",
    "SignOffListResponse",
    "SignOffResponse",
    "UpdateClientRequest",
    "UpdateOrgProfileRequest",
    "VendorAttention",
    "AssistantChatRequest",
    "AssistantChatResponse",
    "AuditTrailResponse",
    "CaseListResponse",
    "CaseSummary",
    "CreateApiKeyRequest",
    "CreatedApiKeyResponse",
    "DashboardResponse",
    "DecisionResponse",
    "DeletedApiKeyResponse",
    "DeletedCaseResponse",
    "DocumentListResponse",
    "DocumentSummary",
    "ErrorResponse",
    "GenerateReportRequest",
    "HealthResponse",
    "InvitationListResponse",
    "InvitationSummary",
    "InviteMemberRequest",
    "MemberSummary",
    "MembersResponse",
    "RejectRequest",
    "RenameApiKeyRequest",
    "ReportDownloads",
    "ReportListResponse",
    "ReportSummary",
    "ReviewItemsResponse",
    "UpdateCaseRequest",
    "UpdateProfileRequest",
    "UploadResponse",
    "UploadedDocument",
    "UserProfileResponse",
    "SalesDataUploadResponse",
    "SalesDataUploadListResponse",
]


class HealthResponse(TarazuModel):
    """`GET /health`. The only unauthenticated route."""

    status: Literal["ok"] = "ok"
    service: str = "tarazu-backend"
    version: str


class ErrorResponse(TarazuModel):
    """FastAPI's error shape, declared so it appears in the OpenAPI schema."""

    detail: str


class UploadedDocument(TarazuModel):
    document_id: str
    document_type: DocumentType
    filename: str
    size_bytes: int = Field(ge=0)
    storage_path: str


class SalesDataUploadResponse(TarazuModel):
    """`POST /v1/cases/{case_id}/sales-data` and `GET` responses."""

    sales_data_id: str
    case_id: str
    filename: str
    size_bytes: int = Field(ge=0)
    uploaded_by: str
    uploaded_at: datetime


class SalesDataUploadListResponse(TarazuModel):
    """`GET /v1/cases/{case_id}/sales-data`."""

    uploads: list[SalesDataUploadResponse]


class UploadResponse(TarazuModel):
    """`POST /v1/upload`. The result of running a case through the pipeline.

    Two shapes, one model. Synchronously (`?background=false`) the pipeline has
    finished by the time this returns and the counts are final. In background
    mode — the default, because extraction over a real statement takes tens of
    seconds — the case is created, the job is queued, `job_id` names it, and
    the counts are zero until `GET /v1/jobs/{job_id}` reports `succeeded`.
    """

    case_id: str
    documents: list[UploadedDocument]
    status: CaseStatus
    review_item_count: int = Field(ge=0)
    #: Documents where the two extraction passes disagreed and a human must look.
    needs_human_review_count: int = Field(ge=0)
    message: str
    #: Present when the work was queued. Poll `GET /v1/jobs/{job_id}`.
    job_id: str | None = None


class ReviewItemsResponse(TarazuModel):
    """`GET /v1/review-items`. The whole review queue for a case."""

    case_id: str
    case_status: CaseStatus = CaseStatus.READY_FOR_REVIEW
    total: int = Field(ge=0)
    items: list[ReviewItem]


class ApproveRequest(TarazuModel):
    """`POST /v1/review-items/{id}/approve`. A note is optional."""

    note: str | None = None


class RejectRequest(TarazuModel):
    """`POST /v1/review-items/{id}/reject`. A reason is mandatory.

    Rejecting without saying why would leave a hole in the audit trail, so the
    reason is required by the contract rather than by the UI.
    """

    reason: str = Field(min_length=1)


class DecisionResponse(TarazuModel):
    """The result of an approve or reject: the updated item and its trail entry."""

    review_item: ReviewItem
    audit_record: AuditRecord


class DashboardResponse(DashboardSummary):
    """`GET /v1/dashboard`. The dashboard summary, unwrapped."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# API keys
#
# Note which shape carries the raw key: exactly one, returned by exactly one
# call. `ApiKeySummary` has no field for a secret, so no listing route can grow
# one by accident, and neither shape has a `key_hash`.
# --------------------------------------------------------------------------- #


class CreateApiKeyRequest(TarazuModel):
    """`POST /v1/api-keys`. A label, and what the key may do."""

    #: What this key is for, so it can be recognised months later and revoked
    #: with confidence. "n8n integration", "Zapier — monthly export".
    name: str = Field(min_length=1, max_length=100)
    #: Defaults to read-only. A key that can approve should have to say so.
    scopes: list[ApiKeyScope] = Field(default_factory=lambda: [ApiKeyScope.READ], min_length=1)


class ApiKeySummary(TarazuModel):
    """One key, as anybody is ever allowed to read it back.

    No `key_hash` and no `api_key`. Everything here is safe to render in a UI
    and safe to log.
    """

    key_id: str
    name: str
    #: `trz_live_` plus the key's first eight random characters. The same string
    #: that appears in the audit trail as `api-key:<prefix>`.
    key_prefix: str
    scopes: list[ApiKeyScope]
    created_by: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    #: Convenience for the UI, so it does not have to reason about a timestamp.
    revoked: bool = False

    @classmethod
    def of(cls, record: ApiKeyRecord) -> "ApiKeySummary":
        """Narrow a stored record to what may be shown. The hash is dropped here."""
        return cls(
            key_id=record.key_id,
            name=record.name,
            key_prefix=record.key_prefix,
            scopes=record.scopes,
            created_by=record.created_by,
            created_at=record.created_at,
            last_used_at=record.last_used_at,
            revoked_at=record.revoked_at,
            revoked=record.revoked_at is not None,
        )


class CreatedApiKeyResponse(TarazuModel):
    """`POST /v1/api-keys`. **The only response that ever carries the raw key.**

    It is not stored anywhere, so this response is the one and only chance to
    copy it. Losing it means creating a new key, which is the correct outcome:
    a system that can show you the key again is a system that kept it.
    """

    api_key: str
    key: ApiKeySummary
    message: str = (
        "Save this key now: it is shown once and cannot be retrieved again. "
        "Store it in your integration's secret store, never in source control."
    )


class ApiKeyListResponse(TarazuModel):
    """`GET /v1/api-keys`. The organization's keys, revoked ones included."""

    total: int = Field(ge=0)
    keys: list[ApiKeySummary]


class MemberSummary(TarazuModel):
    """One person with access to the organization.

    `email` is present where the identity store can resolve it (the local
    store); Supabase identities live in GoTrue, resolve to ids only from
    here, and the UI falls back to the id.
    """

    user_id: str
    email: str | None = None
    role: OrgRole
    created_at: datetime


class MembersResponse(TarazuModel):
    """`GET /v1/members`. Everyone who can see this organization's cases."""

    total: int = Field(ge=0)
    members: list[MemberSummary]


class InviteMemberRequest(TarazuModel):
    """`POST /v1/members/invites`. Who it is for, and what they may do."""

    email: str = Field(min_length=3, max_length=200)
    role: OrgRole = OrgRole.MEMBER


class InvitationSummary(TarazuModel):
    """An invitation as the owner sees it — code included, because the owner
    is the one who has to hand it to the invitee."""

    invite_id: str
    email: str
    role: OrgRole
    code: str
    created_by: str
    created_at: datetime
    accepted_at: datetime | None = None
    accepted_by: str | None = None
    accepted: bool = False

    @classmethod
    def of(cls, record: OrgInvitation) -> "InvitationSummary":
        return cls(
            invite_id=record.invite_id,
            email=record.email,
            role=record.role,
            code=record.code,
            created_by=record.created_by,
            created_at=record.created_at,
            accepted_at=record.accepted_at,
            accepted_by=record.accepted_by,
            accepted=record.accepted_at is not None,
        )


class InvitationListResponse(TarazuModel):
    """`GET /v1/members/invites`. Open and accepted invitations, newest first."""

    total: int = Field(ge=0)
    invitations: list[InvitationSummary]


class CaseSummary(TarazuModel):
    """One row of `GET /v1/cases`: the engagement plus its working counts."""

    case_id: str
    client_name: str
    #: The recurring client this period belongs to (ADR 0005), if any.
    client_id: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    status: CaseStatus
    status_detail: str | None = None
    created_by: str
    created_at: datetime
    total_review_items: int = Field(ge=0)
    pending_items: int = Field(ge=0)
    flagged_items: int = Field(ge=0)


class CaseListResponse(TarazuModel):
    """`GET /v1/cases`. The organization's engagements, newest first."""

    total: int = Field(ge=0)
    cases: list[CaseSummary]


class UpdateCaseRequest(TarazuModel):
    """`PATCH /v1/cases/{case_id}`. The engagement's editable facts.

    PATCH semantics: a field the request leaves out keeps its current value;
    sending `null` for a period, or for `client_id`, clears it. The client name
    cannot be cleared — an engagement is always about somebody — and the
    status, creator, and timestamps are facts about the case's life rather than
    settings, so they are not on this model at all.
    """

    client_name: str | None = Field(default=None, min_length=1, max_length=200)
    #: Attach this period to a recurring client, or detach it with `null`.
    client_id: str | None = None
    period_start: date | None = None
    period_end: date | None = None


class DeletedCaseResponse(TarazuModel):
    """`DELETE /v1/cases/{case_id}`. The engagement's working data is gone.

    Documents, extractions, the review queue, flags, and the Benford result
    went with it. Generated reports and the audit trail are append-only
    evidence and outlive the case — the trail's own record of this deletion is
    the last word on it.
    """

    case_id: str
    deleted: bool = True


class AuditTrailResponse(TarazuModel):
    """`GET /v1/audit-trail`. One case's full immutable trail, oldest first."""

    case_id: str
    total: int = Field(ge=0)
    records: list[AuditRecord]


MAX_AVATAR_CHARS = 400_000  # ~300 KB of image once base64-decoded


class UpdateProfileRequest(TarazuModel):
    """`PUT /v1/profile`. Full replacement of the editable profile fields.

    Send every field on each save — an omitted field is cleared, not kept.
    That keeps the contract PUT-shaped and the stores trivial. The avatar is a
    `data:image/...` URL so the picture needs no file storage; the size cap
    keeps a profile row a profile row, not a document store.
    """

    full_name: str | None = Field(default=None, max_length=100)
    job_title: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=40)
    avatar: str | None = Field(default=None, max_length=MAX_AVATAR_CHARS)
    gender: str | None = Field(default=None, max_length=20)
    date_of_birth: date | None = None
    location: str | None = Field(default=None, max_length=100)
    license_number: str | None = Field(default=None, max_length=60)
    language: str | None = Field(default=None, max_length=5)
    notify_case_ready: bool = True
    notify_high_severity: bool = True
    notify_weekly_digest: bool = False

    @field_validator(
        "full_name", "job_title", "phone", "avatar", "gender", "location",
        "license_number", "language",
    )
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("language")
    @classmethod
    def _language_is_supported(cls, value: str | None) -> str | None:
        if value is not None and value not in ("en", "ur"):
            raise ValueError('language must be "en" or "ur"')
        return value

    @field_validator("avatar")
    @classmethod
    def _avatar_is_an_inline_image(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.match(r"^data:image/(png|jpeg|jpg|webp);base64,", value):
            raise ValueError(
                "avatar must be a data:image/(png|jpeg|webp);base64 URL"
            )
        return value


class UserProfileResponse(TarazuModel):
    """`GET /v1/profile` and the `PUT` response. Everything is optional —
    a person who never filled their profile has one made of Nones."""

    user_id: str
    full_name: str | None = None
    job_title: str | None = None
    phone: str | None = None
    avatar: str | None = None
    gender: str | None = None
    date_of_birth: date | None = None
    location: str | None = None
    license_number: str | None = None
    language: str | None = None
    notify_case_ready: bool = True
    notify_high_severity: bool = True
    notify_weekly_digest: bool = False

    @classmethod
    def of(cls, record: UserProfile) -> "UserProfileResponse":
        return cls(
            user_id=record.user_id,
            full_name=record.full_name,
            job_title=record.job_title,
            phone=record.phone,
            avatar=record.avatar,
            gender=record.gender,
            date_of_birth=record.date_of_birth,
            location=record.location,
            license_number=record.license_number,
            language=record.language,
            notify_case_ready=record.notify_case_ready,
            notify_high_severity=record.notify_high_severity,
            notify_weekly_digest=record.notify_weekly_digest,
        )


class RenameApiKeyRequest(TarazuModel):
    """`PATCH /v1/api-keys/{key_id}`. The one thing about a key that can change.

    Scopes are fixed for a key's lifetime, and everything else on the row is a
    fact about its creation. Only the label is a setting.
    """

    name: str = Field(min_length=1, max_length=100)


class DeletedApiKeyResponse(TarazuModel):
    """`DELETE /v1/api-keys/{key_id}/record`. The row is gone for good.

    Works on an active key too — deletion stops it immediately, because
    authentication finds keys by hash and the hash goes with the row. The
    audit trail keeps its `api-key:<prefix>` entries, but after this they no
    longer resolve to a name or a creator — the trade the deleting person
    confirmed.
    """

    key_id: str
    deleted: bool = True


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #


class GenerateReportRequest(TarazuModel):
    """`POST /v1/reports`. Which case; defaults to the caller's most recent.

    Both formats are always produced together — one generation, one record,
    two files — so there is no format to choose here. Pick one at download.
    """

    case_id: str | None = None


class ReportDownloads(TarazuModel):
    """Relative URLs for the two files, so the UI never has to build them."""

    pdf: str
    excel: str


class ReportSummary(TarazuModel):
    """One report as the history screen lists it, and as `POST` returns it."""

    report_id: str
    case_id: str
    generated_by: str
    generated_at: datetime
    item_count: int = Field(ge=0)
    approved_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    flag_count: int = Field(ge=0)
    audit_record_count: int = Field(ge=0)
    pdf_sha256: str
    excel_sha256: str
    downloads: ReportDownloads

    @classmethod
    def of(cls, record: ReportRecord) -> "ReportSummary":
        base = f"/v1/reports/{record.report_id}/download"
        return cls(
            report_id=record.report_id,
            case_id=record.case_id,
            generated_by=record.generated_by,
            generated_at=record.generated_at,
            item_count=record.item_count,
            approved_count=record.approved_count,
            rejected_count=record.rejected_count,
            pending_count=record.pending_count,
            flag_count=record.flag_count,
            audit_record_count=record.audit_record_count,
            pdf_sha256=record.pdf_sha256,
            excel_sha256=record.excel_sha256,
            downloads=ReportDownloads(pdf=f"{base}?format=pdf", excel=f"{base}?format=excel"),
        )


class ReportListResponse(TarazuModel):
    """`GET /v1/reports`. Every report ever generated for the case, newest first."""

    case_id: str
    total: int = Field(ge=0)
    reports: list[ReportSummary]


# --------------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------------- #


class DocumentSummary(TarazuModel):
    """`GET /v1/documents` — one uploaded file and how to view it.

    `page_count` is what extraction saw; it is `null` for the ledger, which
    has rows rather than pages and is never rendered as an image.
    """

    document_id: str
    document_type: DocumentType
    filename: str
    size_bytes: int = Field(ge=0)
    page_count: int | None = Field(default=None, ge=1)
    needs_human_review: bool = False
    #: Relative URL of the original bytes.
    file_url: str
    #: Relative URL template for a rendered page; `{page}` is 1-based.
    page_url_template: str | None = None


class DocumentListResponse(TarazuModel):
    case_id: str
    total: int = Field(ge=0)
    documents: list[DocumentSummary]


# --------------------------------------------------------------------------- #
# The assistant
# --------------------------------------------------------------------------- #


class AssistantChatRequest(TarazuModel):
    """`POST /v1/assistant/chat`. One question about one case."""

    question: str = Field(min_length=1, max_length=2000)
    case_id: str | None = None
    #: Force the answer language. Detected from the question when omitted.
    language: AssistantLanguage | None = None

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be blank")
        return stripped


class AssistantChatResponse(TarazuModel):
    """The answer, and the trail entry that records it was given."""

    case_id: str
    answer: AssistantAnswer
    audit_record: AuditRecord


# --------------------------------------------------------------------------- #
# Clients and periods (ADR 0005)
# --------------------------------------------------------------------------- #


class CreateClientRequest(TarazuModel):
    """`POST /v1/clients`. A recurring client of the firm."""

    name: str = Field(min_length=1, max_length=200)
    reference: str | None = Field(default=None, max_length=60)
    #: The client's own rule thresholds. Omitted means the module defaults.
    rules: ClientRuleConfig | None = None
    currency: str = Field(default="PKR", pattern=r"^[A-Z]{3}$")
    language: AssistantLanguage = AssistantLanguage.ENGLISH
    relationship_owner: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


class UpdateClientRequest(TarazuModel):
    """`PATCH /v1/clients/{client_id}`. Only what the request names changes."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    reference: str | None = Field(default=None, max_length=60)
    rules: ClientRuleConfig | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    language: AssistantLanguage | None = None
    relationship_owner: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ClientSummary(TarazuModel):
    """One row of `GET /v1/clients`: the client and what its history amounts to.

    Every count is read off persisted periods and their queues — the same
    numbers the case list shows, grouped by client rather than estimated.
    """

    client_id: str
    name: str
    reference: str | None = None
    rules: ClientRuleConfig
    currency: str
    language: AssistantLanguage
    relationship_owner: str | None = None
    notes: str | None = None
    created_by: str
    created_at: datetime
    archived_at: datetime | None = None
    archived: bool = False
    #: How many periods have been run for this client.
    period_count: int = Field(default=0, ge=0)
    #: Items still awaiting a decision, across every period.
    pending_items: int = Field(default=0, ge=0)
    open_evidence_requests: int = Field(default=0, ge=0)
    #: The end of the most recent period, so the list can be read as a history.
    last_period_end: date | None = None
    last_activity_at: datetime | None = None

    @classmethod
    def of(cls, record: Client, **counts) -> "ClientSummary":
        return cls(
            client_id=record.client_id,
            name=record.name,
            reference=record.reference,
            rules=record.rules,
            currency=record.currency,
            language=record.language,
            relationship_owner=record.relationship_owner,
            notes=record.notes,
            created_by=record.created_by,
            created_at=record.created_at,
            archived_at=record.archived_at,
            archived=record.archived_at is not None,
            **counts,
        )


class ClientListResponse(TarazuModel):
    """`GET /v1/clients`. The firm's clients, newest first."""

    total: int = Field(ge=0)
    clients: list[ClientSummary]


class ClientDetailResponse(TarazuModel):
    """`GET /v1/clients/{client_id}`. The client and every period run for it."""

    client: ClientSummary
    periods: list[CaseSummary]


# --------------------------------------------------------------------------- #
# Background jobs
# --------------------------------------------------------------------------- #


class JobSummary(TarazuModel):
    """One unit of background work and how far it has got."""

    job_id: str
    case_id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    step: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    #: True once the job has stopped, whether it worked or not.
    finished: bool = False

    @classmethod
    def of(cls, record: JobRecord) -> "JobSummary":
        return cls(
            job_id=record.job_id,
            case_id=record.case_id,
            status=record.status,
            progress=record.progress,
            step=record.step,
            created_at=record.created_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            error=record.error,
            finished=record.status.is_terminal,
        )


class JobResponse(JobSummary):
    """`GET /v1/jobs/{job_id}`. What the upload screen polls."""


class JobListResponse(TarazuModel):
    total: int = Field(ge=0)
    jobs: list[JobSummary]


# --------------------------------------------------------------------------- #
# Value corrections
# --------------------------------------------------------------------------- #


class CreateCorrectionRequest(TarazuModel):
    """`POST /v1/review-items/{id}/corrections`. What the value really is.

    Both readings survive: `ai_value` is what the model read (omit it when it
    read nothing), `corrected_value` is what the auditor says it is. Recording
    a correction does not re-run matching — see `ValueCorrection`.
    """

    document_id: str = Field(min_length=1)
    field: str = Field(min_length=1, max_length=80)
    ai_value: str | None = Field(default=None, max_length=500)
    corrected_value: str = Field(min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=1000)


class CorrectionResponse(TarazuModel):
    """The recorded correction and the trail entry that keeps it."""

    correction: ValueCorrection
    audit_record: AuditRecord


class CorrectionListResponse(TarazuModel):
    case_id: str
    total: int = Field(ge=0)
    corrections: list[ValueCorrection]


# --------------------------------------------------------------------------- #
# Evidence requests
# --------------------------------------------------------------------------- #


class CreateEvidenceRequestRequest(TarazuModel):
    """`POST /v1/evidence-requests`. One thing to ask the client for."""

    title: str = Field(min_length=1, max_length=200)
    detail: str | None = Field(default=None, max_length=2000)
    case_id: str | None = None
    #: The review item that raised the question, when there is one.
    review_item_id: str | None = None
    due_date: date | None = None


class RespondEvidenceRequestRequest(TarazuModel):
    """`POST /v1/evidence-requests/{id}/respond`. The client's answer."""

    response_note: str = Field(min_length=1, max_length=2000)


class CancelEvidenceRequestRequest(TarazuModel):
    """`POST /v1/evidence-requests/{id}/cancel`. Withdraw the ask."""

    note: str | None = Field(default=None, max_length=2000)


class EvidenceRequestResponse(TarazuModel):
    """One request after a change, with the trail entry recording it."""

    request: EvidenceRequest
    audit_record: AuditRecord


class EvidenceRequestListResponse(TarazuModel):
    case_id: str
    total: int = Field(ge=0)
    #: Still open or answered — the work outstanding.
    open_total: int = Field(ge=0)
    requests: list[EvidenceRequest]


# --------------------------------------------------------------------------- #
# Sign-off (maker-checker)
# --------------------------------------------------------------------------- #


class CreateSignOffRequest(TarazuModel):
    """`POST /v1/sign-offs`. A second person signing the engagement off."""

    case_id: str | None = None
    note: str | None = Field(default=None, max_length=1000)


class SignOffResponse(TarazuModel):
    sign_off: SignOff
    audit_record: AuditRecord


class SignOffListResponse(TarazuModel):
    case_id: str
    total: int = Field(ge=0)
    sign_offs: list[SignOff]
    #: Whether this case's client requires a sign-off before a report.
    required: bool = False
    #: Whether that requirement is currently met.
    satisfied: bool = False


# --------------------------------------------------------------------------- #
# Organization profile (report branding)
# --------------------------------------------------------------------------- #

MAX_LOGO_CHARS = 400_000  # ~300 KB of image once base64-decoded


class UpdateOrgProfileRequest(TarazuModel):
    """`PUT /v1/org-profile`. Full replacement, like the user profile.

    Send every field on each save — an omitted field is cleared, not kept.
    """

    legal_name: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=400)
    contact_email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    website: str | None = Field(default=None, max_length=200)
    registration_number: str | None = Field(default=None, max_length=80)
    logo: str | None = Field(default=None, max_length=MAX_LOGO_CHARS)
    report_footer: str | None = Field(default=None, max_length=300)

    @field_validator(
        "legal_name", "address", "contact_email", "phone", "website",
        "registration_number", "report_footer",
    )
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("logo")
    @classmethod
    def _logo_is_an_inline_image(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.match(r"^data:image/(png|jpeg|jpg|webp);base64,", value):
            raise ValueError("logo must be a data:image/(png|jpeg|webp);base64 URL")
        return value


class OrgProfileResponse(TarazuModel):
    """`GET /v1/org-profile`. The firm's branding, printed on its reports."""

    org_id: str
    #: The organization's name from the tenancy row, so the UI always has one.
    name: str
    legal_name: str | None = None
    address: str | None = None
    contact_email: str | None = None
    phone: str | None = None
    website: str | None = None
    registration_number: str | None = None
    logo: str | None = None
    report_footer: str | None = None
    updated_at: datetime | None = None

    @classmethod
    def of(cls, org_id: str, name: str, record: OrgProfile | None) -> "OrgProfileResponse":
        if record is None:
            return cls(org_id=org_id, name=name)
        return cls(
            org_id=org_id,
            name=name,
            legal_name=record.legal_name,
            address=record.address,
            contact_email=record.contact_email,
            phone=record.phone,
            website=record.website,
            registration_number=record.registration_number,
            logo=record.logo,
            report_footer=record.report_footer,
            updated_at=record.updated_at,
        )


# --------------------------------------------------------------------------- #
# Insights and period comparison
#
# Everything here is counted from persisted deterministic results across the
# firm's cases. No model is involved and nothing is estimated — these are the
# same numbers the dashboard shows, grouped differently.
# --------------------------------------------------------------------------- #


class VendorAttention(TarazuModel):
    """One party, and how often the rules have had something to say about it.

    Deliberately *not* a "risk score": Tarazu flags what needs review and never
    claims to detect fraud. This counts flags and names the rules that fired.
    """

    party_name: str
    flag_count: int = Field(ge=0)
    high: int = Field(ge=0)
    medium: int = Field(ge=0)
    low: int = Field(ge=0)
    #: Which rules fired on this party, most frequent first.
    rules: list[str] = Field(default_factory=list)
    #: How many distinct cases the party appears in.
    case_count: int = Field(ge=0)
    item_count: int = Field(ge=0)
    total_amount: str
    currency: str = "PKR"


class RuleFrequency(TarazuModel):
    """How often one rule fired across the firm's work."""

    rule_id: str
    count: int = Field(ge=0)
    severity: Severity
    #: Of those, how many sit on an item somebody has already decided.
    reviewed: int = Field(ge=0)


class MonthlyPoint(TarazuModel):
    """One month of activity, for the trend chart."""

    #: `YYYY-MM`.
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    item_count: int = Field(ge=0)
    flag_count: int = Field(ge=0)
    total_amount: str
    currency: str = "PKR"


class InsightsResponse(TarazuModel):
    """`GET /v1/insights`. The firm across all of its cases."""

    case_count: int = Field(ge=0)
    client_count: int = Field(ge=0)
    total_review_items: int = Field(ge=0)
    pending_items: int = Field(ge=0)
    total_flags: int = Field(ge=0)
    #: Flags sitting on an item nobody has decided yet.
    unreviewed_flags: int = Field(ge=0)
    open_evidence_requests: int = Field(ge=0)
    estimated_hours_saved: float = Field(ge=0.0)
    vendors: list[VendorAttention] = Field(default_factory=list)
    rules: list[RuleFrequency] = Field(default_factory=list)
    months: list[MonthlyPoint] = Field(default_factory=list)


class BusinessSummaryResponse(TarazuModel):
    """`GET /v1/business-summary`. The engagement as the business owner sees it."""

    case_id: str
    client_name: str
    period_start: str | None = None
    period_end: str | None = None
    status: CaseStatus
    total_review_items: int = Field(ge=0)
    matched: int = Field(ge=0)
    partial: int = Field(ge=0)
    unmatched: int = Field(ge=0)
    approved: int = Field(ge=0)
    rejected: int = Field(ge=0)
    pending: int = Field(ge=0)
    flag_count: int = Field(ge=0)
    high_severity: int = Field(ge=0)
    medium_severity: int = Field(ge=0)
    low_severity: int = Field(ge=0)
    total_amount: str
    currency: str
    owner_summary: str
    urdu_summary: str | None = None
    sign_off_required: bool = False
    sign_off_satisfied: bool = False
    latest_report: ReportSummary | None = None
    generated_at: datetime | None = None


class PeriodDelta(TarazuModel):
    """One measure, in both periods, and the movement between them."""

    label: str
    left: str
    right: str
    #: `+3`, `-12.5%`, or "" where a difference is not meaningful.
    change: str = ""
    #: True when the movement is worth the reader's attention.
    notable: bool = False


class PeriodComparison(TarazuModel):
    """Two periods side by side, which is how auditors actually read them."""

    left: CaseSummary
    right: CaseSummary
    deltas: list[PeriodDelta]
    #: Parties in one period and not the other, both ways round.
    new_parties: list[str] = Field(default_factory=list)
    dropped_parties: list[str] = Field(default_factory=list)


class CompareResponse(PeriodComparison):
    """`GET /v1/compare?left=…&right=…`."""


# --------------------------------------------------------------------------- #
# Sampling
#
# Classic substantive testing: draw a defensible subset of the population and
# say exactly how it was drawn. Deterministic — the same seed gives the same
# sample — because a sample nobody can reproduce is not audit evidence.
# --------------------------------------------------------------------------- #


class SamplingMethod(str, Enum):
    #: Every item equally likely. The seed makes it reproducible.
    RANDOM = "random"
    #: Monetary-unit sampling: probability proportional to amount, so large
    #: items are near-certain to be picked. The standard substantive method.
    MONETARY_UNIT = "monetary_unit"
    #: The largest amounts, in order. Not a statistical sample; say so.
    HIGH_VALUE = "high_value"


class SampleRequest(TarazuModel):
    """`POST /v1/sampling`. Draw a sample from one case's population."""

    case_id: str | None = None
    method: SamplingMethod = SamplingMethod.MONETARY_UNIT
    size: int = Field(default=10, ge=1, le=500)
    #: Reproducibility. Omitted means one is generated and returned.
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class SampleItem(TarazuModel):
    review_item_id: str
    party_name: str
    date: date
    amount: str
    currency: str = "PKR"
    match_status: str
    flag_count: int = Field(ge=0)
    #: Why this item is in the sample, in one line.
    reason: str


class SampleResponse(TarazuModel):
    """A drawn sample, and everything needed to defend or reproduce it."""

    case_id: str
    method: SamplingMethod
    seed: int
    population_size: int = Field(ge=0)
    population_amount: str
    sample_size: int = Field(ge=0)
    sample_amount: str
    #: What share of the population's money the sample covers.
    coverage_percent: float = Field(ge=0.0, le=100.0)
    items: list[SampleItem]
    #: How the sample was drawn, in the words that belong in a working paper.
    method_note: str
    audit_record: AuditRecord
