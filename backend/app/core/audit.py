"""The append-only audit-trail writer (reliability rule 5).

Every action, by AI or human, lands here. There is exactly one function that
writes, it only ever appends, and there is deliberately no counterpart that
changes or removes a record.

That is the convention. The guarantee is in the database:

- **Postgres** — `revoke update, delete on public.audit_trail from anon,
  authenticated, service_role`, RLS policies for insert and select only, and a
  `before update or delete` trigger that raises. The REVOKE is the one that
  matters most: `service_role` bypasses RLS, but it does not bypass table
  privileges.
- **SQLite** (local mode) — triggers that abort UPDATE and DELETE.

Every record is written into one organization and read back only within it. That
narrows who can *see* the trail; it does not narrow what the trail keeps, and it
adds no route by which a record could be changed or removed. The select policy
is scoped by membership; the insert policy stays open to any member; there is
still no update policy and no delete policy, and there must never be one.

See `infra/supabase/schema.sql` and `infra/supabase/0002-organizations.sql`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from app.core.repository import CaseRepository
from app.shared.schemas import ActorType, AuditAction, AuditRecord

__all__ = [
    "Actor",
    "record_action",
    "record_actor_action",
    "record_ai_action",
    "record_human_action",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Actor:
    """Who is doing this, and who is accountable for it.

    Those are usually the same person and occasionally are not. A request that
    arrives with an API key was made by a machine — `actor_type` is `system` and
    `actor_id` names the key — but a person generated that key and answers for
    what it does, and that person is `user_id`.

    Keeping both is what lets the trail be honest in one direction and the
    records be attributable in the other: `audit_trail` says "api-key:trz_live_
    a1b2c3d4 approved this", while `review_items.decided_by` names the human
    whose key it is. Collapsing them would either hide the automation or leave
    the decision belonging to nobody.
    """

    actor_type: ActorType
    actor_id: str
    #: The accountable person. Lands in `cases.created_by` and
    #: `review_items.decided_by`, both of which reference a real user.
    user_id: str

    @classmethod
    def human(cls, user_id: str) -> "Actor":
        """A person, signed in. Acting as themselves."""
        return cls(actor_type=ActorType.HUMAN, actor_id=user_id, user_id=user_id)

    @classmethod
    def api_key(cls, key_prefix: str, owner_user_id: str) -> "Actor":
        """A machine holding one of `owner_user_id`'s keys.

        `actor_id` is `api-key:<prefix>` — the key's non-secret head, never the
        key itself. Reading the trail tells you which integration acted, which
        is exactly what you need to know when revoking one.
        """
        return cls(
            actor_type=ActorType.SYSTEM,
            actor_id=f"api-key:{key_prefix}",
            user_id=owner_user_id,
        )


def record_action(
    repository: CaseRepository,
    org_id: str,
    case_id: str,
    actor_type: ActorType,
    actor_id: str,
    action: AuditAction,
    item_id: str | None = None,
    detail: str | None = None,
) -> AuditRecord:
    """Append one record to the trail and return it.

    The record is returned so a route can hand it straight back to the caller:
    an approve response carries the trail entry it wrote, which is what lets the
    UI show the auditor that their decision was recorded.

    `org_id` is the tenant the record belongs to. It is a column on the row, not
    a field of `AuditRecord`: the trail entry a caller is handed back describes
    what happened, and which firm's trail it lives in is not theirs to be told.
    """
    record = AuditRecord(
        audit_id=f"AUD-{uuid4().hex[:12]}",
        case_id=case_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        item_id=item_id,
        detail=detail,
        occurred_at=datetime.now(timezone.utc),
    )
    repository.append_audit(org_id, record)
    logger.info(
        "audit: %s by %s:%s on %s (case %s, org %s)",
        action.value,
        actor_type.value,
        actor_id,
        item_id or "-",
        case_id,
        org_id,
    )
    return record


def record_actor_action(
    repository: CaseRepository,
    org_id: str,
    case_id: str,
    actor: Actor,
    action: AuditAction,
    item_id: str | None = None,
    detail: str | None = None,
) -> AuditRecord:
    """Append an action, however it was authenticated.

    The one writer used by the request path, so a route never has to decide
    whether this call came from a person or from an integration — the `Actor`
    already knows, and the trail records what it says.
    """
    return record_action(
        repository, org_id, case_id, actor.actor_type, actor.actor_id, action,
        item_id, detail,
    )


def record_human_action(
    repository: CaseRepository,
    org_id: str,
    case_id: str,
    user_id: str,
    action: AuditAction,
    item_id: str | None = None,
    detail: str | None = None,
) -> AuditRecord:
    """Append an action a person took. `user_id` is the real Supabase user id."""
    return record_action(
        repository, org_id, case_id, ActorType.HUMAN, user_id, action, item_id, detail
    )


def record_ai_action(
    repository: CaseRepository,
    org_id: str,
    case_id: str,
    model: str,
    action: AuditAction,
    item_id: str | None = None,
    detail: str | None = None,
) -> AuditRecord:
    """Append an action the AI took. `model` identifies which model did it."""
    return record_action(
        repository, org_id, case_id, ActorType.AI, model, action, item_id, detail
    )
