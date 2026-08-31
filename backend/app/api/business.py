"""`/v1/business-summary` — the owner-facing view of one engagement.

The dashboard is built for the auditor. This screen is built for the audited
business's owner: the counts are the same, but the language is plain, the
emphasis is on what was decided and what still needs attention, and the
Urdu executive summary appears here when the client reads Urdu.

Like every other read, it is scoped to the caller's organization. A viewer
(invited by the firm to watch their own engagement) sees the same numbers an
owner or member sees on this screen; nothing here is role-gated.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import Principal, get_case_id, get_repository, require_read
from app.api.sign_offs import sign_off_state
from app.core.repository import CaseRepository
from app.modules.reports.urdu import urdu_executive_summary
from app.shared.api import BusinessSummaryResponse, ReportSummary
from app.shared.schemas import (
    AssistantLanguage,
    CaseRecord,
    MatchStatus,
    ReviewDecision,
    ReviewItem,
)

__all__ = ["router"]

router = APIRouter(tags=["business"])


def _money(amount: Decimal, currency: str) -> str:
    """Group and fix to two places, with the currency code."""
    return f"{currency} {amount:,.2f}"


def _dominant_currency(items: Iterable[ReviewItem], default: str = "PKR") -> str:
    """The currency most of these ledger rows are in."""
    counts = Counter(item.ledger_entry.currency for item in items)
    if not counts:
        return default
    return min(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]


def _total_in(items: Iterable[ReviewItem], currency: str) -> Decimal:
    """Sum the amounts in one currency, leaving the rest out."""
    return sum(
        (
            item.ledger_entry.amount
            for item in items
            if item.ledger_entry.currency == currency
        ),
        Decimal("0"),
    )


def _owner_summary(
    *,
    client_name: str,
    period_start: str | None,
    period_end: str | None,
    item_count: int,
    matched: int,
    partial: int,
    unmatched: int,
    approved: int,
    rejected: int,
    pending: int,
    flag_count: int,
    high_severity: int,
    total_amount: str,
    sign_off_required: bool,
    sign_off_satisfied: bool,
) -> str:
    """Plain-English paragraph for the business owner, composed from counts.

    No AI import: every word is deterministic, so the text can never disagree
    with the tables on the same screen.
    """
    parts: list[str] = []
    period = (
        f" for the period {period_start} to {period_end}"
        if period_start and period_end
        else ""
    )
    parts.append(
        f"{client_name}{period}: {item_count} ledger entries were reviewed."
    )
    parts.append(
        f"{matched} matched fully, {partial} matched partially, and {unmatched} "
        f"had no matching bank or invoice entry."
    )
    if item_count:
        parts.append(f"The total ledger value reviewed was {total_amount}.")
    if flag_count:
        parts.append(
            f"{flag_count} items were flagged for attention"
            + (f" ({high_severity} high severity)" if high_severity else "")
            + "."
        )
    else:
        parts.append("No rules flagged any entries for attention.")

    parts.append(
        f"The auditor approved {approved} entries, rejected {rejected}, and "
        f"{pending} still await a decision."
    )

    if sign_off_required:
        parts.append(
            "A second-person sign-off is required before the report is final"
            + (" and has been recorded." if sign_off_satisfied else " and is still pending.")
        )

    parts.append(
        "Every figure was produced by deterministic code from the uploaded documents, "
        "and every decision is recorded against a named person."
    )
    return " ".join(parts)


def _period(case: CaseRecord, items: list[ReviewItem]) -> tuple[str | None, str | None]:
    """The period to show, from the case record or from the ledger dates."""
    if case.period_start and case.period_end:
        return case.period_start.isoformat(), case.period_end.isoformat()
    dates = [item.ledger_entry.date for item in items]
    if not dates:
        return None, None
    return min(dates).isoformat(), max(dates).isoformat()


@router.get(
    "/business-summary",
    response_model=BusinessSummaryResponse,
    summary="Owner-facing summary of the active engagement",
)
async def business_summary(
    case_id: str = Depends(get_case_id),
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> BusinessSummaryResponse:
    """The engagement as the audited business owner sees it.

    Returns the same counts the dashboard shows, but with a plain-language
    summary and the Urdu executive summary when the client record says the
    owner reads Urdu. The latest report and its downloads are included if one
    has been generated.
    """
    case = repository.get_case(principal.org_id, case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No case with id {case_id!r}.",
        )

    items = repository.list_review_items(principal.org_id, case_id)
    client = (
        repository.get_client(principal.org_id, case.client_id)
        if case.client_id
        else None
    )

    period_start, period_end = _period(case, items)

    by_status = {"matched": 0, "partial": 0, "unmatched": 0}
    for item in items:
        by_status[item.match.status.value] += 1

    by_decision = {
        "approved": 0,
        "rejected": 0,
        "pending": 0,
    }
    for item in items:
        by_decision[item.decision.value] += 1

    by_severity = {"high": 0, "medium": 0, "low": 0}
    for item in items:
        for flag in item.flags:
            by_severity[flag.severity.value] += 1
    flag_count = sum(by_severity.values())

    currency = client.currency if client else _dominant_currency(items)
    total = _total_in(items, currency)

    sign_off_required, sign_off_satisfied = sign_off_state(
        repository, principal.org_id, case_id
    )

    owner_summary = _owner_summary(
        client_name=case.client_name,
        period_start=period_start,
        period_end=period_end,
        item_count=len(items),
        matched=by_status["matched"],
        partial=by_status["partial"],
        unmatched=by_status["unmatched"],
        approved=by_decision["approved"],
        rejected=by_decision["rejected"],
        pending=by_decision["pending"],
        flag_count=flag_count,
        high_severity=by_severity["high"],
        total_amount=_money(total, currency),
        sign_off_required=sign_off_required,
        sign_off_satisfied=sign_off_satisfied,
    )

    urdu_summary = None
    if client and client.language is AssistantLanguage.URDU:
        urdu_summary = urdu_executive_summary(
            client_name=case.client_name,
            period_start=period_start,
            period_end=period_end,
            item_count=len(items),
            matched=by_status["matched"],
            partial=by_status["partial"],
            unmatched=by_status["unmatched"],
            approved=by_decision["approved"],
            rejected=by_decision["rejected"],
            pending=by_decision["pending"],
            flag_count=flag_count,
            high_severity=by_severity["high"],
            total_amount=total,
            currency=currency,
        )

    reports = repository.list_reports(principal.org_id, case_id)
    latest_report = ReportSummary.of(reports[0]) if reports else None

    return BusinessSummaryResponse(
        case_id=case_id,
        client_name=case.client_name,
        period_start=period_start,
        period_end=period_end,
        status=case.status,
        total_review_items=len(items),
        matched=by_status["matched"],
        partial=by_status["partial"],
        unmatched=by_status["unmatched"],
        approved=by_decision["approved"],
        rejected=by_decision["rejected"],
        pending=by_decision["pending"],
        flag_count=flag_count,
        high_severity=by_severity["high"],
        medium_severity=by_severity["medium"],
        low_severity=by_severity["low"],
        total_amount=_money(total, currency),
        currency=currency,
        owner_summary=owner_summary,
        urdu_summary=urdu_summary,
        sign_off_required=sign_off_required,
        sign_off_satisfied=sign_off_satisfied,
        latest_report=latest_report,
        generated_at=latest_report.generated_at if latest_report else None,
    )
