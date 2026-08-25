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

from app.shared.schemas import (
    ApiKeyRecord,
    ApiKeyScope,
    AuditRecord,
    CaseStatus,
    DashboardSummary,
    DocumentType,
    OrgInvitation,
    OrgRole,
    ReviewItem,
    TarazuModel,
    UserProfile,
)

__all__ = [
    "ApiKeyListResponse",
    "ApiKeySummary",
    "ApproveRequest",
    "AuditTrailResponse",
    "CaseListResponse",
    "CaseSummary",
    "CreateApiKeyRequest",
    "CreatedApiKeyResponse",
    "DashboardResponse",
    "DecisionResponse",
    "DeletedApiKeyResponse",
    "ErrorResponse",
    "HealthResponse",
    "InvitationListResponse",
    "InvitationSummary",
    "InviteMemberRequest",
    "MemberSummary",
    "MembersResponse",
    "RejectRequest",
    "RenameApiKeyRequest",
    "ReviewItemsResponse",
    "UpdateProfileRequest",
    "UploadResponse",
    "UploadedDocument",
    "UserProfileResponse",
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


class UploadResponse(TarazuModel):
    """`POST /v1/upload`. The result of running a case through the pipeline."""

    case_id: str
    documents: list[UploadedDocument]
    status: CaseStatus
    review_item_count: int = Field(ge=0)
    #: Documents where the two extraction passes disagreed and a human must look.
    needs_human_review_count: int = Field(ge=0)
    message: str


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
