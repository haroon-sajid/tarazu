"""`/v1/api-keys` — an organization's machine credentials.

This is how a firm connects Tarazu to n8n, Zapier, or its own software without
handing a person's password to a workflow builder. A key belongs to one
organization, carries only the scopes it was given, and reaches exactly the data
its creator could reach and nothing else.

Three things this file is careful about:

1. **The raw key is returned once, by `POST`, and never again.** It is not
   stored, so there is nothing to return later. The listing route serves
   `ApiKeySummary`, which has no field for a secret.
2. **Keys cannot manage keys.** Every route here depends on `human_only`. A
   credential that can mint credentials makes one leak permanent and puts
   revocation in the attacker's hands.
3. **Revoking does not delete.** `DELETE` stamps `revoked_at` and keeps the row,
   so the audit trail's `api-key:<prefix>` entries stay resolvable to a name, a
   creator, and a date long after the integration is gone.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import Principal, get_repository, human_only
from app.core.api_keys import mint_api_key
from app.core.repository import CaseRepository
from app.shared.api import (
    ApiKeyListResponse,
    ApiKeySummary,
    CreateApiKeyRequest,
    CreatedApiKeyResponse,
)
from app.shared.schemas import ApiKeyRecord

router = APIRouter(tags=["api-keys"])
logger = logging.getLogger(__name__)


@router.post(
    "/api-keys",
    response_model=CreatedApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an API key (returns the key once)",
)
async def create_api_key(
    body: CreateApiKeyRequest,
    principal: Principal = Depends(human_only),
    repository: CaseRepository = Depends(get_repository),
) -> CreatedApiKeyResponse:
    """Mint a key for the caller's organization.

    The response carries the only copy of the key that will ever leave this
    process. What is persisted is its prefix and a SHA-256 digest — enough to
    recognise the key when it comes back, and not enough to reproduce it.
    """
    minted = mint_api_key()
    record = ApiKeyRecord(
        key_id=f"AK-{uuid4().hex[:12]}",
        org_id=principal.org_id,
        created_by=principal.user_id,
        name=body.name.strip(),
        key_prefix=minted.prefix,
        key_hash=minted.key_hash,
        scopes=body.scopes,
        created_at=datetime.now(timezone.utc),
    )
    repository.create_api_key(record)

    # The prefix is safe to log and is what the audit trail will show. The key
    # itself is not logged here or anywhere else.
    logger.info(
        "API key %s (%s) created for org %s by %s with scopes %s",
        record.key_prefix,
        record.name,
        record.org_id,
        record.created_by,
        [scope.value for scope in record.scopes],
    )
    return CreatedApiKeyResponse(api_key=minted.raw, key=ApiKeySummary.of(record))


@router.get(
    "/api-keys",
    response_model=ApiKeyListResponse,
    summary="List this organization's API keys",
)
async def list_api_keys(
    principal: Principal = Depends(human_only),
    repository: CaseRepository = Depends(get_repository),
) -> ApiKeyListResponse:
    """Name, prefix, scopes, last use, and revocation status. Never a secret.

    Revoked keys are listed too. "Which integrations have we had, and when did
    we turn this one off" is the question this screen exists to answer, and
    hiding revoked keys would take the answer away.
    """
    keys = [ApiKeySummary.of(record) for record in repository.list_api_keys(principal.org_id)]
    return ApiKeyListResponse(total=len(keys), keys=keys)


@router.delete(
    "/api-keys/{key_id}",
    response_model=ApiKeySummary,
    summary="Revoke an API key",
)
async def revoke_api_key(
    key_id: str,
    principal: Principal = Depends(human_only),
    repository: CaseRepository = Depends(get_repository),
) -> ApiKeySummary:
    """Stop the key working, immediately and permanently.

    The row survives; only `revoked_at` changes. There is no un-revoke: a key
    that has been off is a key that may have been off *because it leaked*, and
    turning it back on would be the wrong tool for "I was too hasty". Create a
    new one.

    Revoking twice is not an error — the second call returns the same summary
    with the original `revoked_at`. Someone revoking a key in a hurry should not
    have to interpret a `409`.
    """
    revoked = repository.revoke_api_key(
        principal.org_id, key_id, datetime.now(timezone.utc)
    )
    if not revoked:
        # Another organization's key is `404`, exactly as its cases are.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No API key with id {key_id!r}.",
        )

    record = repository.get_api_key(principal.org_id, key_id)
    if record is None:  # pragma: no cover - the revoke above just found it
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No API key with id {key_id!r}.",
        )
    logger.info("API key %s revoked by %s", record.key_prefix, principal.user_id)
    return ApiKeySummary.of(record)
