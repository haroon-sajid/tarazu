"""Local implementation of `CaseRepository`, `IdentityStore`, and `DocumentStore`.

SQLite plus a directory of files. This exists so the whole pipeline can be run,
tested, and demoed before the Supabase project is provisioned, and so the test
suite never needs a network. It mirrors the Postgres schema in
`infra/supabase/schema.sql` and its tenancy migration
`infra/supabase/0002-organizations.sql`, including the two parts that matter:

**Every tenant-owned row carries an `org_id`, and every read filters on it.**
The filter is in the SQL, not in a check the caller could forget, so another
firm's case is not "found but refused" — it is simply not found. That is the
same shape as the Postgres row-level security policies, which make a row outside
your `organization_members` invisible rather than forbidden.

**`audit_trail` is append-only here too.** Two SQLite triggers abort UPDATE and
DELETE on the table. That is the same guarantee the Postgres schema makes with
revoked privileges, RLS, and its own trigger — so a test that proves the trail
cannot be rewritten proves it about the shape of the system, not about one
database. Adding `org_id` to the trail is an added column and an added read
filter; no statement in this file updates or deletes an audit row, and the
migration below fills the new column with `alter table ... add column ... default`
precisely so that it never has to.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.core.config import DEFAULT_ORG_ID
from app.core.repository import CaseDocument, StoredDocument
from app.shared.schemas import (
    ApiKeyRecord,
    AssistantLanguage,
    AuditRecord,
    BenfordResult,
    CaseRecord,
    CaseStatus,
    Client,
    ClientRuleConfig,
    EvidenceRequest,
    EvidenceRequestStatus,
    ExtractionResult,
    JobKind,
    JobRecord,
    JobStatus,
    OrganizationMember,
    Organization,
    OrgInvitation,
    OrgProfile,
    OrgRole,
    ReportRecord,
    ReviewItem,
    SignOff,
    UserProfile,
    ValueCorrection,
)

__all__ = [
    "AuditTrailImmutable",
    "LocalDocumentStore",
    "ReportImmutable",
    "SignOffImmutable",
    "SqliteCaseRepository",
    "hash_password",
    "verify_password_hash",
]


class AuditTrailImmutable(RuntimeError):
    """Something tried to change or remove an audit record. It was refused."""


class ReportImmutable(RuntimeError):
    """Something tried to change or remove a generated report's record. Refused."""


class SignOffImmutable(RuntimeError):
    """Something tried to change or remove a sign-off. It was refused."""


#: Every tenant-owned table, and the audit trail. Used by the migration below.
ORG_SCOPED_TABLES = (
    "cases",
    "documents",
    "extractions",
    "review_items",
    "flags",
    "benford_results",
    "audit_trail",
)


#: Created first, and before the migration runs: the migration backfills into
#: the default organization, so the organization has to be there to back into.
TENANCY_SCHEMA = """
pragma journal_mode = wal;
pragma foreign_keys  = on;

-- ---------------------------------------------------------------------------
-- Tenancy. One organization is one accounting firm; membership is the only
-- thing that grants access to its rows.
-- ---------------------------------------------------------------------------

create table if not exists organizations (
  org_id     text primary key,
  name       text not null,
  created_at text not null
);

create table if not exists organization_members (
  org_id     text not null references organizations (org_id) on delete cascade,
  user_id    text not null,
  role       text not null default 'member' check (role in ('owner', 'member')),
  created_at text not null,
  primary key (org_id, user_id)
);

create index if not exists organization_members_user_idx
  on organization_members (user_id, created_at);

-- Local identities, so signup and login work without Supabase. With Supabase
-- configured this table is unused: identities live in auth.users.
create table if not exists users (
  user_id       text primary key,
  email         text not null unique collate nocase,
  password_hash text not null,
  created_at    text not null
);

-- Open doors into an organization: an owner cuts a single-use code; whoever
-- presents it at signup joins that org instead of founding a new one.
create table if not exists org_invitations (
  invite_id   text primary key,
  org_id      text not null,
  email       text not null,
  role        text not null default 'member' check (role in ('owner', 'member')),
  code        text not null unique,
  created_by  text not null,
  created_at  text not null,
  accepted_at text,
  accepted_by text
);

create index if not exists org_invitations_org_idx
  on org_invitations (org_id, created_at);

-- Editable presentation on top of an identity: display name, picture,
-- contact details. Keyed by user, never an authorization input. The avatar
-- is a size-capped data: URL, so no file storage is involved.
create table if not exists user_profiles (
  user_id              text primary key,
  full_name            text,
  job_title            text,
  phone                text,
  avatar               text,
  gender               text,
  date_of_birth        text,
  location             text,
  license_number       text,
  language             text,
  notify_case_ready    integer,
  notify_high_severity integer,
  notify_weekly_digest integer,
  updated_at           text
);
"""


SCHEMA = """
-- A recurring client of the firm (ADR 0005). Periods point at it; archiving
-- one keeps every period, decision, report, and trail entry behind it.
create table if not exists clients (
  client_id          text primary key,
  org_id             text not null,
  name               text not null,
  reference          text,
  rules              text not null,
  currency           text not null default 'PKR',
  language           text not null default 'en',
  relationship_owner text,
  notes              text,
  created_by         text not null,
  created_at         text not null,
  archived_at        text
);

create index if not exists clients_org_idx on clients (org_id, created_at);

create table if not exists cases (
  case_id       text primary key,
  org_id        text not null,
  client_name   text not null,
  client_id     text,
  period_start  text,
  period_end    text,
  status        text not null default 'uploaded',
  status_detail text,
  created_by    text not null,
  created_at    text not null
);

create index if not exists cases_client_idx on cases (org_id, client_id, created_at);

create table if not exists documents (
  document_id   text primary key,
  org_id        text not null,
  case_id       text not null references cases (case_id) on delete cascade,
  document_type text not null,
  filename      text not null,
  storage_path  text not null,
  size_bytes    integer not null default 0,
  uploaded_by   text not null,
  created_at    text not null
);

create table if not exists extractions (
  document_id        text primary key,
  org_id             text not null,
  case_id            text not null references cases (case_id) on delete cascade,
  model              text not null,
  needs_human_review integer not null default 0,
  payload            text not null,
  created_at         text not null
);

create table if not exists review_items (
  review_item_id        text primary key,
  org_id                text not null,
  case_id               text not null references cases (case_id) on delete cascade,
  position              integer not null,
  match_status          text not null,
  match_strength        text not null,
  extraction_confidence text not null,
  flag_count            integer not null default 0,
  decision              text not null default 'pending',
  decided_by            text,
  decided_at            text,
  rejection_reason      text,
  payload               text not null
);

-- `flag_id` is minted by `rules/`, which numbers flags within the case it was
-- given. That makes it unique per case and no wider, so the key is the case's
-- as well — otherwise one firm's upload would replace a row belonging to
-- another firm that happened to raise its first flag too.
create table if not exists flags (
  flag_id        text not null,
  org_id         text not null,
  case_id        text not null references cases (case_id) on delete cascade,
  review_item_id text not null,
  rule_id        text not null,
  severity       text not null,
  explanation    text not null,
  source_row_id  text not null,
  payload        text not null,
  primary key (org_id, case_id, flag_id)
);

create table if not exists benford_results (
  case_id text primary key references cases (case_id) on delete cascade,
  org_id  text not null,
  payload text not null
);

-- API keys. One organization's machine credentials, for n8n, Zapier, or its own
-- software. `key_hash` is a SHA-256 digest and `key_prefix` is the non-secret
-- head of the key; the raw key is never written here.
--
-- There is no delete path. A key is revoked by stamping `revoked_at`, and the
-- row stays so that "which key did this, and when was it turned off" remains
-- answerable long after the integration is gone.
create table if not exists api_keys (
  key_id       text primary key,
  org_id       text not null,
  created_by   text not null,
  name         text not null,
  key_prefix   text not null,
  key_hash     text not null unique,
  scopes       text not null,
  last_used_at text,
  revoked_at   text,
  created_at   text not null
);

create index if not exists api_keys_org_idx on api_keys (org_id, created_at);

create table if not exists audit_trail (
  audit_id    text primary key,
  org_id      text not null,
  case_id     text not null,
  actor_type  text not null,
  actor_id    text not null,
  action      text not null,
  item_id     text,
  detail      text,
  occurred_at text not null
);

-- Generated reports: what the firm delivered, and when. Append-only for the
-- same reason the trail is — a report is evidence — and enforced the same way,
-- by triggers below. No foreign key to `cases`: a report must outlive what it
-- describes. The bytes live in the document store at the two paths.
create table if not exists reports (
  report_id          text primary key,
  org_id             text not null,
  case_id            text not null,
  generated_by       text not null,
  generated_at       text not null,
  pdf_path           text not null,
  excel_path         text not null,
  pdf_sha256         text not null,
  excel_sha256       text not null,
  item_count         integer not null,
  approved_count     integer not null,
  rejected_count     integer not null,
  pending_count      integer not null,
  flag_count         integer not null,
  audit_record_count integer not null
);

create index if not exists reports_org_case_idx
  on reports (org_id, case_id, generated_at);

create trigger if not exists reports_no_update
  before update on reports
begin
  select raise(abort, 'reports are append-only: UPDATE is not permitted');
end;

create trigger if not exists reports_no_delete
  before delete on reports
begin
  select raise(abort, 'reports are append-only: DELETE is not permitted');
end;

-- Background jobs. Working state, not evidence: these rows are updated as a
-- job progresses, and what actually happened is in the audit trail regardless
-- of what this table ends up saying. No foreign key to `cases`, so a job row
-- survives a case being deleted mid-flight.
create table if not exists jobs (
  job_id      text primary key,
  org_id      text not null,
  case_id     text not null,
  kind        text not null default 'pipeline',
  status      text not null default 'queued',
  progress    integer not null default 0,
  step        text not null default 'Queued',
  created_by  text not null,
  created_at  text not null,
  started_at  text,
  finished_at text,
  error       text
);

create index if not exists jobs_org_case_idx on jobs (org_id, case_id, created_at);

-- What a human says a value actually is, beside what the model read. Both are
-- kept: this is evidence about the extraction, not a rewrite of it.
create table if not exists value_corrections (
  correction_id   text primary key,
  org_id          text not null,
  case_id         text not null references cases (case_id) on delete cascade,
  review_item_id  text not null,
  document_id     text not null,
  field           text not null,
  ai_value        text,
  corrected_value text not null,
  note            text,
  corrected_by    text not null,
  corrected_at    text not null
);

create index if not exists value_corrections_case_idx
  on value_corrections (org_id, case_id, corrected_at);

-- "Ask the client for invoice #43", with its state, inside the trail rather
-- than in somebody's inbox.
create table if not exists evidence_requests (
  request_id     text primary key,
  org_id         text not null,
  case_id        text not null references cases (case_id) on delete cascade,
  review_item_id text,
  title          text not null,
  detail         text,
  status         text not null default 'open',
  due_date       text,
  requested_by   text not null,
  requested_at   text not null,
  response_note  text,
  responded_by   text,
  responded_at   text,
  cancellation_note text,
  closed_by      text,
  closed_at      text
);

create index if not exists evidence_requests_case_idx
  on evidence_requests (org_id, case_id, requested_at);

-- A second person putting their name to a finished engagement (maker-checker).
-- Append-only for the same reason reports are: it is somebody's signature.
create table if not exists sign_offs (
  sign_off_id    text primary key,
  org_id         text not null,
  case_id        text not null,
  signed_by      text not null,
  signed_at      text not null,
  note           text,
  item_count     integer not null,
  approved_count integer not null,
  rejected_count integer not null
);

create index if not exists sign_offs_org_case_idx
  on sign_offs (org_id, case_id, signed_at);

create trigger if not exists sign_offs_no_update
  before update on sign_offs
begin
  select raise(abort, 'sign_offs are append-only: UPDATE is not permitted');
end;

create trigger if not exists sign_offs_no_delete
  before delete on sign_offs
begin
  select raise(abort, 'sign_offs are append-only: DELETE is not permitted');
end;

-- The firm's own details, printed on every report it delivers. Presentation
-- only; nothing here is an authorization input.
create table if not exists org_profiles (
  org_id              text primary key,
  legal_name          text,
  address             text,
  contact_email       text,
  phone               text,
  website             text,
  registration_number text,
  logo                text,
  report_footer       text,
  updated_at          text
);

-- Named for the columns they lead with, so a database migrated from the
-- single-tenant schema gains them rather than keeping the narrower ones under
-- a name `create index if not exists` would skip.
create index if not exists audit_trail_org_case_idx
  on audit_trail (org_id, case_id, occurred_at);
create index if not exists review_items_org_case_idx
  on review_items (org_id, case_id, position);
create index if not exists cases_org_idx on cases (org_id, created_at);

-- The append-only guarantee, enforced by the database rather than by us
-- remembering. Mirrors the REVOKE + RLS + trigger in the Postgres schema.
create trigger if not exists audit_trail_no_update
  before update on audit_trail
begin
  select raise(abort, 'audit_trail is append-only: UPDATE is not permitted');
end;

create trigger if not exists audit_trail_no_delete
  before delete on audit_trail
begin
  select raise(abort, 'audit_trail is append-only: DELETE is not permitted');
end;
"""


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Local password hashing
#
# PBKDF2-HMAC-SHA256 from the standard library, so the local store needs no
# extra dependency. Supabase hashes with bcrypt on its side; nothing here is
# ever used when Supabase is configured.
# --------------------------------------------------------------------------- #

_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password_hash(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, expected = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(derived.hex(), expected)


class SqliteCaseRepository:
    """`CaseRepository` and `IdentityStore` backed by a SQLite file (or `:memory:`)."""

    def __init__(
        self,
        database_path: Path | str = ":memory:",
        default_org_id: str = DEFAULT_ORG_ID,
    ) -> None:
        self._path = str(database_path)
        self._default_org_id = default_org_id
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False because FastAPI's threadpool moves sync
        # handlers between threads; the lock below serialises access.
        self._connection = sqlite3.connect(self._path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._connection.executescript(TENANCY_SCHEMA)
            self._connection.commit()
        # Before the rest of the schema, because that half indexes `org_id` and
        # a database written before tenancy has no such column yet.
        self._migrate_to_multi_tenant()
        self._migrate_user_profiles()
        # Before the schema, not after: the schema indexes `cases (client_id)`,
        # and a database written before that column existed has to gain it
        # first or the index is built over a column that is not there. On a
        # fresh database the tables do not exist yet, so this does nothing and
        # the schema below creates them complete.
        self._migrate_added_columns()
        with self._lock:
            self._connection.executescript(SCHEMA)
            self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    # -- migration ---------------------------------------------------------- #

    def _migrate_user_profiles(self) -> None:
        """Add profile columns a database created before them does not have.

        `create table if not exists` never alters an existing table, so a file
        from an earlier build keeps its old shape; this backfills the missing
        columns additively. Idempotent — it runs on every open.
        """
        with self._lock:
            existing = {
                row[1]
                for row in self._connection.execute(
                    "pragma table_info(user_profiles)"
                )
            }
            if not existing:
                return  # fresh database: the schema creates the full table
            wanted = {
                "gender": "text",
                "date_of_birth": "text",
                "location": "text",
                "license_number": "text",
                "language": "text",
                "notify_case_ready": "integer",
                "notify_high_severity": "integer",
                "notify_weekly_digest": "integer",
            }
            for column, column_type in wanted.items():
                if column not in existing:
                    self._connection.execute(
                        f"alter table user_profiles add column {column} {column_type}"
                    )
            self._connection.commit()

    #: Columns added to existing tables after they were first shipped. Purely
    #: additive: `create table if not exists` never alters a table that is
    #: already there, so a database from an earlier build keeps its old shape
    #: until this fills the gaps. Every one of these is nullable, which is what
    #: makes the migration safe to run against live rows — a case written
    #: before clients existed simply has no client, and that is a valid case.
    ADDED_COLUMNS: dict[str, dict[str, str]] = {
        "cases": {"client_id": "text"},
        "evidence_requests": {"cancellation_note": "text"},
    }

    def _migrate_added_columns(self) -> None:
        """Add nullable columns a database created before them does not have."""
        with self._lock:
            for table, columns in self.ADDED_COLUMNS.items():
                existing = {
                    row["name"]
                    for row in self._connection.execute(f"pragma table_info({table})")
                }
                if not existing:
                    continue  # fresh database: the schema created it in full
                for column, column_type in columns.items():
                    if column not in existing:
                        self._connection.execute(
                            f"alter table {table} add column {column} {column_type}"
                        )
            self._connection.commit()

    def _migrate_to_multi_tenant(self) -> None:
        """Add `org_id` to a database written before tenancy existed, and backfill.

        The mirror of `infra/supabase/0002-organizations.sql`, and idempotent for
        the same reason: it is run on every open. Existing rows are assigned to
        the default organization.

        The column is added with a DEFAULT rather than added and then UPDATEd,
        because an UPDATE on `audit_trail` is refused by the append-only trigger
        — correctly. `alter table ... add column` is DDL: it fills the existing
        rows without ever issuing a row update, so the trail gains its tenant
        column with its immutability entirely intact.
        """
        with self._lock:
            added: list[str] = []
            for table in ORG_SCOPED_TABLES:
                columns = {
                    row["name"]
                    for row in self._connection.execute(f"pragma table_info({table})")
                }
                if not columns or "org_id" in columns:
                    continue
                self._connection.execute(
                    f"alter table {table} add column org_id text not null "
                    f"default '{self._default_org_id}'"
                )
                added.append(table)
            if added:
                self._connection.execute(
                    "insert or ignore into organizations (org_id, name, created_at) "
                    "values (?, ?, ?)",
                    (self._default_org_id, "Tarazu (default organization)", _now()),
                )
                # Whoever created the pre-tenancy cases owns the default org.
                for row in self._connection.execute(
                    "select distinct created_by from cases where org_id = ?",
                    (self._default_org_id,),
                ).fetchall():
                    self._connection.execute(
                        "insert or ignore into organization_members "
                        "(org_id, user_id, role, created_at) values (?, ?, 'owner', ?)",
                        (self._default_org_id, row["created_by"], _now()),
                    )
            self._rekey_flags_by_organization()
            self._connection.commit()

    def _rekey_flags_by_organization(self) -> None:
        """Widen the `flags` primary key from `flag_id` to `(org_id, case_id, flag_id)`.

        SQLite cannot alter a primary key in place, so the table is rebuilt with
        its rows carried across. `flags` is derived output — it is written whole
        by `save_review_items` and never read back by the app — so a rebuild
        loses nothing, and leaving the narrow key in place would let one firm's
        upload silently replace another firm's flag row.

        Called with the lock held, inside the migration's transaction.
        """
        info = self._connection.execute("pragma table_info(flags)").fetchall()
        key = [row["name"] for row in info if row["pk"]]
        if not info or key != ["flag_id"]:
            return
        self._connection.executescript(
            """
            create table flags_rekeyed (
              flag_id        text not null,
              org_id         text not null,
              case_id        text not null references cases (case_id) on delete cascade,
              review_item_id text not null,
              rule_id        text not null,
              severity       text not null,
              explanation    text not null,
              source_row_id  text not null,
              payload        text not null,
              primary key (org_id, case_id, flag_id)
            );
            insert into flags_rekeyed
              select flag_id, org_id, case_id, review_item_id, rule_id, severity,
                     explanation, source_row_id, payload
              from flags;
            drop table flags;
            alter table flags_rekeyed rename to flags;
            """
        )

    # -- internals ---------------------------------------------------------- #

    def _write(self, statements: list[tuple[str, tuple]]) -> None:
        with self._lock:
            try:
                for sql, params in statements:
                    self._connection.execute(sql, params)
                self._connection.commit()
            except sqlite3.IntegrityError as error:
                self._connection.rollback()
                message = str(error)
                if message.startswith("reports are append-only"):
                    raise ReportImmutable(message) from error
                if message.startswith("sign_offs are append-only"):
                    raise SignOffImmutable(message) from error
                if "append-only" in message:
                    raise AuditTrailImmutable(message) from error
                raise

    def _rows(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._connection.execute(sql, params).fetchall()

    # -- organizations ------------------------------------------------------ #

    def create_organization(self, organization: Organization) -> None:
        self._write(
            [
                (
                    "insert or replace into organizations (org_id, name, created_at) "
                    "values (?, ?, ?)",
                    (
                        organization.org_id,
                        organization.name,
                        organization.created_at.isoformat(),
                    ),
                )
            ]
        )

    def get_organization(self, org_id: str) -> Organization | None:
        rows = self._rows("select * from organizations where org_id = ?", (org_id,))
        if not rows:
            return None
        return Organization(
            org_id=rows[0]["org_id"],
            name=rows[0]["name"],
            created_at=rows[0]["created_at"],
        )

    def add_member(self, member: OrganizationMember) -> None:
        self._write(
            [
                (
                    "insert or replace into organization_members "
                    "(org_id, user_id, role, created_at) values (?, ?, ?, ?)",
                    (
                        member.org_id,
                        member.user_id,
                        member.role.value,
                        member.created_at.isoformat(),
                    ),
                )
            ]
        )

    def get_membership(self, user_id: str) -> OrganizationMember | None:
        rows = self._rows(
            "select * from organization_members where user_id = ? "
            "order by created_at, org_id limit 1",
            (user_id,),
        )
        return self._member(rows[0]) if rows else None

    def list_members(self, org_id: str) -> list[OrganizationMember]:
        return [
            self._member(row)
            for row in self._rows(
                "select * from organization_members where org_id = ? order by created_at",
                (org_id,),
            )
        ]

    @staticmethod
    def _member(row: sqlite3.Row) -> OrganizationMember:
        return OrganizationMember(
            org_id=row["org_id"],
            user_id=row["user_id"],
            role=OrgRole(row["role"]),
            created_at=row["created_at"],
        )

    # -- organization profile ------------------------------------------------ #

    def get_org_profile(self, org_id: str) -> OrgProfile | None:
        rows = self._rows("select * from org_profiles where org_id = ?", (org_id,))
        if not rows:
            return None
        row = rows[0]
        return OrgProfile(
            org_id=row["org_id"],
            legal_name=row["legal_name"],
            address=row["address"],
            contact_email=row["contact_email"],
            phone=row["phone"],
            website=row["website"],
            registration_number=row["registration_number"],
            logo=row["logo"],
            report_footer=row["report_footer"],
            updated_at=row["updated_at"],
        )

    def save_org_profile(self, profile: OrgProfile) -> None:
        self._write(
            [
                (
                    "insert or replace into org_profiles (org_id, legal_name, address, "
                    "contact_email, phone, website, registration_number, logo, "
                    "report_footer, updated_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        profile.org_id,
                        profile.legal_name,
                        profile.address,
                        profile.contact_email,
                        profile.phone,
                        profile.website,
                        profile.registration_number,
                        profile.logo,
                        profile.report_footer,
                        _iso(profile.updated_at),
                    ),
                )
            ]
        )

    # -- clients (ADR 0005) -------------------------------------------------- #

    def create_client(self, org_id: str, client: Client) -> None:
        self._write([self._client_upsert(org_id, client)])

    @staticmethod
    def _client_upsert(org_id: str, client: Client) -> tuple[str, tuple]:
        return (
            "insert or replace into clients (client_id, org_id, name, reference, "
            "rules, currency, language, relationship_owner, notes, created_by, "
            "created_at, archived_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                client.client_id,
                org_id,
                client.name,
                client.reference,
                client.rules.model_dump_json(),
                client.currency,
                client.language.value,
                client.relationship_owner,
                client.notes,
                client.created_by,
                client.created_at.isoformat(),
                _iso(client.archived_at),
            ),
        )

    def get_client(self, org_id: str, client_id: str) -> Client | None:
        rows = self._rows(
            "select * from clients where client_id = ? and org_id = ?",
            (client_id, org_id),
        )
        return self._client(rows[0]) if rows else None

    def list_clients(self, org_id: str, include_archived: bool = False) -> list[Client]:
        sql = "select * from clients where org_id = ?"
        if not include_archived:
            sql += " and archived_at is null"
        return [
            self._client(row)
            for row in self._rows(sql + " order by created_at desc", (org_id,))
        ]

    def update_client(self, org_id: str, client: Client) -> Client | None:
        if self.get_client(org_id, client.client_id) is None:
            return None
        self._write([self._client_upsert(org_id, client)])
        return self.get_client(org_id, client.client_id)

    def set_client_archived(
        self, org_id: str, client_id: str, archived_at: datetime | None
    ) -> bool:
        if self.get_client(org_id, client_id) is None:
            return False
        self._write(
            [
                (
                    "update clients set archived_at = ? where client_id = ? and org_id = ?",
                    (_iso(archived_at), client_id, org_id),
                )
            ]
        )
        return True

    @staticmethod
    def _client(row: sqlite3.Row) -> Client:
        return Client(
            client_id=row["client_id"],
            name=row["name"],
            reference=row["reference"],
            rules=ClientRuleConfig.model_validate_json(row["rules"]),
            currency=row["currency"],
            language=AssistantLanguage(row["language"]),
            relationship_owner=row["relationship_owner"],
            notes=row["notes"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            archived_at=row["archived_at"],
        )

    # -- invitations --------------------------------------------------------- #

    def create_invitation(self, invitation: OrgInvitation) -> None:
        self._write(
            [
                (
                    "insert into org_invitations (invite_id, org_id, email, role, "
                    "code, created_by, created_at, accepted_at, accepted_by) "
                    "values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        invitation.invite_id,
                        invitation.org_id,
                        invitation.email,
                        invitation.role.value,
                        invitation.code,
                        invitation.created_by,
                        invitation.created_at.isoformat(),
                        _iso(invitation.accepted_at),
                        invitation.accepted_by,
                    ),
                )
            ]
        )

    def list_invitations(self, org_id: str) -> list[OrgInvitation]:
        return [
            self._invitation(row)
            for row in self._rows(
                "select * from org_invitations where org_id = ? order by created_at desc",
                (org_id,),
            )
        ]

    def find_invitation_by_code(self, code: str) -> OrgInvitation | None:
        """Not org-scoped: the code is what names the org. See the protocol."""
        rows = self._rows("select * from org_invitations where code = ?", (code,))
        return self._invitation(rows[0]) if rows else None

    def accept_invitation(self, invite_id: str, user_id: str, at: datetime) -> None:
        self._write(
            [
                (
                    "update org_invitations set accepted_at = ?, accepted_by = ? "
                    "where invite_id = ?",
                    (at.isoformat(), user_id, invite_id),
                )
            ]
        )

    def delete_invitation(self, org_id: str, invite_id: str) -> bool:
        rows = self._rows(
            "select invite_id from org_invitations where invite_id = ? and org_id = ?",
            (invite_id, org_id),
        )
        if not rows:
            return False
        self._write(
            [
                (
                    "delete from org_invitations where invite_id = ? and org_id = ?",
                    (invite_id, org_id),
                )
            ]
        )
        return True

    @staticmethod
    def _invitation(row: sqlite3.Row) -> OrgInvitation:
        return OrgInvitation(
            invite_id=row["invite_id"],
            org_id=row["org_id"],
            email=row["email"],
            role=OrgRole(row["role"]),
            code=row["code"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            accepted_at=row["accepted_at"],
            accepted_by=row["accepted_by"],
        )

    # -- local identities (IdentityStore) ----------------------------------- #

    def create_user(self, email: str, password: str) -> str:
        user_id = str(uuid4())
        try:
            self._write(
                [
                    (
                        "insert into users (user_id, email, password_hash, created_at) "
                        "values (?, ?, ?, ?)",
                        (user_id, email.strip(), hash_password(password), _now()),
                    )
                ]
            )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"an account already exists for {email!r}") from error
        return user_id

    def verify_password(self, email: str, password: str) -> str | None:
        rows = self._rows("select * from users where email = ?", (email.strip(),))
        if not rows:
            return None
        return rows[0]["user_id"] if verify_password_hash(password, rows[0]["password_hash"]) else None

    def set_password(self, user_id: str, new_password: str) -> None:
        rows = self._rows("select user_id from users where user_id = ?", (user_id,))
        if not rows:
            raise ValueError(f"no user with id {user_id!r}")
        self._write(
            [
                (
                    "update users set password_hash = ? where user_id = ?",
                    (hash_password(new_password), user_id),
                )
            ]
        )

    def get_user_email(self, user_id: str) -> str | None:
        rows = self._rows("select email from users where user_id = ?", (user_id,))
        return rows[0]["email"] if rows else None

    # -- cases -------------------------------------------------------------- #

    def create_case(self, org_id: str, case: CaseRecord) -> None:
        self._write(
            [
                (
                    "insert or replace into cases (case_id, org_id, client_name, client_id, "
                    "period_start, period_end, status, status_detail, created_by, created_at) "
                    "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        case.case_id,
                        org_id,
                        case.client_name,
                        case.client_id,
                        case.period_start.isoformat() if case.period_start else None,
                        case.period_end.isoformat() if case.period_end else None,
                        case.status.value,
                        case.status_detail,
                        case.created_by,
                        case.created_at.isoformat(),
                    ),
                )
            ]
        )

    def get_case(self, org_id: str, case_id: str) -> CaseRecord | None:
        rows = self._rows(
            "select * from cases where case_id = ? and org_id = ?", (case_id, org_id)
        )
        return self._case(rows[0]) if rows else None

    def list_cases(self, org_id: str) -> list[CaseRecord]:
        return [
            self._case(row)
            for row in self._rows(
                "select * from cases where org_id = ? order by created_at desc",
                (org_id,),
            )
        ]

    def list_cases_for_client(self, org_id: str, client_id: str) -> list[CaseRecord]:
        return [
            self._case(row)
            for row in self._rows(
                "select * from cases where org_id = ? and client_id = ? "
                "order by created_at desc",
                (org_id, client_id),
            )
        ]

    @staticmethod
    def _case(row: sqlite3.Row) -> CaseRecord:
        keys = row.keys()
        return CaseRecord(
            case_id=row["case_id"],
            client_name=row["client_name"],
            # A database written before clients existed has no such column even
            # after the migration adds it to `cases` — a row read from an older
            # connection can still be missing it, so ask before reading.
            client_id=row["client_id"] if "client_id" in keys else None,
            period_start=row["period_start"],
            period_end=row["period_end"],
            status=CaseStatus(row["status"]),
            status_detail=row["status_detail"],
            created_by=row["created_by"],
            created_at=row["created_at"],
        )

    def set_case_status(
        self, org_id: str, case_id: str, status: CaseStatus, detail: str | None = None
    ) -> None:
        self._write(
            [
                (
                    "update cases set status = ?, status_detail = ? "
                    "where case_id = ? and org_id = ?",
                    (status.value, detail, case_id, org_id),
                )
            ]
        )

    def latest_case_id(self, org_id: str, created_by: str | None = None) -> str | None:
        if created_by:
            rows = self._rows(
                "select case_id from cases where org_id = ? and created_by = ? "
                "order by created_at desc limit 1",
                (org_id, created_by),
            )
            if rows:
                return rows[0]["case_id"]
        rows = self._rows(
            "select case_id from cases where org_id = ? order by created_at desc limit 1",
            (org_id,),
        )
        return rows[0]["case_id"] if rows else None

    def update_case(
        self,
        org_id: str,
        case_id: str,
        *,
        client_name: str,
        period_start: date | None,
        period_end: date | None,
        client_id: str | None = None,
    ) -> CaseRecord | None:
        if self.get_case(org_id, case_id) is None:
            return None
        self._write(
            [
                (
                    "update cases set client_name = ?, client_id = ?, period_start = ?, "
                    "period_end = ? where case_id = ? and org_id = ?",
                    (
                        client_name,
                        client_id,
                        period_start.isoformat() if period_start else None,
                        period_end.isoformat() if period_end else None,
                        case_id,
                        org_id,
                    ),
                )
            ]
        )
        return self.get_case(org_id, case_id)

    def delete_case(self, org_id: str, case_id: str) -> bool:
        if self.get_case(org_id, case_id) is None:
            return False
        # The working tables are deleted by name rather than trusting the
        # foreign-key cascades to exist on a database created before they did;
        # all six statements run in one transaction, so a case is either fully
        # gone or fully intact. The audit trail and any reports are not named
        # at all — they are append-only evidence and outlive the case (their
        # triggers would refuse a delete here anyway).
        self._write(
            [
                ("delete from flags where org_id = ? and case_id = ?", (org_id, case_id)),
                (
                    "delete from value_corrections where org_id = ? and case_id = ?",
                    (org_id, case_id),
                ),
                (
                    "delete from evidence_requests where org_id = ? and case_id = ?",
                    (org_id, case_id),
                ),
                (
                    "delete from review_items where org_id = ? and case_id = ?",
                    (org_id, case_id),
                ),
                (
                    "delete from extractions where org_id = ? and case_id = ?",
                    (org_id, case_id),
                ),
                (
                    "delete from documents where org_id = ? and case_id = ?",
                    (org_id, case_id),
                ),
                (
                    "delete from benford_results where org_id = ? and case_id = ?",
                    (org_id, case_id),
                ),
                ("delete from cases where case_id = ? and org_id = ?", (case_id, org_id)),
            ]
        )
        return True

    # -- documents and extractions ------------------------------------------ #

    def add_documents(
        self, org_id: str, case_id: str, documents: list[StoredDocument], uploaded_by: str
    ) -> None:
        now = _now()
        self._write(
            [
                (
                    "insert or replace into documents (document_id, org_id, case_id, "
                    "document_type, filename, storage_path, size_bytes, uploaded_by, created_at) "
                    "values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        document.document_id,
                        org_id,
                        case_id,
                        document.document_type.value,
                        document.filename,
                        document.storage_path,
                        document.size_bytes,
                        uploaded_by,
                        now,
                    ),
                )
                for document in documents
            ]
        )

    def list_documents(self, org_id: str, case_id: str) -> list[StoredDocument]:
        return [
            StoredDocument(
                document_id=row["document_id"],
                document_type=row["document_type"],
                filename=row["filename"],
                size_bytes=row["size_bytes"],
                storage_path=row["storage_path"],
            )
            for row in self._rows(
                "select * from documents where org_id = ? and case_id = ? order by created_at",
                (org_id, case_id),
            )
        ]

    def get_document(self, org_id: str, document_id: str) -> CaseDocument | None:
        rows = self._rows(
            "select * from documents where document_id = ? and org_id = ?",
            (document_id, org_id),
        )
        if not rows:
            return None
        row = rows[0]
        return CaseDocument(
            document_id=row["document_id"],
            document_type=row["document_type"],
            filename=row["filename"],
            size_bytes=row["size_bytes"],
            storage_path=row["storage_path"],
            case_id=row["case_id"],
        )

    def save_extraction(self, org_id: str, case_id: str, result: ExtractionResult) -> None:
        self._write(
            [
                (
                    "insert or replace into extractions (document_id, org_id, case_id, model, "
                    "needs_human_review, payload, created_at) values (?, ?, ?, ?, ?, ?, ?)",
                    (
                        result.document_id,
                        org_id,
                        case_id,
                        result.model,
                        int(result.needs_human_review),
                        result.model_dump_json(),
                        result.extracted_at.isoformat(),
                    ),
                )
            ]
        )

    def list_extractions(self, org_id: str, case_id: str) -> list[ExtractionResult]:
        return [
            ExtractionResult.model_validate_json(row["payload"])
            for row in self._rows(
                "select payload from extractions where org_id = ? and case_id = ? "
                "order by created_at",
                (org_id, case_id),
            )
        ]

    # -- review items ------------------------------------------------------- #

    def save_review_items(self, org_id: str, case_id: str, items: list[ReviewItem]) -> None:
        statements: list[tuple[str, tuple]] = [
            ("delete from flags where org_id = ? and case_id = ?", (org_id, case_id)),
            ("delete from review_items where org_id = ? and case_id = ?", (org_id, case_id)),
        ]
        for position, item in enumerate(items):
            statements.append(
                (
                    "insert into review_items (review_item_id, org_id, case_id, position, "
                    "match_status, match_strength, extraction_confidence, flag_count, "
                    "decision, decided_by, decided_at, rejection_reason, payload) "
                    "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.review_item_id,
                        org_id,
                        case_id,
                        position,
                        item.match.status.value,
                        item.match.match_strength.value,
                        item.extraction_confidence.value,
                        len(item.flags),
                        item.decision.value,
                        item.decided_by,
                        _iso(item.decided_at),
                        item.rejection_reason,
                        item.model_dump_json(),
                    ),
                )
            )
            statements.extend(
                (
                    "insert or replace into flags (flag_id, org_id, case_id, review_item_id, "
                    "rule_id, severity, explanation, source_row_id, payload) "
                    "values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        flag.flag_id,
                        org_id,
                        case_id,
                        item.review_item_id,
                        flag.rule_id,
                        flag.severity.value,
                        flag.explanation,
                        flag.source_row_id,
                        flag.model_dump_json(),
                    ),
                )
                for flag in item.flags
            )
        self._write(statements)

    def list_review_items(self, org_id: str, case_id: str) -> list[ReviewItem]:
        return [
            ReviewItem.model_validate_json(row["payload"])
            for row in self._rows(
                "select payload from review_items where org_id = ? and case_id = ? "
                "order by position",
                (org_id, case_id),
            )
        ]

    def get_review_item(self, org_id: str, review_item_id: str) -> ReviewItem | None:
        rows = self._rows(
            "select payload from review_items where review_item_id = ? and org_id = ?",
            (review_item_id, org_id),
        )
        return ReviewItem.model_validate_json(rows[0]["payload"]) if rows else None

    def update_review_item(self, org_id: str, item: ReviewItem) -> None:
        self._write(
            [
                (
                    "update review_items set decision = ?, decided_by = ?, decided_at = ?, "
                    "rejection_reason = ?, payload = ? where review_item_id = ? and org_id = ?",
                    (
                        item.decision.value,
                        item.decided_by,
                        _iso(item.decided_at),
                        item.rejection_reason,
                        item.model_dump_json(),
                        item.review_item_id,
                        org_id,
                    ),
                )
            ]
        )

    # -- benford ------------------------------------------------------------ #

    def save_benford(self, org_id: str, case_id: str, result: BenfordResult) -> None:
        self._write(
            [
                (
                    "insert or replace into benford_results (case_id, org_id, payload) "
                    "values (?, ?, ?)",
                    (case_id, org_id, result.model_dump_json()),
                )
            ]
        )

    def get_benford(self, org_id: str, case_id: str) -> BenfordResult | None:
        rows = self._rows(
            "select payload from benford_results where case_id = ? and org_id = ?",
            (case_id, org_id),
        )
        return BenfordResult.model_validate_json(rows[0]["payload"]) if rows else None

    # -- reports ------------------------------------------------------------ #

    def save_report(self, org_id: str, record: ReportRecord) -> None:
        # A plain insert: the triggers refuse an update, and `insert or replace`
        # would be a delete in disguise. A duplicate id is an error, correctly.
        self._write(
            [
                (
                    "insert into reports (report_id, org_id, case_id, generated_by, "
                    "generated_at, pdf_path, excel_path, pdf_sha256, excel_sha256, "
                    "item_count, approved_count, rejected_count, pending_count, "
                    "flag_count, audit_record_count) "
                    "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.report_id,
                        org_id,
                        record.case_id,
                        record.generated_by,
                        record.generated_at.isoformat(),
                        record.pdf_path,
                        record.excel_path,
                        record.pdf_sha256,
                        record.excel_sha256,
                        record.item_count,
                        record.approved_count,
                        record.rejected_count,
                        record.pending_count,
                        record.flag_count,
                        record.audit_record_count,
                    ),
                )
            ]
        )

    def list_reports(self, org_id: str, case_id: str) -> list[ReportRecord]:
        return [
            self._report(row)
            for row in self._rows(
                "select * from reports where org_id = ? and case_id = ? "
                "order by generated_at desc, report_id desc",
                (org_id, case_id),
            )
        ]

    def get_report(self, org_id: str, report_id: str) -> ReportRecord | None:
        rows = self._rows(
            "select * from reports where report_id = ? and org_id = ?", (report_id, org_id)
        )
        return self._report(rows[0]) if rows else None

    @staticmethod
    def _report(row: sqlite3.Row) -> ReportRecord:
        return ReportRecord(
            report_id=row["report_id"],
            case_id=row["case_id"],
            generated_by=row["generated_by"],
            generated_at=row["generated_at"],
            pdf_path=row["pdf_path"],
            excel_path=row["excel_path"],
            pdf_sha256=row["pdf_sha256"],
            excel_sha256=row["excel_sha256"],
            item_count=row["item_count"],
            approved_count=row["approved_count"],
            rejected_count=row["rejected_count"],
            pending_count=row["pending_count"],
            flag_count=row["flag_count"],
            audit_record_count=row["audit_record_count"],
        )

    # -- background jobs ---------------------------------------------------- #

    def create_job(self, org_id: str, job: JobRecord) -> None:
        self._write([self._job_upsert(org_id, job)])

    def update_job(self, org_id: str, job: JobRecord) -> None:
        # Jobs are working state, not evidence: `insert or replace` is right
        # here, and there is no trigger refusing it. What actually happened is
        # in the append-only audit trail, whatever this row ends up saying.
        self._write([self._job_upsert(org_id, job)])

    @staticmethod
    def _job_upsert(org_id: str, job: JobRecord) -> tuple[str, tuple]:
        return (
            "insert or replace into jobs (job_id, org_id, case_id, kind, status, "
            "progress, step, created_by, created_at, started_at, finished_at, error) "
            "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job.job_id,
                org_id,
                job.case_id,
                job.kind.value,
                job.status.value,
                job.progress,
                job.step,
                job.created_by,
                job.created_at.isoformat(),
                _iso(job.started_at),
                _iso(job.finished_at),
                job.error,
            ),
        )

    def get_job(self, org_id: str, job_id: str) -> JobRecord | None:
        rows = self._rows(
            "select * from jobs where job_id = ? and org_id = ?", (job_id, org_id)
        )
        return self._job(rows[0]) if rows else None

    def latest_job_for_case(self, org_id: str, case_id: str) -> JobRecord | None:
        rows = self._rows(
            "select * from jobs where org_id = ? and case_id = ? "
            "order by created_at desc, job_id desc limit 1",
            (org_id, case_id),
        )
        return self._job(rows[0]) if rows else None

    def list_jobs(
        self, org_id: str, status: JobStatus | None = None, limit: int = 50
    ) -> list[JobRecord]:
        sql = "select * from jobs where org_id = ?"
        params: tuple = (org_id,)
        if status is not None:
            sql += " and status = ?"
            params = (org_id, status.value)
        return [
            self._job(row)
            for row in self._rows(
                sql + " order by created_at desc, job_id desc limit ?",
                (*params, int(limit)),
            )
        ]

    @staticmethod
    def _job(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            job_id=row["job_id"],
            case_id=row["case_id"],
            kind=JobKind(row["kind"]),
            status=JobStatus(row["status"]),
            progress=row["progress"],
            step=row["step"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            error=row["error"],
        )

    # -- value corrections --------------------------------------------------- #

    def save_correction(self, org_id: str, correction: ValueCorrection) -> None:
        self._write(
            [
                (
                    "insert or replace into value_corrections (correction_id, org_id, "
                    "case_id, review_item_id, document_id, field, ai_value, "
                    "corrected_value, note, corrected_by, corrected_at) "
                    "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        correction.correction_id,
                        org_id,
                        correction.case_id,
                        correction.review_item_id,
                        correction.document_id,
                        correction.field,
                        correction.ai_value,
                        correction.corrected_value,
                        correction.note,
                        correction.corrected_by,
                        correction.corrected_at.isoformat(),
                    ),
                )
            ]
        )

    def list_corrections(self, org_id: str, case_id: str) -> list[ValueCorrection]:
        return [
            ValueCorrection(
                correction_id=row["correction_id"],
                case_id=row["case_id"],
                review_item_id=row["review_item_id"],
                document_id=row["document_id"],
                field=row["field"],
                ai_value=row["ai_value"],
                corrected_value=row["corrected_value"],
                note=row["note"],
                corrected_by=row["corrected_by"],
                corrected_at=row["corrected_at"],
            )
            for row in self._rows(
                "select * from value_corrections where org_id = ? and case_id = ? "
                "order by corrected_at, correction_id",
                (org_id, case_id),
            )
        ]

    # -- evidence requests --------------------------------------------------- #

    def save_evidence_request(self, org_id: str, request: EvidenceRequest) -> None:
        self._write(
            [
                (
                    "insert or replace into evidence_requests (request_id, org_id, "
                    "case_id, review_item_id, title, detail, status, due_date, "
                    "requested_by, requested_at, response_note, responded_by, "
                    "responded_at, cancellation_note, closed_by, closed_at) "
                    "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        request.request_id,
                        org_id,
                        request.case_id,
                        request.review_item_id,
                        request.title,
                        request.detail,
                        request.status.value,
                        request.due_date.isoformat() if request.due_date else None,
                        request.requested_by,
                        request.requested_at.isoformat(),
                        request.response_note,
                        request.responded_by,
                        _iso(request.responded_at),
                        request.cancellation_note,
                        request.closed_by,
                        _iso(request.closed_at),
                    ),
                )
            ]
        )

    def get_evidence_request(
        self, org_id: str, request_id: str
    ) -> EvidenceRequest | None:
        rows = self._rows(
            "select * from evidence_requests where request_id = ? and org_id = ?",
            (request_id, org_id),
        )
        return self._evidence_request(rows[0]) if rows else None

    def list_evidence_requests(self, org_id: str, case_id: str) -> list[EvidenceRequest]:
        return [
            self._evidence_request(row)
            for row in self._rows(
                "select * from evidence_requests where org_id = ? and case_id = ? "
                "order by requested_at desc, request_id desc",
                (org_id, case_id),
            )
        ]

    @staticmethod
    def _evidence_request(row: sqlite3.Row) -> EvidenceRequest:
        return EvidenceRequest(
            request_id=row["request_id"],
            case_id=row["case_id"],
            review_item_id=row["review_item_id"],
            title=row["title"],
            detail=row["detail"],
            status=EvidenceRequestStatus(row["status"]),
            due_date=row["due_date"],
            requested_by=row["requested_by"],
            requested_at=row["requested_at"],
            response_note=row["response_note"],
            responded_by=row["responded_by"],
            responded_at=row["responded_at"],
            cancellation_note=row["cancellation_note"],
            closed_by=row["closed_by"],
            closed_at=row["closed_at"],
        )

    # -- sign-offs ------------------------------------------------------------ #

    def save_sign_off(self, org_id: str, sign_off: SignOff) -> None:
        # A plain insert: the triggers refuse an update, and `insert or replace`
        # would be a delete in disguise. A duplicate id is an error, correctly.
        self._write(
            [
                (
                    "insert into sign_offs (sign_off_id, org_id, case_id, signed_by, "
                    "signed_at, note, item_count, approved_count, rejected_count) "
                    "values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        sign_off.sign_off_id,
                        org_id,
                        sign_off.case_id,
                        sign_off.signed_by,
                        sign_off.signed_at.isoformat(),
                        sign_off.note,
                        sign_off.item_count,
                        sign_off.approved_count,
                        sign_off.rejected_count,
                    ),
                )
            ]
        )

    def list_sign_offs(self, org_id: str, case_id: str) -> list[SignOff]:
        return [
            SignOff(
                sign_off_id=row["sign_off_id"],
                case_id=row["case_id"],
                signed_by=row["signed_by"],
                signed_at=row["signed_at"],
                note=row["note"],
                item_count=row["item_count"],
                approved_count=row["approved_count"],
                rejected_count=row["rejected_count"],
            )
            for row in self._rows(
                "select * from sign_offs where org_id = ? and case_id = ? "
                "order by signed_at desc, sign_off_id desc",
                (org_id, case_id),
            )
        ]

    # -- api keys ----------------------------------------------------------- #

    def create_api_key(self, key: ApiKeyRecord) -> None:
        self._write(
            [
                (
                    "insert into api_keys (key_id, org_id, created_by, name, key_prefix, "
                    "key_hash, scopes, last_used_at, revoked_at, created_at) "
                    "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        key.key_id,
                        key.org_id,
                        key.created_by,
                        key.name,
                        key.key_prefix,
                        key.key_hash,
                        json.dumps([scope.value for scope in key.scopes]),
                        _iso(key.last_used_at),
                        _iso(key.revoked_at),
                        key.created_at.isoformat(),
                    ),
                )
            ]
        )

    def list_api_keys(self, org_id: str) -> list[ApiKeyRecord]:
        return [
            self._api_key(row)
            for row in self._rows(
                "select * from api_keys where org_id = ? order by created_at desc",
                (org_id,),
            )
        ]

    def get_api_key(self, org_id: str, key_id: str) -> ApiKeyRecord | None:
        rows = self._rows(
            "select * from api_keys where key_id = ? and org_id = ?", (key_id, org_id)
        )
        return self._api_key(rows[0]) if rows else None

    def find_api_key_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        """Not org-scoped, because this is what decides the org. See the protocol."""
        rows = self._rows("select * from api_keys where key_hash = ?", (key_hash,))
        return self._api_key(rows[0]) if rows else None

    def revoke_api_key(self, org_id: str, key_id: str, revoked_at: datetime) -> bool:
        existing = self.get_api_key(org_id, key_id)
        if existing is None:
            return False
        if existing.revoked_at is not None:
            # Already revoked. Keep the original timestamp: when it stopped
            # working is a fact, and the second call did not change it.
            return True
        self._write(
            [
                (
                    "update api_keys set revoked_at = ? where key_id = ? and org_id = ?",
                    (revoked_at.isoformat(), key_id, org_id),
                )
            ]
        )
        return True

    def rename_api_key(self, org_id: str, key_id: str, name: str) -> bool:
        if self.get_api_key(org_id, key_id) is None:
            return False
        self._write(
            [
                (
                    "update api_keys set name = ? where key_id = ? and org_id = ?",
                    (name, key_id, org_id),
                )
            ]
        )
        return True

    def delete_api_key(self, org_id: str, key_id: str) -> bool:
        if self.get_api_key(org_id, key_id) is None:
            # Missing and another org's key are refused the same way.
            return False
        self._write(
            [
                (
                    "delete from api_keys where key_id = ? and org_id = ?",
                    (key_id, org_id),
                )
            ]
        )
        return True

    def touch_api_key(self, key_id: str, used_at: datetime) -> None:
        self._write(
            [
                (
                    "update api_keys set last_used_at = ? where key_id = ?",
                    (used_at.isoformat(), key_id),
                )
            ]
        )

    @staticmethod
    def _api_key(row: sqlite3.Row) -> ApiKeyRecord:
        return ApiKeyRecord(
            key_id=row["key_id"],
            org_id=row["org_id"],
            created_by=row["created_by"],
            name=row["name"],
            key_prefix=row["key_prefix"],
            key_hash=row["key_hash"],
            scopes=json.loads(row["scopes"]),
            last_used_at=row["last_used_at"],
            revoked_at=row["revoked_at"],
            created_at=row["created_at"],
        )

    # -- user profiles ------------------------------------------------------- #

    def get_user_profile(self, user_id: str) -> UserProfile | None:
        rows = self._rows(
            "select * from user_profiles where user_id = ?", (user_id,)
        )
        if not rows:
            return None
        row = rows[0]

        def flag(column: str, default: bool) -> bool:
            # Rows written before the column existed hold NULL: the default rules.
            value = row[column]
            return default if value is None else bool(value)

        return UserProfile(
            user_id=row["user_id"],
            full_name=row["full_name"],
            job_title=row["job_title"],
            phone=row["phone"],
            avatar=row["avatar"],
            gender=row["gender"],
            date_of_birth=row["date_of_birth"],
            location=row["location"],
            license_number=row["license_number"],
            language=row["language"],
            notify_case_ready=flag("notify_case_ready", True),
            notify_high_severity=flag("notify_high_severity", True),
            notify_weekly_digest=flag("notify_weekly_digest", False),
            updated_at=row["updated_at"],
        )

    def save_user_profile(self, profile: UserProfile) -> None:
        self._write(
            [
                (
                    "insert or replace into user_profiles "
                    "(user_id, full_name, job_title, phone, avatar, gender, "
                    "date_of_birth, location, license_number, language, "
                    "notify_case_ready, notify_high_severity, notify_weekly_digest, "
                    "updated_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        profile.user_id,
                        profile.full_name,
                        profile.job_title,
                        profile.phone,
                        profile.avatar,
                        profile.gender,
                        profile.date_of_birth.isoformat() if profile.date_of_birth else None,
                        profile.location,
                        profile.license_number,
                        profile.language,
                        int(profile.notify_case_ready),
                        int(profile.notify_high_severity),
                        int(profile.notify_weekly_digest),
                        _iso(profile.updated_at),
                    ),
                )
            ]
        )

    # -- audit trail -------------------------------------------------------- #

    def append_audit(self, org_id: str, record: AuditRecord) -> None:
        self._write(
            [
                (
                    "insert into audit_trail (audit_id, org_id, case_id, actor_type, actor_id, "
                    "action, item_id, detail, occurred_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.audit_id,
                        org_id,
                        record.case_id,
                        record.actor_type.value,
                        record.actor_id,
                        record.action.value,
                        record.item_id,
                        record.detail,
                        record.occurred_at.isoformat(),
                    ),
                )
            ]
        )

    def list_audit(
        self, org_id: str, case_id: str, item_id: str | None = None
    ) -> list[AuditRecord]:
        sql = "select * from audit_trail where org_id = ? and case_id = ?"
        params: tuple = (org_id, case_id)
        if item_id:
            sql += " and item_id = ?"
            params = (org_id, case_id, item_id)
        return [
            AuditRecord(
                audit_id=row["audit_id"],
                case_id=row["case_id"],
                actor_type=row["actor_type"],
                actor_id=row["actor_id"],
                action=row["action"],
                item_id=row["item_id"],
                detail=row["detail"],
                occurred_at=row["occurred_at"],
            )
            for row in self._rows(sql + " order by occurred_at, audit_id", params)
        ]


class LocalDocumentStore:
    """`DocumentStore` backed by a directory on disk."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> Path:
        target = (self._root / path).resolve()
        if not str(target).startswith(str(self._root.resolve())):
            raise ValueError(f"path escapes the document store: {path!r}")
        return target

    def put(self, path: str, content: bytes, content_type: str) -> str:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return path

    def get(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    def signed_url(self, path: str, expires_in: int = 3600) -> str | None:
        # A local directory is not reachable from the browser. The frontend
        # fetches these through the backend instead.
        return None
