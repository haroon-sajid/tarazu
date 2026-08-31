"""The human review screen: list the queue, and record one human decision.

Reliability rule 1 lives here. There is no auto-approval path in this file and
there must never be one: every decision arrives as an explicit HTTP call from a
person clicking a button, carries their verified `user_id`, and appends a row to
the immutable audit trail before the response is returned.

Every lookup in this file is scoped to the caller's organization, and a review
item outside it is `404` rather than `403`. That is deliberate: a `403` would
confirm that a firm called Haroon Textiles has an item `RI-0007`, which is itself
a disclosure. From outside the organization, the item does not exist.

A decision may also arrive from an integration holding a `write`-scoped API key.
Rule 1 is not weakened by that and must not be: the key belongs to a named
auditor, the item records *them* as `decided_by`, and the audit trail records
plainly that the click came from `api-key:<prefix>` rather than from a person at
a screen. A firm that automates approvals can be seen to have done so.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    Principal,
    get_case_id,
    get_repository,
    require_read,
    require_write,
)
from app.core.audit import record_actor_action
from app.core.repository import CaseRepository
from app.shared.api import (
    ApproveRequest,
    CorrectionListResponse,
    CorrectionResponse,
    CreateCorrectionRequest,
    DecisionResponse,
    RejectRequest,
    ReviewItemsResponse,
)
from app.shared.schemas import (
    AuditAction,
    AuditRecord,
    CaseStatus,
    MatchStatus,
    OrgRole,
    ReviewDecision,
    ReviewItem,
    ValueCorrection,
)

router = APIRouter(tags=["review"])


def _deciding_principal(principal: Principal) -> Principal:
    """Refuse a read-only viewer. Rule 1 needs an accountable decider.

    `require_write` guards the credential's scope; this guards the seat. A
    `viewer` is the audited business's own owner (ADR 0005), invited to watch
    their engagement — they may read everything on it and change none of it.
    """
    if principal.role is OrgRole.VIEWER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Your role is read-only. Approving, rejecting, and correcting are "
                "the auditor's; ask the firm running this engagement."
            ),
        )
    return principal


@router.get(
    "/review-items",
    response_model=ReviewItemsResponse,
    summary="List every item awaiting or carrying a human decision",
)
async def list_review_items(
    case_id: str = Depends(get_case_id),
    decision: ReviewDecision | None = Query(default=None, description="Filter by decision"),
    match_status: MatchStatus | None = Query(default=None, description="Filter by match status"),
    flagged: bool | None = Query(default=None, description="Only items with, or without, flags"),
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> ReviewItemsResponse:
    """Return the review queue for a case, optionally filtered.

    Filtering happens here rather than in the browser so the review table stays
    fast on a real ledger, and so the counts the UI shows come from one place —
    which is also what makes this route useful to an integration polling for
    `?decision=pending&flagged=true`.
    """
    items = repository.list_review_items(principal.org_id, case_id)
    if decision is not None:
        items = [item for item in items if item.decision is decision]
    if match_status is not None:
        items = [item for item in items if item.match.status is match_status]
    if flagged is not None:
        items = [item for item in items if bool(item.flags) is flagged]

    case = repository.get_case(principal.org_id, case_id)
    return ReviewItemsResponse(
        case_id=case_id,
        case_status=case.status if case else CaseStatus.READY_FOR_REVIEW,
        total=len(items),
        items=items,
    )


def _require_undecided(
    repository: CaseRepository, org_id: str, review_item_id: str
) -> ReviewItem:
    item = repository.get_review_item(org_id, review_item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No review item with id {review_item_id!r}.",
        )
    if item.decision is not ReviewDecision.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Review item {review_item_id} was already {item.decision.value} by "
                f"{item.decided_by}. Decisions are not overwritten; reopen the item instead."
            ),
        )
    return item


def _decide(
    repository: CaseRepository,
    principal: Principal,
    item: ReviewItem,
    decision: ReviewDecision,
    rejection_reason: str | None,
    detail: str | None,
) -> DecisionResponse:
    """Persist one decision, then append its audit record.

    Re-validates through `ReviewItem` rather than mutating in place, so the
    decision invariants — who decided, when, and why — are enforced by the
    schema on the way in as well as by the database on the way down.

    `decided_by` is always a person: the signed-in auditor, or — when the call
    came from an integration — the auditor whose key it is. A decision that
    belonged to no one would satisfy the database and defeat the point of it.
    The audit record, written from `principal.actor`, is where the fact that a
    machine made the call is preserved.
    """
    payload = item.model_dump()
    payload.update(
        decision=decision,
        decided_by=principal.user_id,
        decided_at=datetime.now(timezone.utc),
        rejection_reason=rejection_reason,
    )
    decided = ReviewItem.model_validate(payload)
    repository.update_review_item(principal.org_id, decided)

    record: AuditRecord = record_actor_action(
        repository,
        principal.org_id,
        decided.case_id,
        principal.actor,
        AuditAction.ITEM_APPROVED
        if decision is ReviewDecision.APPROVED
        else AuditAction.ITEM_REJECTED,
        item_id=decided.review_item_id,
        detail=detail,
    )
    return DecisionResponse(review_item=decided, audit_record=record)


@router.post(
    "/review-items/{review_item_id}/approve",
    response_model=DecisionResponse,
    summary="Approve one item (never automatic)",
)
async def approve_review_item(
    review_item_id: str,
    body: ApproveRequest | None = None,
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
) -> DecisionResponse:
    item = _require_undecided(repository, principal.org_id, review_item_id)
    return _decide(
        repository, principal, item, ReviewDecision.APPROVED,
        rejection_reason=None, detail=(body.note if body else None),
    )


@router.post(
    "/review-items/{review_item_id}/reject",
    response_model=DecisionResponse,
    summary="Reject one item (reason required)",
)
async def reject_review_item(
    review_item_id: str,
    body: RejectRequest,
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
) -> DecisionResponse:
    item = _require_undecided(repository, principal.org_id, review_item_id)
    return _decide(
        repository, principal, item, ReviewDecision.REJECTED,
        rejection_reason=body.reason, detail=body.reason,
    )


@router.post(
    "/review-items/{review_item_id}/corrections",
    response_model=CorrectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record what a misread value actually is (both readings are kept)",
)
async def correct_value(
    review_item_id: str,
    body: CreateCorrectionRequest,
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
) -> CorrectionResponse:
    """Record a human's correction of a value the model misread.

    A real bank statement will produce a low-confidence reading sooner or
    later, and until now the only thing an auditor could do about it was reject
    the whole item. This records the narrower, truer fact: the model read
    `49,500`, the statement says `49,900`, and a named person says so at a
    named time.

    **Both readings survive.** The correction never overwrites the extraction:
    it sits beside it, travels into the report's provenance section, and lands
    in the append-only trail. That is evidence about the extraction, which is
    what Tarazu is for — and it is not bookkeeping, because the client's own
    books are not being written here (ADR 0004).

    **It does not re-run matching.** Changing a figure changes arithmetic, and
    arithmetic in this product is deterministic code run over a whole case
    (rule 2). Silently re-matching one row against a corrected amount would
    produce a queue that no single run ever computed. Re-processing stays an
    explicit act; this route records the finding that prompts it.
    """
    _deciding_principal(principal)
    item = repository.get_review_item(principal.org_id, review_item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No review item with id {review_item_id!r}.",
        )

    # The document must be one this firm holds, and one this case is actually
    # built from: a correction citing a document from another engagement would
    # put unverifiable provenance into the report.
    document = repository.get_document(principal.org_id, body.document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No document with id {body.document_id!r}.",
        )
    if document.case_id != item.case_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Document {body.document_id} belongs to case {document.case_id}, not "
                f"to {item.case_id}. A correction cites evidence from its own case."
            ),
        )

    try:
        correction = ValueCorrection(
            correction_id=f"COR-{uuid4().hex[:10]}",
            case_id=item.case_id,
            review_item_id=review_item_id,
            document_id=body.document_id,
            field=body.field,
            ai_value=body.ai_value,
            corrected_value=body.corrected_value,
            note=body.note,
            corrected_by=principal.user_id,
            corrected_at=datetime.now(timezone.utc),
        )
    except ValueError as error:
        # The schema refuses a "correction" that changes nothing.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error

    repository.save_correction(principal.org_id, correction)
    record = record_actor_action(
        repository,
        principal.org_id,
        item.case_id,
        principal.actor,
        AuditAction.VALUE_CORRECTED,
        item_id=review_item_id,
        detail=(
            f"{body.field} on {body.document_id}: model read "
            f"{body.ai_value if body.ai_value is not None else '(nothing)'!r}, "
            f"corrected to {body.corrected_value!r}"
            + (f" — {body.note}" if body.note else "")
        ),
    )
    return CorrectionResponse(correction=correction, audit_record=record)


@router.get(
    "/corrections",
    response_model=CorrectionListResponse,
    summary="Every correction recorded on a case",
)
async def list_corrections(
    case_id: str = Depends(get_case_id),
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> CorrectionListResponse:
    """Oldest first, so the case's corrections read as a sequence of events."""
    corrections = repository.list_corrections(principal.org_id, case_id)
    return CorrectionListResponse(
        case_id=case_id, total=len(corrections), corrections=corrections
    )


@router.get(
    "/review-items/{review_item_id}/audit",
    response_model=list[AuditRecord],
    summary="The audit trail for one item",
)
async def item_audit_trail(
    review_item_id: str,
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> list[AuditRecord]:
    """Every recorded action on one item, oldest first.

    Read-only by construction: the trail has no update or delete route, and the
    database refuses both regardless. The item is looked up inside the caller's
    organization first, so this cannot become a way to read another firm's trail
    by guessing an item id.
    """
    item = repository.get_review_item(principal.org_id, review_item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No review item with id {review_item_id!r}.",
        )
    return repository.list_audit(principal.org_id, item.case_id, item_id=review_item_id)
