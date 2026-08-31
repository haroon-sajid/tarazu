"""`/v1/evidence-requests` — what the auditor still needs from the client.

An audit stalls on missing paper: the invoice behind an unmatched payment, the
explanation for a weekend entry, the contract a round number is supposed to sit
under. Asking the client for it is part of the engagement, so the ask is kept
here rather than in somebody's inbox — raised against the case, tied to the
review item that raised the question, and carried to a close through the same
immutable trail as every decision. A reviewer six months later can see what was
outstanding, what came back, and who was satisfied by it.

Nothing in this file decides anything (reliability rule 1). An evidence request
is a question. Answering one approves nothing, rejects nothing, and re-matches
nothing: the auditor still goes to `/v1/review-items` and says so themselves.
Nothing here computes either — no amount, count, or match is touched.

Every lookup is scoped to the caller's organization, and a request outside it is
`404` rather than `403`, for the reason set out at the top of `review.py`: a
`403` would confirm that some other firm holds an `EVR-…` by that id.

A closed request stays closed. Respond, resolve, and cancel all refuse a request
that is already resolved or cancelled (`409`) rather than reopening it, so the
sequence of events reads forwards and never backwards. The row carries only
where the ask got to; the history of how it got there is the audit trail, which
is append-only and is written before any of these routes returns.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    Principal,
    get_case_id,
    get_repository,
    require_read,
    require_write,
    resolve_case_id,
)
from app.core.audit import record_actor_action
from app.core.repository import CaseRepository
from app.shared.api import (
    CancelEvidenceRequestRequest,
    CreateEvidenceRequestRequest,
    EvidenceRequestListResponse,
    EvidenceRequestResponse,
    RespondEvidenceRequestRequest,
)
from app.shared.schemas import (
    AuditAction,
    EvidenceRequest,
    EvidenceRequestStatus,
)

__all__ = ["router"]

router = APIRouter(tags=["evidence-requests"])


def _load(
    repository: CaseRepository, org_id: str, request_id: str
) -> EvidenceRequest:
    """Fetch one request inside the caller's organization, or `404`.

    The store filters by `org_id`, so this code cannot tell "never existed" from
    "belongs to another firm" — and therefore cannot leak the difference.
    """
    request = repository.get_evidence_request(org_id, request_id)
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No evidence request with id {request_id!r}.",
        )
    return request


def _require_open(
    repository: CaseRepository, org_id: str, request_id: str
) -> EvidenceRequest:
    """The request, provided it is still live.

    Resolved and cancelled are both terminal. Reopening one would let the row
    contradict the trail that closed it, so a second close — or an answer that
    arrives after the auditor moved on — is a `409` and a new ask instead.
    """
    request = _load(repository, org_id, request_id)
    if request.status.is_closed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Evidence request {request_id} was already {request.status.value} "
                f"by {request.closed_by}. Closed requests are not reopened; raise a "
                "new request instead."
            ),
        )
    return request


def _checked_review_item(
    repository: CaseRepository, org_id: str, case_id: str, review_item_id: str | None
) -> str | None:
    """Validate the item a request is being hung off, if one was named.

    A request that points at an item from a different engagement would show up
    on the wrong case's screen and cite the wrong evidence, so the link is
    checked here rather than trusted: unknown inside this organization is `404`
    (identically to another firm's item), and known but belonging to another
    case is `422` — that one is a real mistake by the caller and saying so is
    not a disclosure, because they can already see both.
    """
    if review_item_id is None:
        return None
    item = repository.get_review_item(org_id, review_item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No review item with id {review_item_id!r}.",
        )
    if item.case_id != case_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Review item {review_item_id} belongs to case {item.case_id}, not "
                f"to {case_id}. An evidence request stays with the case that raised it."
            ),
        )
    return review_item_id


def _transition(
    repository: CaseRepository,
    principal: Principal,
    request: EvidenceRequest,
    updates: dict[str, Any],
    action: AuditAction,
    detail: str,
) -> EvidenceRequestResponse:
    """Persist one state change, then append the record of it.

    Re-validates through `EvidenceRequest` rather than mutating in place, the
    same way `review.py::_decide` does: the schema's own rule — an answered
    request records when it was answered, a closed one records when it was
    closed — is enforced on the way in as well as by the database on the way
    down. A transition that forgot a timestamp fails here, loudly, instead of
    reaching the store as a half-written state.

    The trail entry is written before the response is returned, and it names the
    request rather than the review item: `item_id` is the `EVR-…`, so
    `GET /v1/cases/{id}/audit` reads as the history of the ask itself.
    """
    payload = request.model_dump()
    payload.update(updates)
    changed = EvidenceRequest.model_validate(payload)
    repository.save_evidence_request(principal.org_id, changed)

    record = record_actor_action(
        repository,
        principal.org_id,
        changed.case_id,
        principal.actor,
        action,
        item_id=changed.request_id,
        detail=detail,
    )
    return EvidenceRequestResponse(request=changed, audit_record=record)


@router.get(
    "/evidence-requests",
    response_model=EvidenceRequestListResponse,
    summary="Everything still outstanding with the client on a case",
)
async def list_evidence_requests(
    case_id: str = Depends(get_case_id),
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> EvidenceRequestListResponse:
    """Every request raised on the case, newest first.

    `open_total` counts the requests that are open *or* answered — the work
    still outstanding. An answered request is not finished work: somebody sent
    something back, and an auditor has yet to look at it and say whether it
    settles the question. Counting it as closed would let a case look complete
    while an unread attachment was the only thing holding it up.
    """
    requests = repository.list_evidence_requests(principal.org_id, case_id)
    return EvidenceRequestListResponse(
        case_id=case_id,
        total=len(requests),
        open_total=sum(1 for request in requests if not request.status.is_closed),
        requests=requests,
    )


@router.post(
    "/evidence-requests",
    response_model=EvidenceRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ask the client for one missing document or explanation",
)
async def create_evidence_request(
    body: CreateEvidenceRequestRequest,
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
) -> EvidenceRequestResponse:
    """Raise one ask against a case, optionally against the item behind it.

    One request is one thing to chase, which is why the title is required and
    short: "the invoice for the 12 June payment", not a list. Several asks are
    several requests, so each can be answered and closed on its own and the
    outstanding count means something.

    `requested_by` is always a person — the signed-in auditor, or the auditor
    whose API key this is. An ask that belonged to nobody would give the client
    no one to reply to and the trail no one to name.
    """
    case_id = resolve_case_id(repository, principal, body.case_id)
    review_item_id = _checked_review_item(
        repository, principal.org_id, case_id, body.review_item_id
    )

    request = EvidenceRequest(
        request_id=f"EVR-{uuid4().hex[:10]}",
        case_id=case_id,
        review_item_id=review_item_id,
        title=body.title,
        detail=body.detail,
        status=EvidenceRequestStatus.OPEN,
        due_date=body.due_date,
        requested_by=principal.user_id,
        requested_at=datetime.now(timezone.utc),
    )
    repository.save_evidence_request(principal.org_id, request)

    about = f" about {review_item_id}" if review_item_id else ""
    due = f", due {request.due_date.isoformat()}" if request.due_date else ""
    record = record_actor_action(
        repository,
        principal.org_id,
        case_id,
        principal.actor,
        AuditAction.EVIDENCE_REQUESTED,
        item_id=request.request_id,
        detail=f"Asked the client for: {request.title}{about}{due}.",
    )
    return EvidenceRequestResponse(request=request, audit_record=record)


@router.post(
    "/evidence-requests/{request_id}/respond",
    response_model=EvidenceRequestResponse,
    summary="Record what the client sent back",
)
async def respond_to_evidence_request(
    request_id: str,
    body: RespondEvidenceRequestRequest,
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
) -> EvidenceRequestResponse:
    """Record an answer against the ask, and leave it outstanding.

    Answering is not settling: the request moves to `answered` and still counts
    towards `open_total` until an auditor resolves it. That gap is the point —
    it is where a human reads what arrived and decides whether it answers the
    question, which is reliability rule 1 applied to evidence rather than to
    items.

    The client has no login here, so `responded_by` is the auditor who wrote the
    answer down. The note is what came back, in their words; documents the
    client actually sends belong in `POST /v1/upload`, where they get extracted,
    matched, and given provenance like every other document.
    """
    request = _require_open(repository, principal.org_id, request_id)
    return _transition(
        repository,
        principal,
        request,
        {
            "status": EvidenceRequestStatus.ANSWERED,
            "response_note": body.response_note,
            "responded_by": principal.user_id,
            "responded_at": datetime.now(timezone.utc),
        },
        AuditAction.EVIDENCE_ANSWERED,
        detail=f"Response recorded: {body.response_note}",
    )


@router.post(
    "/evidence-requests/{request_id}/resolve",
    response_model=EvidenceRequestResponse,
    summary="Close a request the auditor is satisfied with",
)
async def resolve_evidence_request(
    request_id: str,
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
) -> EvidenceRequestResponse:
    """Mark the ask settled: a person read what came back and accepted it.

    Deliberately reachable from `open` as well as from `answered` — evidence
    often arrives outside the product (the client walks the invoice in) and the
    auditor should be able to say so without inventing a response first. What is
    not optional is the person: `closed_by` names whoever was satisfied, and the
    trail says when.
    """
    request = _require_open(repository, principal.org_id, request_id)
    now = datetime.now(timezone.utc)
    return _transition(
        repository,
        principal,
        request,
        {
            "status": EvidenceRequestStatus.RESOLVED,
            "closed_by": principal.user_id,
            "closed_at": now,
        },
        AuditAction.EVIDENCE_RESOLVED,
        detail=f"Resolved: {request.title}.",
    )


@router.post(
    "/evidence-requests/{request_id}/cancel",
    response_model=EvidenceRequestResponse,
    summary="Withdraw a request that is no longer needed",
)
async def cancel_evidence_request(
    request_id: str,
    body: CancelEvidenceRequestRequest = CancelEvidenceRequestRequest(),
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
) -> EvidenceRequestResponse:
    """Withdraw the ask without it having been answered.

    A request raised in error, or overtaken by something else, is cancelled
    rather than deleted: the client was asked, and that happened whether or not
    it should have. The row keeps `cancelled` and the trail records a distinct
    `evidence_cancelled` action. An optional note explains why.
    """
    request = _require_open(repository, principal.org_id, request_id)
    now = datetime.now(timezone.utc)
    note = body.note
    detail = f"Cancelled without a response: {request.title}."
    if note:
        detail += f" Note: {note}"
    return _transition(
        repository,
        principal,
        request,
        {
            "status": EvidenceRequestStatus.CANCELLED,
            "cancellation_note": note,
            "closed_by": principal.user_id,
            "closed_at": now,
        },
        AuditAction.EVIDENCE_CANCELLED,
        detail=detail,
    )
