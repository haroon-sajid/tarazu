"""`GET /v1/dashboard` — the case summary shown on the dashboard screen.

Every number here is **counted** from persisted deterministic results. No figure
on this screen is produced or estimated by a model, and the Benford distribution
is arithmetic performed in `rules/`, not here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import Principal, get_case_id, get_repository, require_read
from app.core.repository import CaseRepository
from app.dashboard_metrics import audit_readiness, data_confidence, next_best_actions
from app.shared.api import DashboardResponse
from app.shared.schemas import (
    Confidence,
    ConfidenceBreakdown,
    DecisionBreakdown,
    MatchStatus,
    ReviewDecision,
    ReviewItem,
    Severity,
    SeverityBreakdown,
    StatusBreakdown,
)

__all__ = ["router"]

router = APIRouter(tags=["dashboard"])

#: Minutes of manual reconciliation one review item stands in for. Deliberately
#: conservative, and stated as an estimate wherever it is shown.
MINUTES_SAVED_PER_ITEM = 4


@router.get("/dashboard", response_model=DashboardResponse, summary="Case summary")
async def get_dashboard(
    case_id: str = Depends(get_case_id),
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> DashboardResponse:
    """Counts, flag severities, Benford, readiness, and what to do next.

    The route reads and hands off. Every derived figure is computed by
    `app.dashboard_metrics`, deterministically, from the persisted queue — the
    caller's organization's queue, and never a number counted over another's.
    """
    case = repository.get_case(principal.org_id, case_id)
    items = repository.list_review_items(principal.org_id, case_id)
    benford = repository.get_benford(principal.org_id, case_id)
    sales_analytics = repository.get_sales_analytics(principal.org_id, case_id)

    flags = [flag for item in items for flag in item.flags]
    period_start = _earliest(items) or (case.period_start if case else None)
    period_end = _latest(items) or (case.period_end if case else None)

    return DashboardResponse(
        case_id=case_id,
        client_name=case.client_name if case else "Unknown client",
        period_start=period_start,
        period_end=period_end,
        total_review_items=len(items),
        match_status=StatusBreakdown(
            matched=_count(items, lambda i: i.match.status is MatchStatus.MATCHED),
            partial=_count(items, lambda i: i.match.status is MatchStatus.PARTIAL),
            unmatched=_count(items, lambda i: i.match.status is MatchStatus.UNMATCHED),
        ),
        decisions=DecisionBreakdown(
            pending=_count(items, lambda i: i.decision is ReviewDecision.PENDING),
            approved=_count(items, lambda i: i.decision is ReviewDecision.APPROVED),
            rejected=_count(items, lambda i: i.decision is ReviewDecision.REJECTED),
        ),
        extraction_confidence=ConfidenceBreakdown(
            high=_count(items, lambda i: i.extraction_confidence is Confidence.HIGH),
            medium=_count(items, lambda i: i.extraction_confidence is Confidence.MEDIUM),
            low=_count(items, lambda i: i.extraction_confidence is Confidence.LOW),
        ),
        flagged_item_count=_count(items, lambda i: bool(i.flags)),
        total_flags=len(flags),
        flags_by_severity=SeverityBreakdown(
            high=sum(1 for flag in flags if flag.severity is Severity.HIGH),
            medium=sum(1 for flag in flags if flag.severity is Severity.MEDIUM),
            low=sum(1 for flag in flags if flag.severity is Severity.LOW),
        ),
        # Observed count and frequency, expected frequency, deviation per digit,
        # plus the chi-square statistic — everything the chart needs.
        benford=benford,
        audit_readiness_score=audit_readiness(items),
        data_confidence=data_confidence(items, period_start, period_end),
        next_best_actions=next_best_actions(items),
        estimated_hours_saved=round(len(items) * MINUTES_SAVED_PER_ITEM / 60, 1),
        sales_analytics=sales_analytics,
    )


def _count(items: list[ReviewItem], predicate) -> int:
    return sum(1 for item in items if predicate(item))


def _earliest(items: list[ReviewItem]):
    return min((item.ledger_entry.date for item in items), default=None)


def _latest(items: list[ReviewItem]):
    return max((item.ledger_entry.date for item in items), default=None)
