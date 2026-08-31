"""`/v1/cases` — the organization's engagements.

An audit firm runs many engagements at once; this is the screen that lists
them. Each row carries the case plus three working counts (items, pending,
flagged), all counted from persisted deterministic results — nothing here is
estimated.

The counts are computed with one queue read per case. At engagement scale
(tens of cases, not thousands) that is simpler and safer than a bespoke
aggregate query duplicated across two stores; revisit only if a real firm's
case list ever gets slow.

Two verbs beyond the list. `PATCH` corrects a case's editable facts — the
client name and the period — and `DELETE` removes the engagement together
with its working data. Both are scoped like every other route: another firm's
case is a `404`, indistinguishable from one that never existed. Both land in
the audit trail too, which is append-only and outlives the case it describes,
so "who renamed this, who removed that" stays answerable after the fact.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import Principal, get_repository, require_read, require_write
from app.core.audit import record_actor_action
from app.core.repository import CaseRepository
from app.shared.api import (
    CaseListResponse,
    CaseSummary,
    DeletedCaseResponse,
    UpdateCaseRequest,
)
from app.shared.schemas import AuditAction, CaseRecord, ReviewDecision

__all__ = ["router"]

router = APIRouter(tags=["cases"])
logger = logging.getLogger(__name__)


def _summary(repository: CaseRepository, org_id: str, case: CaseRecord) -> CaseSummary:
    """One list row: the case plus its counts, read from the persisted queue."""
    items = repository.list_review_items(org_id, case.case_id)
    return CaseSummary(
        case_id=case.case_id,
        client_name=case.client_name,
        period_start=case.period_start,
        period_end=case.period_end,
        status=case.status,
        status_detail=case.status_detail,
        created_by=case.created_by,
        created_at=case.created_at,
        total_review_items=len(items),
        pending_items=sum(
            1 for item in items if item.decision is ReviewDecision.PENDING
        ),
        flagged_items=sum(1 for item in items if item.flags),
    )


@router.get(
    "/cases",
    response_model=CaseListResponse,
    summary="List this organization's cases",
)
async def list_cases(
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> CaseListResponse:
    """Every case in the caller's organization, most recent first.

    Scoped like everything else: another firm's cases are not filtered out of
    this list — they were never in the query.
    """
    summaries = [
        _summary(repository, principal.org_id, case)
        for case in repository.list_cases(principal.org_id)
    ]
    return CaseListResponse(total=len(summaries), cases=summaries)


@router.patch(
    "/cases/{case_id}",
    response_model=CaseSummary,
    summary="Rename a case or correct its period",
)
async def update_case(
    case_id: str,
    body: UpdateCaseRequest,
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
) -> CaseSummary:
    """Correct the engagement's editable facts: the client name, the period.

    A field the request leaves out keeps its current value; `null` for a period
    clears it. The status, creator, and timestamps are facts about the case's
    life, not settings — they move only when the pipeline moves them.

    The change is recorded in the case's trail, naming exactly what changed. An
    empty body is not an error; it changes nothing and records nothing, because
    there is nothing worth remembering in it.
    """
    case = repository.get_case(principal.org_id, case_id)
    if case is None:
        # Another organization's case is a 404, exactly as on every read.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No case with id {case_id!r}.",
        )

    provided = body.model_fields_set
    client_name = case.client_name
    if "client_name" in provided:
        if not body.client_name or not body.client_name.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The case needs a client name.",
            )
        client_name = body.client_name.strip()
    period_start = body.period_start if "period_start" in provided else case.period_start
    period_end = body.period_end if "period_end" in provided else case.period_end
    if period_start and period_end and period_start > period_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The period cannot end before it starts.",
        )

    updated = repository.update_case(
        principal.org_id,
        case_id,
        client_name=client_name,
        period_start=period_start,
        period_end=period_end,
    )
    if updated is None:  # pragma: no cover - the read above just found it
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No case with id {case_id!r}.",
        )

    changes: list[str] = []
    if client_name != case.client_name:
        changes.append(f"client renamed from {case.client_name!r} to {client_name!r}")
    if period_start != case.period_start:
        changes.append(
            f"period start set to {period_start.isoformat()}"
            if period_start
            else "period start cleared"
        )
    if period_end != case.period_end:
        changes.append(
            f"period end set to {period_end.isoformat()}" if period_end else "period end cleared"
        )
    if changes:
        record_actor_action(
            repository,
            principal.org_id,
            case_id,
            principal.actor,
            AuditAction.CASE_UPDATED,
            detail="; ".join(changes),
        )
    logger.info(
        "Case %s updated by %s: %s",
        case_id,
        principal.user_id,
        "; ".join(changes) or "nothing changed",
    )
    return _summary(repository, principal.org_id, updated)


@router.delete(
    "/cases/{case_id}",
    response_model=DeletedCaseResponse,
    summary="Delete a case and its working data",
)
async def delete_case(
    case_id: str,
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
) -> DeletedCaseResponse:
    """Remove the engagement: its documents, extractions, review queue, flags,
    and Benford result. Permanent, and effective immediately.

    What deletion deliberately does not touch is the evidence. Generated
    reports and the audit trail are append-only in both stores, so they outlive
    the case — and the trail's own record of this deletion is the last entry
    naming it. The counts in that record are read before the rows go, which is
    what keeps the trail self-describing once the case it describes no longer
    exists.
    """
    case = repository.get_case(principal.org_id, case_id)
    if case is None:
        # Another organization's case is a 404, exactly as on every read.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No case with id {case_id!r}.",
        )
    item_count = len(repository.list_review_items(principal.org_id, case_id))
    document_count = len(repository.list_documents(principal.org_id, case_id))

    deleted = repository.delete_case(principal.org_id, case_id)
    if not deleted:  # pragma: no cover - the read above just found it
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No case with id {case_id!r}.",
        )

    # Appended after the delete, into a trail with no dependency on the case
    # row: the record of a deletion must survive the deletion it records.
    record_actor_action(
        repository,
        principal.org_id,
        case_id,
        principal.actor,
        AuditAction.CASE_DELETED,
        detail=(
            f"{case.client_name!r} deleted with {item_count} review items and "
            f"{document_count} documents. Reports and this trail outlive the case."
        ),
    )
    logger.info(
        "Case %s (%s) deleted by %s", case_id, case.client_name, principal.user_id
    )
    return DeletedCaseResponse(case_id=case_id)
