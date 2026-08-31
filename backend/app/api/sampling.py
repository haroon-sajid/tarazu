"""`/v1/sampling` — draw a defensible sample from a case's population.

Drawing a sample reads the case and decides nothing about it, so a `read`-scoped
key may do it: the auditor picking twenty items to test should not need a
credential that can approve them. What the sample changes is the record of what
was done — which is why every draw appends a `sample_drawn` entry naming the
method, the size, the seed, and the coverage.

**The seed is the point.** A sample nobody can reproduce is not audit evidence:
six months later somebody will ask how these twenty items were chosen, and
"randomly" is not an answer. Supply a seed to repeat an earlier draw exactly;
omit it and one is generated here and returned, so the answer exists from the
first draw onwards rather than having to be reconstructed.

The selection itself is `modules/sampling/`, which is pure deterministic Python
and never sees an AI client. This file resolves the case, records the draw, and
formats money for the wire.
"""

from __future__ import annotations

import secrets
from decimal import Decimal

from fastapi import APIRouter, Depends

from app.api.deps import (
    Principal,
    get_repository,
    require_read,
    resolve_case_id,
)
from app.core.audit import record_actor_action
from app.core.repository import CaseRepository
from app.modules.sampling import service as sampling
from app.shared.api import SampleItem, SampleRequest, SampleResponse
from app.shared.schemas import AuditAction

__all__ = ["router"]

router = APIRouter(tags=["sampling"])


def _money(value: Decimal) -> str:
    """Money on the wire, formatted exactly as the reports module formats it."""
    return f"{value:,.2f}"


@router.post(
    "/sampling",
    response_model=SampleResponse,
    summary="Draw a deterministic sample from a case's population",
)
async def draw_sample(
    body: SampleRequest | None = None,
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> SampleResponse:
    """Select items to test from the case's review queue, and record the draw.

    The population is the whole queue, decided items included: a sample is drawn
    to decide what to look at, and filtering it by what has already been looked
    at would bias it. The response carries the seed used — supplied or
    generated — the method note in working-paper language, and the trail entry
    proving who drew it and how.

    Nothing here approves, rejects, or otherwise touches a review item. A sample
    nominates work; the human still does it.
    """
    request = body or SampleRequest()
    case_id = resolve_case_id(repository, principal, request.case_id)
    population = repository.list_review_items(principal.org_id, case_id)

    # A draw with no seed still has a seed; it is chosen here and handed back so
    # the auditor can repeat this exact sample later. `secrets` rather than
    # `random`, so two draws a millisecond apart cannot collide on a clock-seeded
    # generator — the seed is an identifier of a draw, not part of the draw.
    seed = request.seed if request.seed is not None else secrets.randbelow(2**31)

    outcome = sampling.draw_sample(population, request.method, request.size, seed)

    record = record_actor_action(
        repository,
        principal.org_id,
        case_id,
        principal.actor,
        AuditAction.SAMPLE_DRAWN,
        detail=(
            f"{request.method.value} sample: {outcome.sample_size} of "
            f"{outcome.population_size} items, requested size {request.size}, "
            f"seed {seed}, covering {outcome.coverage_percent}% of the population's "
            f"value ({_money(outcome.sample_total)} of "
            f"{_money(outcome.population_total)})"
        ),
    )

    return SampleResponse(
        case_id=case_id,
        method=request.method,
        seed=seed,
        population_size=outcome.population_size,
        population_amount=_money(outcome.population_total),
        sample_size=outcome.sample_size,
        sample_amount=_money(outcome.sample_total),
        coverage_percent=outcome.coverage_percent,
        items=[
            SampleItem(
                review_item_id=selected.item.review_item_id,
                party_name=selected.item.ledger_entry.party_name,
                date=selected.item.ledger_entry.date,
                amount=_money(selected.item.ledger_entry.amount),
                currency=selected.item.ledger_entry.currency,
                match_status=selected.item.match.status.value,
                flag_count=len(selected.item.flags),
                reason=selected.reason,
            )
            for selected in outcome.selected
        ],
        method_note=outcome.method_note,
        audit_record=record,
    )
