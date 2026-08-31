"""The persistence interface, the identity interface, and the document store.

Two implementations exist behind the repository: Supabase (Postgres + Storage)
and a local one (SQLite + the filesystem). The rest of the app is written
against these protocols and never against either implementation, which is what
lets the pipeline be run and demoed before the Supabase project exists.

**Every tenant-scoped method takes `org_id` first, and that is not decoration.**
An accounting firm is a tenant; a row belongs to exactly one. The implementations
filter on `org_id` in the query itself rather than fetching and then checking, so
a caller cannot forget the check and a missing row and another firm's row are
indistinguishable from the outside — which is what makes a cross-tenant read a
404 rather than a 403 that confirms the resource exists.

**The append-only guarantee is a property of the store, not of this interface.**
There is no `update_audit` or `delete_audit` method here — but that absence is
only a convention, and a convention is not a guarantee. Both implementations
enforce immutability in the database itself: Postgres via revoked privileges,
RLS, and a trigger (see `infra/supabase/schema.sql`); SQLite via triggers that
abort UPDATE and DELETE on the same table. Scoping the trail by organization
adds a filter to reads and a column to inserts; it takes nothing away.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol, runtime_checkable

from app.shared.schemas import (
    ApiKeyRecord,
    AuditRecord,
    BenfordResult,
    CaseRecord,
    CaseStatus,
    Client,
    EvidenceRequest,
    ExtractionResult,
    JobRecord,
    JobStatus,
    Organization,
    OrganizationMember,
    OrgInvitation,
    OrgProfile,
    ReportRecord,
    ReviewItem,
    SignOff,
    UserProfile,
    ValueCorrection,
)
from app.shared.api import UploadedDocument

__all__ = [
    "CaseDocument",
    "CaseRepository",
    "DocumentStore",
    "IdentityStore",
    "LocalUser",
    "StoredDocument",
]


class StoredDocument(UploadedDocument):
    """An uploaded document, once its bytes are actually somewhere."""


class CaseDocument(StoredDocument):
    """A stored document together with the case it belongs to.

    What `get_document` returns: a route that was handed only a document id
    needs the case to find the extraction behind it, and the org-scoped lookup
    is the only place that knows which case that is.
    """

    case_id: str


@runtime_checkable
class DocumentStore(Protocol):
    """Where uploaded document bytes live."""

    def put(self, path: str, content: bytes, content_type: str) -> str:
        """Store `content` at `path` and return the path it can be read back by."""

    def get(self, path: str) -> bytes:
        """Read the bytes back."""

    def signed_url(self, path: str, expires_in: int = 3600) -> str | None:
        """A short-lived URL the frontend can render the document from.

        Returns None when the store cannot mint one, in which case the frontend
        falls back to fetching the document through the backend.
        """


@runtime_checkable
class CaseRepository(Protocol):
    """Everything the app persists, behind one interface.

    Implementations must be safe to call from FastAPI request handlers.
    """

    # -- organizations ------------------------------------------------------ #

    def create_organization(self, organization: Organization) -> None: ...

    def get_organization(self, org_id: str) -> Organization | None: ...

    def add_member(self, member: OrganizationMember) -> None: ...

    def get_membership(self, user_id: str) -> OrganizationMember | None:
        """The organization this user belongs to, or None.

        A user may hold rows for more than one organization; this returns the
        oldest, deterministically, and that is the org every request of theirs
        is scoped to. Switching between organizations is a later feature and a
        later route — never a client-supplied `org_id`.
        """

    def list_members(self, org_id: str) -> list[OrganizationMember]: ...

    # -- organization profile ------------------------------------------------ #

    def get_org_profile(self, org_id: str) -> OrgProfile | None:
        """The firm's branding, or None if nobody has filled it in."""

    def save_org_profile(self, profile: OrgProfile) -> None:
        """Create or fully replace the firm's branding row."""

    # -- clients (ADR 0005) -------------------------------------------------- #

    def create_client(self, org_id: str, client: Client) -> None: ...

    def get_client(self, org_id: str, client_id: str) -> Client | None:
        """The client, or None if it does not exist *or* belongs to another firm."""

    def list_clients(self, org_id: str, include_archived: bool = False) -> list[Client]:
        """The firm's clients, newest first. Archived ones only when asked for."""

    def update_client(self, org_id: str, client: Client) -> Client | None:
        """Replace the client's editable facts. None if no such client here.

        The creator and creation time are facts about its life, not settings;
        callers send the record they read back, changed.
        """

    def set_client_archived(
        self, org_id: str, client_id: str, archived_at: datetime | None
    ) -> bool:
        """Archive (or restore) a client. False if no such client in this org.

        Archiving never deletes: the periods, decisions, reports, and trail
        behind a client outlive the relationship.
        """

    # -- invitations --------------------------------------------------------- #

    def create_invitation(self, invitation: OrgInvitation) -> None: ...

    def list_invitations(self, org_id: str) -> list[OrgInvitation]:
        """The organization's invitations, newest first, accepted ones included."""

    def find_invitation_by_code(self, code: str) -> OrgInvitation | None:
        """Deliberately not org-scoped: at signup the code is what *names* the
        organization the new user joins. Accepted invitations are returned —
        whether a used code is refused is the signup route's decision."""

    def accept_invitation(self, invite_id: str, user_id: str, at: datetime) -> None:
        """Close the door: stamp who came through it, and when."""

    def delete_invitation(self, org_id: str, invite_id: str) -> bool:
        """Revoke (or tidy away) one invitation. False if no such row in this org."""

    # -- cases -------------------------------------------------------------- #

    def create_case(self, org_id: str, case: CaseRecord) -> None: ...

    def get_case(self, org_id: str, case_id: str) -> CaseRecord | None:
        """The case, or None if it does not exist *or* belongs to another org."""

    def list_cases(self, org_id: str) -> list[CaseRecord]:
        """Every case of one organization, most recently created first."""

    def set_case_status(
        self, org_id: str, case_id: str, status: CaseStatus, detail: str | None = None
    ) -> None: ...

    def latest_case_id(self, org_id: str, created_by: str | None = None) -> str | None:
        """The most recently created case *in this org*, for a frontend that has none."""

    def list_cases_for_client(self, org_id: str, client_id: str) -> list[CaseRecord]:
        """Every period of one client, newest first. The client's history."""

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
        """Replace the case's editable facts. None if no such case in this org.

        The client name and the period are the engagement's settings; the
        status, creator, and timestamps are facts about its life and move only
        when the pipeline moves them. A caller that wants "keep the current
        value" sends the current value — the store does not guess, so there is
        no third state to get wrong.
        """

    def delete_case(self, org_id: str, case_id: str) -> bool:
        """Remove the case and its working data for good. False if absent.

        Documents, extractions, review items, flags, and the Benford result
        follow the case — both stores cascade on the case row. Generated
        reports and the audit trail are evidence and deliberately outlive the
        engagement: both are append-only in the database itself, so there is no
        deletion path for them here, and the trail's own record of this
        deletion keeps working after this returns.
        """

    # -- documents and extractions ------------------------------------------ #

    def add_documents(
        self, org_id: str, case_id: str, documents: list[StoredDocument], uploaded_by: str
    ) -> None: ...

    def list_documents(self, org_id: str, case_id: str) -> list[StoredDocument]: ...

    def get_document(self, org_id: str, document_id: str) -> CaseDocument | None:
        """The document, or None if it does not exist *or* belongs to another org."""

    def save_extraction(self, org_id: str, case_id: str, result: ExtractionResult) -> None: ...

    def list_extractions(self, org_id: str, case_id: str) -> list[ExtractionResult]: ...

    # -- review items ------------------------------------------------------- #

    def save_review_items(self, org_id: str, case_id: str, items: list[ReviewItem]) -> None:
        """Insert or replace the review queue for a case."""

    def list_review_items(self, org_id: str, case_id: str) -> list[ReviewItem]: ...

    def get_review_item(self, org_id: str, review_item_id: str) -> ReviewItem | None:
        """The item, or None if it does not exist *or* belongs to another org."""

    def update_review_item(self, org_id: str, item: ReviewItem) -> None:
        """Persist a decided item. Only the decision fields ever change."""

    # -- benford ------------------------------------------------------------ #

    def save_benford(self, org_id: str, case_id: str, result: BenfordResult) -> None: ...

    def get_benford(self, org_id: str, case_id: str) -> BenfordResult | None: ...

    # -- reports ------------------------------------------------------------ #
    #
    # Append-only, like the audit trail, and for the same reason: a report is
    # evidence of what was delivered. There is no `update_report` and no
    # `delete_report` here, and the stores refuse both underneath.

    def save_report(self, org_id: str, record: ReportRecord) -> None:
        """Record one generated report. Never replaces an existing one."""

    def list_reports(self, org_id: str, case_id: str) -> list[ReportRecord]:
        """Every report generated for the case, newest first."""

    def get_report(self, org_id: str, report_id: str) -> ReportRecord | None:
        """The report, or None if it does not exist *or* belongs to another org."""

    # -- background jobs ---------------------------------------------------- #

    def create_job(self, org_id: str, job: JobRecord) -> None: ...

    def get_job(self, org_id: str, job_id: str) -> JobRecord | None:
        """The job, or None if it does not exist *or* belongs to another org."""

    def update_job(self, org_id: str, job: JobRecord) -> None:
        """Persist a job's progress. Jobs are working state, not evidence:
        unlike the trail they may be updated, and what actually happened is
        recorded in the audit trail regardless of what this row ends up saying."""

    def latest_job_for_case(self, org_id: str, case_id: str) -> JobRecord | None:
        """The most recent job for one case, which is the one to poll."""

    def list_jobs(
        self, org_id: str, status: JobStatus | None = None, limit: int = 50
    ) -> list[JobRecord]:
        """Recent jobs, newest first, optionally filtered by status."""

    # -- value corrections --------------------------------------------------- #

    def save_correction(self, org_id: str, correction: ValueCorrection) -> None:
        """Record one correction. Corrections accumulate; none replaces another."""

    def list_corrections(self, org_id: str, case_id: str) -> list[ValueCorrection]:
        """Every correction made on the case, oldest first."""

    # -- evidence requests --------------------------------------------------- #

    def save_evidence_request(self, org_id: str, request: EvidenceRequest) -> None:
        """Create or replace one request. The trail keeps the state history."""

    def get_evidence_request(self, org_id: str, request_id: str) -> EvidenceRequest | None:
        """The request, or None if it does not exist *or* belongs elsewhere."""

    def list_evidence_requests(self, org_id: str, case_id: str) -> list[EvidenceRequest]:
        """Every request raised on the case, newest first."""

    # -- sign-offs ------------------------------------------------------------ #
    #
    # Append-only, like reports and the trail: a sign-off is somebody putting
    # their name to an engagement. There is no update and no delete.

    def save_sign_off(self, org_id: str, sign_off: SignOff) -> None: ...

    def list_sign_offs(self, org_id: str, case_id: str) -> list[SignOff]:
        """Every sign-off recorded on the case, newest first."""

    # -- api keys ----------------------------------------------------------- #

    def create_api_key(self, key: ApiKeyRecord) -> None:
        """Store a new key. `key.key_hash` is a digest; the raw key is not here."""

    def list_api_keys(self, org_id: str) -> list[ApiKeyRecord]:
        """Every key of one organization, revoked ones included."""

    def get_api_key(self, org_id: str, key_id: str) -> ApiKeyRecord | None:
        """The key, or None if it does not exist *or* belongs to another org."""

    def find_api_key_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        """The key with this digest, whatever organization it belongs to.

        **The one read in this interface that is not org-scoped, and it has to
        be**: this is what *establishes* the organization for a request that
        arrived with a key and no session. Everything the request does
        afterwards is scoped to `key.org_id`.

        Revoked keys are returned, not filtered out. Whether a revoked key is a
        `401` is an authentication decision, and it belongs in one place at the
        authentication boundary rather than being smuggled into a query here.
        """

    def revoke_api_key(self, org_id: str, key_id: str, revoked_at: datetime) -> bool:
        """Stamp `revoked_at`. Returns False if there is no such key in this org.

        Revoking never deletes: the row keeps "which key did this, and when was
        it turned off" answerable. Removing the row is a different act —
        `delete_api_key`.
        """

    def rename_api_key(self, org_id: str, key_id: str, name: str) -> bool:
        """Change the key's label. Returns False if no such key in this org.

        Only the name — scopes are fixed for a key's lifetime, and everything
        else on the row is a fact about its creation, not a setting.
        """

    def delete_api_key(self, org_id: str, key_id: str) -> bool:
        """Remove the key's row for good, active or revoked. False if absent.

        Deleting an active key stops it immediately: authentication finds keys
        by hash, and the hash is gone with the row. The audit trail keeps its
        `api-key:<prefix>` entries, but they no longer resolve to a name or a
        creator; the caller confirmed that trade before calling this.
        """

    def touch_api_key(self, key_id: str, used_at: datetime) -> None:
        """Record that a key was just used. Best-effort; never fails a request."""

    # -- user profiles ------------------------------------------------------- #

    def get_user_profile(self, user_id: str) -> UserProfile | None:
        """The person's editable profile, or None if they never saved one.

        Keyed by user, not organization: a profile is presentation (name,
        picture, contact details), never an authorization input.
        """

    def save_user_profile(self, profile: UserProfile) -> None:
        """Create or fully replace the person's profile row."""

    # -- audit trail -------------------------------------------------------- #

    def append_audit(self, org_id: str, record: AuditRecord) -> None:
        """Append one record. There is no counterpart that changes or removes one."""

    def list_audit(
        self, org_id: str, case_id: str, item_id: str | None = None
    ) -> list[AuditRecord]: ...


class LocalUser(Protocol):
    """The shape `IdentityStore` returns. Never carries the password hash."""

    user_id: str
    email: str


@runtime_checkable
class IdentityStore(Protocol):
    """Signup and password verification, for the local store only.

    With Supabase configured, identities live in `auth.users` and this protocol
    is not used at all: `POST /v1/auth/signup` and `/v1/auth/login` go to GoTrue.
    The local store implements it so the whole multi-tenant flow — two firms,
    two users, two sets of data — can be run end to end without a network.
    """

    def create_user(self, email: str, password: str) -> str:
        """Create a user and return its id. Raises `ValueError` if the email exists."""

    def verify_password(self, email: str, password: str) -> str | None:
        """The user's id if the password matches, else None."""

    def set_password(self, user_id: str, new_password: str) -> None:
        """Replace the user's password. Raises `ValueError` for an unknown user."""

    def get_user_email(self, user_id: str) -> str | None: ...
