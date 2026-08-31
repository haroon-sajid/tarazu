"""`/v1/org-profile` — the firm's own details, printed on its reports.

Presentation only. Nothing on this row is an authorization input, nothing here
changes a number, and the reports module reads it to put the firm's name and
logo on the deliverable it hands a client. A firm that fills nothing in gets
the organization's name and the plain layout, exactly as before.

Reading is open to any member; writing is an owner's act, because the letterhead
a client receives is the firm's identity rather than one auditor's preference.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import Principal, get_repository, human_only, require_read
from app.core.repository import CaseRepository
from app.shared.api import OrgProfileResponse, UpdateOrgProfileRequest
from app.shared.schemas import OrgProfile, OrgRole

__all__ = ["router"]

router = APIRouter(tags=["organization"])
logger = logging.getLogger(__name__)


def _name_of(repository: CaseRepository, org_id: str) -> str:
    organization = repository.get_organization(org_id)
    return organization.name if organization else "Your firm"


@router.get(
    "/org-profile",
    response_model=OrgProfileResponse,
    summary="The firm's branding, as printed on its reports",
)
async def get_org_profile(
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> OrgProfileResponse:
    record = repository.get_org_profile(principal.org_id)
    return OrgProfileResponse.of(
        principal.org_id, _name_of(repository, principal.org_id), record
    )


@router.put(
    "/org-profile",
    response_model=OrgProfileResponse,
    summary="Replace the firm's branding (owner only)",
)
async def update_org_profile(
    body: UpdateOrgProfileRequest,
    principal: Principal = Depends(human_only),
    repository: CaseRepository = Depends(get_repository),
) -> OrgProfileResponse:
    """Full replacement, like the user profile: send every field on each save.

    An owner's act. A member can read the letterhead their reports carry but
    cannot change what the firm presents to its clients, and a `viewer` — the
    audited business's own owner — cannot reach this route at all.
    """
    if principal.role is not OrgRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Only an owner can change the firm's report branding. "
                "Ask an owner of your organization to update it."
            ),
        )

    profile = OrgProfile(
        org_id=principal.org_id,
        legal_name=body.legal_name,
        address=body.address,
        contact_email=body.contact_email,
        phone=body.phone,
        website=body.website,
        registration_number=body.registration_number,
        logo=body.logo,
        report_footer=body.report_footer,
        updated_at=datetime.now(timezone.utc),
    )
    repository.save_org_profile(profile)
    logger.info("Org profile for %s updated by %s", principal.org_id, principal.user_id)
    return OrgProfileResponse.of(
        principal.org_id, _name_of(repository, principal.org_id), profile
    )
