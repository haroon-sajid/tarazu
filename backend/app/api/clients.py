"""`/v1/clients` — the firm's recurring clients (ADR 0005).

A firm does not audit a case; it audits a business, every month or every
quarter. The client is that business: added once, and carrying the settings
that outlive any single period — its rule thresholds, its currency, and the
language its owner reads. A case with a `client_id` is one period of one
client; a case without one is a one-off engagement and stays perfectly valid.

Each row says what the relationship amounts to: how many periods have been
run, how many items are still awaiting a decision across all of them, and what
is still outstanding with the client. Every one of those numbers is counted
from persisted deterministic results — the same figures `/v1/cases` shows,
grouped by client rather than estimated — with one queue read per period. At
firm scale (tens of clients and periods, not thousands) that is simpler and
safer than a bespoke aggregate query duplicated across two stores; revisit it
only if a real firm's client list ever gets slow.

Clients are archived, never deleted. The periods, decisions, reports, and
trail behind a relationship are evidence, and they outlive the relationship:
archiving takes the client out of the pickers and leaves all of it exactly
where it is.

Scoping is the same here as everywhere else — another firm's client is a
`404`, indistinguishable from one that never existed — and every write lands
in the append-only audit trail.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import Principal, get_repository, require_read, require_write
from app.core.audit import record_actor_action
from app.core.repository import CaseRepository
from app.shared.api import (
    CaseSummary,
    ClientDetailResponse,
    ClientListResponse,
    ClientSummary,
    CreateClientRequest,
    UpdateClientRequest,
)
from app.shared.schemas import (
    AuditAction,
    CaseRecord,
    Client,
    ClientRuleConfig,
    ReviewDecision,
)

__all__ = ["router"]

router = APIRouter(tags=["clients"])
logger = logging.getLogger(__name__)


def _tidy(value: str | None) -> str | None:
    """Trim a free-text field; a field holding only spaces holds nothing."""
    if value is None:
        return None
    return value.strip() or None


def _period_summary(
    repository: CaseRepository, org_id: str, case: CaseRecord
) -> CaseSummary:
    """One period of one client: the case plus its counts, read off the queue."""
    items = repository.list_review_items(org_id, case.case_id)
    return CaseSummary(
        case_id=case.case_id,
        client_name=case.client_name,
        client_id=case.client_id,
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


def _history(
    repository: CaseRepository, org_id: str, client_id: str
) -> tuple[list[CaseSummary], dict]:
    """A client's periods, newest first, and what they add up to.

    One function for both shapes the API serves: the list needs only the
    totals, the detail screen needs the periods themselves, and computing them
    twice by two routes is how the two stop agreeing with each other.
    """
    periods = [
        _period_summary(repository, org_id, case)
        for case in repository.list_cases_for_client(org_id, client_id)
    ]
    # Open or answered: what is still outstanding with the client. Resolved and
    # cancelled requests are finished work and do not belong in that count.
    open_requests = sum(
        1
        for period in periods
        for request in repository.list_evidence_requests(org_id, period.case_id)
        if not request.status.is_closed
    )
    period_ends = [period.period_end for period in periods if period.period_end]
    counts = {
        "period_count": len(periods),
        "pending_items": sum(period.pending_items for period in periods),
        "open_evidence_requests": open_requests,
        "last_period_end": max(period_ends) if period_ends else None,
        "last_activity_at": max(
            (period.created_at for period in periods), default=None
        ),
    }
    return periods, counts


def _summary(
    repository: CaseRepository, org_id: str, client: Client
) -> ClientSummary:
    """One list row: the client and the history behind it."""
    _, counts = _history(repository, org_id, client.client_id)
    return ClientSummary.of(client, **counts)


def _load(repository: CaseRepository, org_id: str, client_id: str) -> Client:
    """The client, or a `404` — which is also the answer for another firm's.

    The lookup is filtered by `org_id`, so this code cannot tell "does not
    exist" from "is not yours" either, and therefore cannot leak the
    difference.
    """
    client = repository.get_client(org_id, client_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No client with id {client_id!r}.",
        )
    return client


def _record_client_event(
    repository: CaseRepository,
    principal: Principal,
    client_id: str,
    action: AuditAction,
    detail: str,
) -> None:
    """Append a client-level event to the organization's trail.

    `AuditRecord.case_id` is the trail's key and is required; a client event
    has no case, so the client id goes in it. That is deliberate rather than a
    workaround: a client's history then reads back exactly as a case's does,
    with `list_audit(org_id, client_id)`, and no record has to invent a case it
    did not happen to.
    """
    record_actor_action(
        repository,
        principal.org_id,
        client_id,  # the trail is keyed by case; a client event uses the client id
        principal.actor,
        action,
        item_id=client_id,
        detail=detail,
    )


@router.get(
    "/clients",
    response_model=ClientListResponse,
    summary="List the firm's recurring clients",
)
async def list_clients(
    include_archived: bool = Query(
        default=False,
        description="Include archived clients, which are hidden by default.",
    ),
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> ClientListResponse:
    """Every client of the caller's organization, most recently added first.

    Archived clients are left out unless asked for: the common reading of this
    list is "who are we working for", and a relationship that ended should not
    crowd it. Nothing is hidden permanently — `include_archived=true` returns
    them with their history intact.
    """
    clients = [
        _summary(repository, principal.org_id, client)
        for client in repository.list_clients(
            principal.org_id, include_archived=include_archived
        )
    ]
    return ClientListResponse(total=len(clients), clients=clients)


@router.post(
    "/clients",
    response_model=ClientSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Add a recurring client",
)
async def create_client(
    body: CreateClientRequest,
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
) -> ClientSummary:
    """Add a business the firm audits, in the caller's organization.

    Only the name is required. Everything else has a working default — the
    module's rule thresholds, rupees, English — because a firm should be able
    to add a client in one field and tune it later, and because a threshold
    nobody chose is better named as a default than left empty.

    The client starts with no periods, so every count on the way back is zero.
    """
    name = _tidy(body.name)
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The client needs a name.",
        )

    client = Client(
        client_id=f"CLI-{uuid4().hex[:10]}",
        name=name,
        reference=_tidy(body.reference),
        # An omitted configuration means the module defaults, written onto the
        # client's own row rather than left empty: from here on the thresholds
        # are this client's, and retuning one client never moves another.
        rules=body.rules if body.rules is not None else ClientRuleConfig(),
        currency=body.currency,
        language=body.language,
        relationship_owner=_tidy(body.relationship_owner),
        notes=_tidy(body.notes),
        created_by=principal.user_id,
        created_at=datetime.now(timezone.utc),
    )
    repository.create_client(principal.org_id, client)

    _record_client_event(
        repository,
        principal,
        client.client_id,
        AuditAction.CLIENT_CREATED,
        f"Client {client.name!r} added ({client.currency}, {client.language.value}).",
    )
    logger.info(
        "Client %s (%s) added to org %s by %s",
        client.client_id,
        client.name,
        principal.org_id,
        principal.user_id,
    )
    return _summary(repository, principal.org_id, client)


@router.get(
    "/clients/{client_id}",
    response_model=ClientDetailResponse,
    summary="One client and every period run for it",
)
async def get_client(
    client_id: str,
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> ClientDetailResponse:
    """The client, and its periods newest first — the relationship as history.

    Each period carries the same counts the case list shows, so this screen and
    that one cannot disagree about how much work is outstanding.
    """
    client = _load(repository, principal.org_id, client_id)
    periods, counts = _history(repository, principal.org_id, client_id)
    return ClientDetailResponse(
        client=ClientSummary.of(client, **counts), periods=periods
    )


@router.patch(
    "/clients/{client_id}",
    response_model=ClientSummary,
    summary="Correct a client's details or retune its rules",
)
async def update_client(
    client_id: str,
    body: UpdateClientRequest,
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
) -> ClientSummary:
    """Change the client's settings: its name, reference, rules, and the rest.

    A field the request leaves out keeps its current value; `null` clears the
    optional free text (reference, relationship owner, notes). The name,
    currency, language, and rule thresholds cannot be cleared — a client is
    always called something, its money is always denominated in something, and
    a client with no thresholds would silently fall back to somebody else's —
    so `null` for those means "leave it alone".

    The creator and creation time are facts about the client's life rather than
    settings, and are not on this model at all.

    What changed is named in the audit trail, because "who retuned this client's
    approval limit, and when" is a question a reviewer will ask about a flag
    that did or did not fire. An empty body is not an error: it changes nothing
    and records nothing, since there is nothing worth remembering in it.
    """
    client = _load(repository, principal.org_id, client_id)
    provided = body.model_fields_set

    changes: list[str] = []
    updates: dict = {}

    if "name" in provided:
        name = _tidy(body.name)
        if not name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The client needs a name.",
            )
        if name != client.name:
            updates["name"] = name
            changes.append(f"renamed from {client.name!r} to {name!r}")

    if "reference" in provided:
        reference = _tidy(body.reference)
        if reference != client.reference:
            updates["reference"] = reference
            changes.append(
                f"reference set to {reference!r}" if reference else "reference cleared"
            )

    if "rules" in provided and body.rules is not None:
        if body.rules != client.rules:
            updates["rules"] = body.rules
            changes.append(
                "rule thresholds updated (approval limits "
                f"{body.rules.approval_limits}, sign-off "
                f"{'required' if body.rules.require_sign_off else 'not required'})"
            )

    if "currency" in provided and body.currency is not None:
        if body.currency != client.currency:
            updates["currency"] = body.currency
            changes.append(f"currency set to {body.currency}")

    if "language" in provided and body.language is not None:
        if body.language != client.language:
            updates["language"] = body.language
            changes.append(f"language set to {body.language.value}")

    if "relationship_owner" in provided:
        owner = _tidy(body.relationship_owner)
        if owner != client.relationship_owner:
            updates["relationship_owner"] = owner
            changes.append(
                f"relationship owner set to {owner!r}"
                if owner
                else "relationship owner cleared"
            )

    if "notes" in provided:
        notes = _tidy(body.notes)
        if notes != client.notes:
            updates["notes"] = notes
            changes.append("notes updated" if notes else "notes cleared")

    if not updates:
        # Nothing moved, so nothing is written and nothing is recorded. A no-op
        # PATCH is a fair request; a trail entry saying so would be noise.
        return _summary(repository, principal.org_id, client)

    updated = repository.update_client(
        principal.org_id, client.model_copy(update=updates)
    )
    if updated is None:  # pragma: no cover - the read above just found it
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No client with id {client_id!r}.",
        )

    _record_client_event(
        repository,
        principal,
        client_id,
        AuditAction.CLIENT_UPDATED,
        "; ".join(changes),
    )
    logger.info(
        "Client %s updated by %s: %s", client_id, principal.user_id, "; ".join(changes)
    )
    return _summary(repository, principal.org_id, updated)


@router.post(
    "/clients/{client_id}/archive",
    response_model=ClientSummary,
    summary="Archive a client",
)
async def archive_client(
    client_id: str,
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
) -> ClientSummary:
    """Take the client out of the pickers. Nothing underneath it is deleted.

    Its periods, decisions, reports, and audit trail stay exactly where they
    are — they are the evidence of work that was actually done, and the end of
    a relationship is not a reason to lose them. Archiving is reversible; this
    route has a `restore` counterpart precisely because it takes nothing away.

    Archiving an already-archived client is not an error. It keeps the original
    timestamp and records nothing, because nothing happened.
    """
    client = _load(repository, principal.org_id, client_id)
    if client.archived_at is not None:
        return _summary(repository, principal.org_id, client)

    archived_at = datetime.now(timezone.utc)
    archived = repository.set_client_archived(principal.org_id, client_id, archived_at)
    if not archived:  # pragma: no cover - the read above just found it
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No client with id {client_id!r}.",
        )

    periods, counts = _history(repository, principal.org_id, client_id)
    _record_client_event(
        repository,
        principal,
        client_id,
        AuditAction.CLIENT_ARCHIVED,
        (
            f"Client {client.name!r} archived with {len(periods)} periods. "
            "Periods, reports, and this trail are kept."
        ),
    )
    logger.info(
        "Client %s (%s) archived by %s", client_id, client.name, principal.user_id
    )
    return ClientSummary.of(
        client.model_copy(update={"archived_at": archived_at}), **counts
    )


@router.post(
    "/clients/{client_id}/restore",
    response_model=ClientSummary,
    summary="Restore an archived client",
)
async def restore_client(
    client_id: str,
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
) -> ClientSummary:
    """Put an archived client back in the pickers, history and all.

    Recorded as an edit rather than as its own action: restoring is a change to
    the client's settings, and the trail already carries the archiving it
    reverses. Restoring a client that was never archived changes nothing and
    records nothing.
    """
    client = _load(repository, principal.org_id, client_id)
    if client.archived_at is None:
        return _summary(repository, principal.org_id, client)

    restored = repository.set_client_archived(principal.org_id, client_id, None)
    if not restored:  # pragma: no cover - the read above just found it
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No client with id {client_id!r}.",
        )

    _record_client_event(
        repository,
        principal,
        client_id,
        AuditAction.CLIENT_UPDATED,
        f"Client {client.name!r} restored.",
    )
    logger.info(
        "Client %s (%s) restored by %s", client_id, client.name, principal.user_id
    )
    _, counts = _history(repository, principal.org_id, client_id)
    return ClientSummary.of(client.model_copy(update={"archived_at": None}), **counts)
