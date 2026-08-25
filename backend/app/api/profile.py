"""`/v1/profile` — the signed-in person's editable profile.

A profile is presentation: a display name, a picture, contact details. It is
deliberately powerless — nothing in it feeds authentication, tenancy, or the
audit trail, which names users by id. That is why the contract is simple and
why `PUT` replaces the whole thing: there is no partial-update ceremony worth
having over four cosmetic fields.

Two boundaries are enforced here:

1. **People only.** Both routes depend on `human_only`. A machine credential
   has no face and no phone number, and must not be able to redecorate the
   identity of the person accountable for it.
2. **The avatar is an inline image, capped.** A `data:image/...` URL of at
   most ~300 KB decoded, validated at the schema. Profiles stay rows, not a
   file store.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.deps import Principal, get_repository, human_only
from app.core.repository import CaseRepository
from app.shared.api import UpdateProfileRequest, UserProfileResponse
from app.shared.schemas import UserProfile

router = APIRouter(tags=["profile"])
logger = logging.getLogger(__name__)


@router.get(
    "/profile",
    response_model=UserProfileResponse,
    summary="The signed-in person's profile",
)
async def get_profile(
    principal: Principal = Depends(human_only),
    repository: CaseRepository = Depends(get_repository),
) -> UserProfileResponse:
    """The caller's own profile, and only theirs.

    There is no `{user_id}` in the path on purpose: a profile is reachable
    only by the person it belongs to. Someone who never saved one gets a
    profile made of Nones, not a 404 — an empty profile is a normal state,
    not an error.
    """
    record = repository.get_user_profile(principal.user_id)
    if record is None:
        return UserProfileResponse(user_id=principal.user_id)
    return UserProfileResponse.of(record)


@router.put(
    "/profile",
    response_model=UserProfileResponse,
    summary="Replace the signed-in person's profile",
)
async def update_profile(
    body: UpdateProfileRequest,
    principal: Principal = Depends(human_only),
    repository: CaseRepository = Depends(get_repository),
) -> UserProfileResponse:
    """Full replacement: every editable field becomes what the request says.

    An omitted or blank field is cleared, not kept — the frontend always
    sends the complete form, and the stores stay a single upsert.
    """
    record = UserProfile(
        user_id=principal.user_id,
        full_name=body.full_name,
        job_title=body.job_title,
        phone=body.phone,
        avatar=body.avatar,
        gender=body.gender,
        date_of_birth=body.date_of_birth,
        location=body.location,
        license_number=body.license_number,
        language=body.language,
        notify_case_ready=body.notify_case_ready,
        notify_high_severity=body.notify_high_severity,
        notify_weekly_digest=body.notify_weekly_digest,
        updated_at=datetime.now(timezone.utc),
    )
    repository.save_user_profile(record)
    # Names and phone numbers are personal data: log the event, not the values.
    logger.info(
        "Profile updated by %s (avatar: %s)",
        principal.user_id,
        "set" if record.avatar else "none",
    )
    return UserProfileResponse.of(record)
