"""The audit trail is immutable at the database level, not by convention.

The Postgres schema enforces this three ways — revoked privileges, insert/select
RLS policies, and a `before update or delete` trigger (see the hardening section
of `infra/supabase/schema.sql`). The local SQLite store carries the same
triggers. These tests exercise the SQLite side, which is the shape of the
guarantee; `infra/supabase/verify-audit-immutability.sql` proves it in Postgres.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.audit import record_human_action
from app.core.config import DEFAULT_ORG_ID as ORG
from app.core.repository import CaseRepository
from app.core.sqlite_store import AuditTrailImmutable, SqliteCaseRepository
from app.shared.schemas import ActorType, AuditAction, AuditRecord


def a_record(case_id: str = "CASE-TEST", audit_id: str = "AUD-000000000001") -> AuditRecord:
    return AuditRecord(
        audit_id=audit_id,
        case_id=case_id,
        actor_type=ActorType.HUMAN,
        actor_id="00000000-0000-4000-8000-000000000001",
        action=AuditAction.ITEM_APPROVED,
        item_id="RI-0002",
        detail="Vouched.",
        occurred_at=datetime.now(timezone.utc),
    )


def test_a_record_can_be_appended_and_read_back(repository: SqliteCaseRepository) -> None:
    repository.append_audit(ORG, a_record())
    trail = repository.list_audit(ORG, "CASE-TEST")
    assert len(trail) == 1
    assert trail[0].action is AuditAction.ITEM_APPROVED


def test_an_audit_row_cannot_be_updated(repository: SqliteCaseRepository) -> None:
    repository.append_audit(ORG, a_record())

    with pytest.raises(Exception, match="append-only"):
        repository._connection.execute(
            "update audit_trail set detail = 'tampered' where audit_id = ?",
            ("AUD-000000000001",),
        )

    assert repository.list_audit(ORG, "CASE-TEST")[0].detail == "Vouched."


def test_an_audit_row_cannot_be_deleted(repository: SqliteCaseRepository) -> None:
    repository.append_audit(ORG, a_record())

    with pytest.raises(Exception, match="append-only"):
        repository._connection.execute("delete from audit_trail")

    assert len(repository.list_audit(ORG, "CASE-TEST")) == 1


def test_the_whole_trail_cannot_be_wiped(repository: SqliteCaseRepository) -> None:
    """Not even by someone who reaches past the application entirely."""
    for index in range(3):
        repository.append_audit(ORG, a_record(audit_id=f"AUD-{index:012d}"))

    with pytest.raises(Exception, match="append-only"):
        repository._connection.executescript("delete from audit_trail;")

    assert len(repository.list_audit(ORG, "CASE-TEST")) == 3


def test_the_repository_exposes_no_way_to_change_a_record() -> None:
    """The interface offers append and read. There is no third option."""
    methods = {name for name in dir(CaseRepository) if not name.startswith("_")}
    audit_methods = {name for name in methods if "audit" in name}
    assert audit_methods == {"append_audit", "list_audit"}


def test_deleting_a_case_does_not_take_its_trail_with_it(
    repository: SqliteCaseRepository,
) -> None:
    """The trail has to be able to outlive what it describes."""
    repository.append_audit(ORG, a_record(case_id="CASE-GONE"))
    repository._connection.execute("delete from cases where case_id = ?", ("CASE-GONE",))
    repository._connection.commit()

    assert len(repository.list_audit(ORG, "CASE-GONE")) == 1


def test_the_writer_stamps_the_real_user_id(repository: SqliteCaseRepository) -> None:
    record = record_human_action(
        repository, ORG, "CASE-TEST", "a-real-user-uuid", AuditAction.ITEM_REJECTED,
        item_id="RI-0004", detail="Amount disagrees with the bank.",
    )
    assert record.actor_type is ActorType.HUMAN
    assert record.actor_id == "a-real-user-uuid"
    assert repository.list_audit(ORG, "CASE-TEST")[0].actor_id == "a-real-user-uuid"


def test_audit_records_are_frozen_in_python_too() -> None:
    """Belt and braces: the object cannot be mutated before it reaches the store."""
    record = a_record()
    with pytest.raises(Exception):
        record.detail = "tampered"


def test_the_immutability_error_is_recognisable(repository: SqliteCaseRepository) -> None:
    """The store raises a named error, so callers can tell this from a bug."""
    repository.append_audit(ORG, a_record())
    with pytest.raises(AuditTrailImmutable):
        repository._write(
            [("update audit_trail set detail = ? where audit_id = ?", ("x", "AUD-000000000001"))]
        )


# --------------------------------------------------------------------------- #
# Tenancy, without loosening any of the above
# --------------------------------------------------------------------------- #

OTHER_ORG = "11111111-1111-4111-8111-111111111111"


def test_one_firms_trail_is_invisible_to_another(repository: SqliteCaseRepository) -> None:
    """The trail is scoped by organization on the way out, as well as on the way in."""
    repository.append_audit(ORG, a_record(case_id="CASE-A", audit_id="AUD-A"))
    repository.append_audit(OTHER_ORG, a_record(case_id="CASE-B", audit_id="AUD-B"))

    assert [r.audit_id for r in repository.list_audit(ORG, "CASE-A")] == ["AUD-A"]
    assert [r.audit_id for r in repository.list_audit(OTHER_ORG, "CASE-B")] == ["AUD-B"]
    # Knowing the other firm's case id is not enough. Nothing comes back.
    assert repository.list_audit(ORG, "CASE-B") == []
    assert repository.list_audit(OTHER_ORG, "CASE-A") == []


def test_the_trail_stays_append_only_once_it_is_tenant_scoped(
    repository: SqliteCaseRepository,
) -> None:
    """Scoping narrowed who can read the trail. It changed nothing about writing it."""
    repository.append_audit(ORG, a_record())

    with pytest.raises(Exception, match="append-only"):
        repository._connection.execute(
            "update audit_trail set org_id = ? where audit_id = ?",
            (OTHER_ORG, "AUD-000000000001"),
        )
    with pytest.raises(Exception, match="append-only"):
        repository._connection.execute("delete from audit_trail where org_id = ?", (ORG,))

    assert len(repository.list_audit(ORG, "CASE-TEST")) == 1


def test_migrating_a_pre_tenancy_database_does_not_touch_the_trail(tmp_path) -> None:
    """The backfill adds a column to `audit_trail`; it never updates a row.

    A pre-tenancy database is built here by hand — the old tables, the old
    triggers, and rows in them — and then opened by the current store, which
    runs the same migration `infra/supabase/0002-organizations.sql` runs in
    Postgres. The existing trail entry must survive, keep its detail, land in
    the default organization, and still refuse to be rewritten.
    """
    import sqlite3

    from app.core.sqlite_store import SqliteCaseRepository as Store

    path = tmp_path / "pre-tenancy.db"
    legacy = sqlite3.connect(path)
    legacy.executescript(
        """
        create table cases (
          case_id text primary key, client_name text not null, period_start text,
          period_end text, status text not null default 'uploaded', status_detail text,
          created_by text not null, created_at text not null
        );
        create table audit_trail (
          audit_id text primary key, case_id text not null, actor_type text not null,
          actor_id text not null, action text not null, item_id text, detail text,
          occurred_at text not null
        );
        create trigger audit_trail_no_update before update on audit_trail
        begin select raise(abort, 'audit_trail is append-only: UPDATE is not permitted'); end;
        create trigger audit_trail_no_delete before delete on audit_trail
        begin select raise(abort, 'audit_trail is append-only: DELETE is not permitted'); end;

        insert into cases values
          ('CASE-OLD', 'Haroon Textiles', null, null, 'ready_for_review',
           null, '00000000-0000-4000-8000-000000000001', '2026-01-01T00:00:00+00:00');
        insert into audit_trail values
          ('AUD-OLD', 'CASE-OLD', 'human', '00000000-0000-4000-8000-000000000001',
           'item_approved', 'RI-0002', 'Vouched.', '2026-01-01T00:00:00+00:00');
        """
    )
    legacy.commit()
    legacy.close()

    store = Store(path, ORG)
    try:
        trail = store.list_audit(ORG, "CASE-OLD")
        assert [record.audit_id for record in trail] == ["AUD-OLD"]
        assert trail[0].detail == "Vouched."

        # The case came with it, into the same default organization.
        assert store.get_case(ORG, "CASE-OLD") is not None
        # And whoever created it now owns that organization.
        membership = store.get_membership("00000000-0000-4000-8000-000000000001")
        assert membership is not None and membership.org_id == ORG

        with pytest.raises(Exception, match="append-only"):
            store._connection.execute("update audit_trail set detail = 'tampered'")
    finally:
        store.close()
