"""`/v1/sign-offs` — a second person putting their name to a finished engagement.

The four-eyes principle. Whoever decided the items is not who signs the
engagement off, and with `require_sign_off` set on the client, a report cannot
be generated until somebody has.

**This only ever adds a gate.** Nothing in this file approves, rejects, or
changes a review item; a case with anything still pending cannot be signed off
at all. Reliability rule 1 is strengthened here, never relaxed — and because a
sign-off is somebody's signature, the table is append-only in both stores, like
reports and the trail.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    Principal,
    get_case_id,
    get_repository,
    human_only,
    require_read,
    resolve_case_id,
)
from app.core.audit import record_actor_action
from app.core.repository import CaseRepository
from app.shared.api import (
    CreateSignOffRequest,
    SignOffListResponse,
    SignOffResponse,
)
from app.shared.schemas import (
    AuditAction,
    CaseStatus,
    OrgRole,
    ReviewDecision,
    SignOff,
)

__all__ = ["router", "sign_off_state"]

router = APIRouter(tags=["sign-offs"])
logger = logging.getLogger(__name__)


def sign_off_state(
    repository: CaseRepository, org_id: str, case_id: str
) -> tuple[bool, bool]:
    """`(required, satisfied)` for one case.

    Required is the client's own setting — the firm decides which of its
    clients need a second signature, and a case with no client never does.
    Satisfied simply means at least one sign-off exists.

    Shared with `api/reports.py`, which refuses to generate a deliverable for a
    case that requires a signature and has not got one. Keeping the rule in one
    function is what stops the gate and the screen that reports it drifting.
    """
    case = repository.get_case(org_id, case_id)
    if case is None or not case.client_id:
        return False, bool(repository.list_sign_offs(org_id, case_id))
    client = repository.get_client(org_id, case.client_id)
    required = bool(client and client.rules.require_sign_off)
    return required, bool(repository.list_sign_offs(org_id, case_id))


@router.get(
    "/sign-offs",
    response_model=SignOffListResponse,
    summary="Sign-offs recorded on a case, and whether one is required",
)
async def list_sign_offs(
    case_id: str = Depends(get_case_id),
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> SignOffListResponse:
    records = repository.list_sign_offs(principal.org_id, case_id)
    required, satisfied = sign_off_state(repository, principal.org_id, case_id)
    return SignOffListResponse(
        case_id=case_id,
        total=len(records),
        sign_offs=records,
        required=required,
        satisfied=satisfied,
    )


@router.post(
    "/sign-offs",
    response_model=SignOffResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Sign a finished engagement off (never the person who decided it)",
)
async def create_sign_off(
    body: CreateSignOffRequest | None = None,
    principal: Principal = Depends(human_only),
    repository: CaseRepository = Depends(get_repository),
) -> SignOffResponse:
    """Record a second person's sign-off on the case.

    Three things are checked, and each of them is a refusal rather than a
    warning:

    1. **A person, not a key.** A credential that can sign work off turns the
       four-eyes principle into a configuration detail. `human_only` sees to it.
    2. **Nothing outstanding.** A case with pending items has not been reviewed
       yet, so there is nothing to put a name to.
    3. **Not your own work.** Somebody who decided any item on this case cannot
       sign it off — that is the whole point of the second pair of eyes.
    """
    case_id = resolve_case_id(repository, principal, body.case_id if body else None)

    if principal.role is OrgRole.VIEWER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A viewer cannot sign an engagement off.",
        )

    items = repository.list_review_items(principal.org_id, case_id)
    if not items:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This case has no review items to sign off.",
        )

    pending = [item for item in items if item.decision is ReviewDecision.PENDING]
    if pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{len(pending)} item(s) still await a decision. Every item must be "
                "approved or rejected before the engagement can be signed off."
            ),
        )

    deciders = {item.decided_by for item in items if item.decided_by}
    if principal.user_id in deciders:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You decided items on this case, so you cannot also sign it off. "
                "A sign-off is a second pair of eyes: ask a colleague who did not "
                "review these items to sign it."
            ),
        )

    approved = sum(1 for item in items if item.decision is ReviewDecision.APPROVED)
    rejected = sum(1 for item in items if item.decision is ReviewDecision.REJECTED)
    sign_off = SignOff(
        sign_off_id=f"SGN-{uuid4().hex[:10]}",
        case_id=case_id,
        signed_by=principal.user_id,
        signed_at=datetime.now(timezone.utc),
        note=body.note if body else None,
        item_count=len(items),
        approved_count=approved,
        rejected_count=rejected,
    )
    repository.save_sign_off(principal.org_id, sign_off)

    # The case has been reviewed end to end and signed. `reported` comes later,
    # when a report is generated; this is the state in between.
    case = repository.get_case(principal.org_id, case_id)
    if case is not None and case.status is not CaseStatus.REPORTED:
        repository.set_case_status(principal.org_id, case_id, CaseStatus.APPROVED)

    record = record_actor_action(
        repository,
        principal.org_id,
        case_id,
        principal.actor,
        AuditAction.CASE_SIGNED_OFF,
        item_id=sign_off.sign_off_id,
        detail=(
            f"{len(items)} items ({approved} approved, {rejected} rejected) signed off; "
            f"decided by {', '.join(sorted(deciders)) or 'nobody'}"
            + (f"; note: {sign_off.note}" if sign_off.note else "")
        ),
    )
    logger.info("Case %s signed off by %s", case_id, principal.user_id)
    return SignOffResponse(sign_off=sign_off, audit_record=record)
