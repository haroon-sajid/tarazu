"""`GET /v1/audit-trail` — one case's full immutable trail.

The trail is the product's spine: every action, by human, AI, or machine
credential, in order, forever. Until now it was only visible item by item;
this route serves the whole case so the frontend can render it as one
timeline.

This file only reads. The one writer is `app.core.audit.record_action`, and
nothing anywhere updates or deletes a record — the stores enforce append-only
underneath (a SQLite trigger locally, REVOKE + RLS on Postgres).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import Principal, get_case_id, get_repository, require_read
from app.core.repository import CaseRepository
from app.shared.api import AuditTrailResponse

__all__ = ["router"]

router = APIRouter(tags=["audit-trail"])


@router.get(
    "/audit-trail",
    response_model=AuditTrailResponse,
    summary="The case's full audit trail",
)
async def get_audit_trail(
    case_id: str = Depends(get_case_id),
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> AuditTrailResponse:
    """All recorded actions on the case, oldest first.

    `case_id` defaults to the caller's most recent case, exactly as on the
    dashboard. Another organization's case is `404` before this handler runs.
    """
    records = repository.list_audit(principal.org_id, case_id)
    return AuditTrailResponse(case_id=case_id, total=len(records), records=records)
