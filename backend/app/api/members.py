"""`/v1/members` — who is inside the organization, and how new people join.

Joining works by invitation code: the owner cuts a single-use code here, hands
it over out-of-band, and the invitee presents it at `POST /v1/auth/signup` to
join this organization instead of founding a new one. No email is sent —
the code in the owner's hands *is* the invitation, which keeps the flow
honest about what the platform can verify (possession of the code, not
ownership of an inbox).

Boundaries:

1. **People only** (`human_only`). Machine credentials neither enumerate a
   firm's people nor mint access for new ones.
2. **Only the owner manages membership.** A member sees the member list —
   who else can touch the cases is legitimate to know — but inviting and
   revoking are `403` for anyone but the owner.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import Principal, get_repository, human_only
from app.core.repository import CaseRepository
from app.shared.api import (
    InvitationListResponse,
    InvitationSummary,
    InviteMemberRequest,
    MembersResponse,
    MemberSummary,
)
from app.shared.schemas import OrgInvitation, OrgRole

__all__ = ["router"]

router = APIRouter(tags=["members"])
logger = logging.getLogger(__name__)


def _owner_only(principal: Principal) -> None:
    if principal.role is not OrgRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the organization owner manages members and invitations.",
        )


def _email_of(repository: CaseRepository, user_id: str) -> str | None:
    """Resolve an email where the store can (local mode); None otherwise."""
    lookup = getattr(repository, "get_user_email", None)
    return lookup(user_id) if callable(lookup) else None


@router.get(
    "/members",
    response_model=MembersResponse,
    summary="Everyone with access to this organization",
)
async def list_members(
    principal: Principal = Depends(human_only),
    repository: CaseRepository = Depends(get_repository),
) -> MembersResponse:
    """The member list, visible to every member.

    Who else can see and decide the firm's cases is not a secret inside the
    firm — it is exactly what an auditor reviewing the audit trail needs.
    """
    members = [
        MemberSummary(
            user_id=member.user_id,
            email=_email_of(repository, member.user_id),
            role=member.role,
            created_at=member.created_at,
        )
        for member in repository.list_members(principal.org_id)
    ]
    return MembersResponse(total=len(members), members=members)


@router.post(
    "/members/invites",
    response_model=InvitationSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Invite someone into this organization",
)
async def create_invitation(
    body: InviteMemberRequest,
    principal: Principal = Depends(human_only),
    repository: CaseRepository = Depends(get_repository),
) -> InvitationSummary:
    """Cut a single-use join code for one person. Owner only.

    The response carries the code; handing it to the invitee is the owner's
    act, out-of-band. The invitee uses it at `POST /v1/auth/signup`.
    """
    _owner_only(principal)
    invitation = OrgInvitation(
        invite_id=f"INV-{uuid4().hex[:12]}",
        org_id=principal.org_id,
        email=body.email.strip(),
        role=body.role,
        # 8 hex characters after a recognisable prefix: enough entropy for a
        # single-use, revocable code that a person reads out over a call.
        code=f"TZ-{secrets.token_hex(4).upper()}",
        created_by=principal.user_id,
        created_at=datetime.now(timezone.utc),
    )
    repository.create_invitation(invitation)
    logger.info(
        "Invitation %s created for %s in org %s by %s",
        invitation.invite_id,
        invitation.email,
        invitation.org_id,
        invitation.created_by,
    )
    return InvitationSummary.of(invitation)


@router.get(
    "/members/invites",
    response_model=InvitationListResponse,
    summary="This organization's invitations",
)
async def list_invitations(
    principal: Principal = Depends(human_only),
    repository: CaseRepository = Depends(get_repository),
) -> InvitationListResponse:
    """Open and accepted invitations, newest first. Owner only — the list
    carries live join codes."""
    _owner_only(principal)
    invitations = [
        InvitationSummary.of(record)
        for record in repository.list_invitations(principal.org_id)
    ]
    return InvitationListResponse(total=len(invitations), invitations=invitations)


@router.delete(
    "/members/invites/{invite_id}",
    response_model=InvitationListResponse,
    summary="Revoke an invitation",
)
async def revoke_invitation(
    invite_id: str,
    principal: Principal = Depends(human_only),
    repository: CaseRepository = Depends(get_repository),
) -> InvitationListResponse:
    """Delete the invitation; its code stops admitting anyone immediately.

    Returns the remaining list, so the screen that shows invitations needs no
    second request. Another organization's invitation is `404`, as its cases
    are.
    """
    _owner_only(principal)
    deleted = repository.delete_invitation(principal.org_id, invite_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No invitation with id {invite_id!r}.",
        )
    logger.info("Invitation %s revoked by %s", invite_id, principal.user_id)
    invitations = [
        InvitationSummary.of(record)
        for record in repository.list_invitations(principal.org_id)
    ]
    return InvitationListResponse(total=len(invitations), invitations=invitations)
