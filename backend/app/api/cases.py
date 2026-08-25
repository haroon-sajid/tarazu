"""`GET /v1/cases` — the organization's engagements.

An audit firm runs many engagements at once; this is the screen that lists
them. Each row carries the case plus three working counts (items, pending,
flagged), all counted from persisted deterministic results — nothing here is
estimated.

The counts are computed with one queue read per case. At engagement scale
(tens of cases, not thousands) that is simpler and safer than a bespoke
aggregate query duplicated across two stores; revisit only if a real firm's
case list ever gets slow.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import Principal, get_repository, require_read
from app.core.repository import CaseRepository
from app.shared.api import CaseListResponse, CaseSummary
from app.shared.schemas import ReviewDecision

__all__ = ["router"]

router = APIRouter(tags=["cases"])


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
    summaries: list[CaseSummary] = []
    for case in repository.list_cases(principal.org_id):
        items = repository.list_review_items(principal.org_id, case.case_id)
        summaries.append(
            CaseSummary(
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
        )
    return CaseListResponse(total=len(summaries), cases=summaries)
