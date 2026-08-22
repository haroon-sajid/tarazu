"""Tarazu — AI Audit Assistant: the public HTTP request and response envelopes.

`schemas.py` holds the domain contracts that cross module boundaries. This file
holds the thin envelopes wrapping them for the `/v1/...` API, so that the
frontend has one typed shape per endpoint. It contains no logic — only shapes.

The endpoints these envelopes serve are documented, with example payloads, in
[docs/api-contracts.md](../../../docs/api-contracts.md). Change one and change
the other in the same commit.
"""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from datetime import datetime

from app.shared.schemas import (
    ApiKeyRecord,
    ApiKeyScope,
    AuditRecord,
    CaseStatus,
    DashboardSummary,
    DocumentType,
    ReviewItem,
    TarazuModel,
)

__all__ = [
    "ApiKeyListResponse",
    "ApiKeySummary",
    "ApproveRequest",
    "CreateApiKeyRequest",
    "CreatedApiKeyResponse",
    "DashboardResponse",
    "DecisionResponse",
    "ErrorResponse",
    "HealthResponse",
    "RejectRequest",
    "ReviewItemsResponse",
    "UploadResponse",
    "UploadedDocument",
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
        "Save this key now — it is shown once and cannot be retrieved again. "
        "Store it in your integration's secret store, never in source control."
    )


class ApiKeyListResponse(TarazuModel):
    """`GET /v1/api-keys`. The organization's keys, revoked ones included."""

    total: int = Field(ge=0)
    keys: list[ApiKeySummary]
