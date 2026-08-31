"""Supabase implementation of `CaseRepository`, over PostgREST.

Mirrors `sqlite_store.SqliteCaseRepository` method for method, so the app
behaves identically either side of the store. The Postgres schema it expects is
`infra/supabase/schema.sql` plus its tenancy migration
`infra/supabase/0002-organizations.sql`.

**Every query carries `org_id=eq.<org>`.** That is belt and braces rather than
the only defence: the REST calls here use the service role, which bypasses row
level security, so the RLS policies in the migration protect anything that
reaches Postgres another way (the browser, `psql`, a leaked anon key) while
these filters protect what goes through this class. Both layers say the same
thing, and neither is trusted to be the only one saying it.

Note what is *not* here: no `update_audit`, no `delete_audit`. That absence is
the convention; the guarantee is the REVOKE, the RLS policies, and the trigger
in the schema, which refuse those writes to every role the app can use — the
service role included.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from app.core.repository import CaseDocument, StoredDocument
from app.core.supabase_client import SupabaseRest
from app.shared.schemas import (
    ApiKeyRecord,
    AuditRecord,
    BenfordResult,
    CaseRecord,
    CaseStatus,
    ExtractionResult,
    Organization,
    OrganizationMember,
    OrgInvitation,
    OrgRole,
    ReportRecord,
    ReviewItem,
    SalesAnalyticsResult,
    UserProfile,
)

__all__ = ["SupabaseCaseRepository"]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class SupabaseCaseRepository:
    """`CaseRepository` backed by Supabase Postgres."""

    def __init__(self, rest: SupabaseRest) -> None:
        self._rest = rest

    # -- organizations ------------------------------------------------------ #

    def create_organization(self, organization: Organization) -> None:
        self._rest.insert(
            "organizations",
            [
                {
                    "org_id": organization.org_id,
                    "name": organization.name,
                    "created_at": organization.created_at.isoformat(),
                }
            ],
            upsert=True,
        )

    def get_organization(self, org_id: str) -> Organization | None:
        rows = self._rest.select("organizations", {"org_id": f"eq.{org_id}", "limit": "1"})
        if not rows:
            return None
        return Organization(
            org_id=rows[0]["org_id"],
            name=rows[0]["name"],
            created_at=rows[0]["created_at"],
        )

    def add_member(self, member: OrganizationMember) -> None:
        self._rest.insert(
            "organization_members",
            [
                {
                    "org_id": member.org_id,
                    "user_id": member.user_id,
                    "role": member.role.value,
                    "created_at": member.created_at.isoformat(),
                }
            ],
            upsert=True,
        )

    def get_membership(self, user_id: str) -> OrganizationMember | None:
        rows = self._rest.select(
            "organization_members",
            {"user_id": f"eq.{user_id}", "order": "created_at.asc,org_id.asc", "limit": "1"},
        )
        return self._member(rows[0]) if rows else None

    def list_members(self, org_id: str) -> list[OrganizationMember]:
        return [
            self._member(row)
            for row in self._rest.select(
                "organization_members",
                {"org_id": f"eq.{org_id}", "order": "created_at.asc"},
            )
        ]

    # -- invitations --------------------------------------------------------- #
    # Table from infra/supabase/0005-org-invitations.sql.

    def create_invitation(self, invitation: OrgInvitation) -> None:
        self._rest.insert(
            "org_invitations",
            [
                {
                    "invite_id": invitation.invite_id,
                    "org_id": invitation.org_id,
                    "email": invitation.email,
                    "role": invitation.role.value,
                    "code": invitation.code,
                    "created_by": invitation.created_by,
                    "created_at": invitation.created_at.isoformat(),
                    "accepted_at": _iso(invitation.accepted_at),
                    "accepted_by": invitation.accepted_by,
                }
            ],
        )

    def list_invitations(self, org_id: str) -> list[OrgInvitation]:
        return [
            self._invitation(row)
            for row in self._rest.select(
                "org_invitations",
                {"org_id": f"eq.{org_id}", "order": "created_at.desc"},
            )
        ]

    def find_invitation_by_code(self, code: str) -> OrgInvitation | None:
        """Not org-scoped: the code is what names the org. See the protocol."""
        rows = self._rest.select(
            "org_invitations", {"code": f"eq.{code}", "limit": "1"}
        )
        return self._invitation(rows[0]) if rows else None

    def accept_invitation(self, invite_id: str, user_id: str, at: datetime) -> None:
        self._rest.update(
            "org_invitations",
            {"invite_id": f"eq.{invite_id}"},
            {"accepted_at": at.isoformat(), "accepted_by": user_id},
        )

    def delete_invitation(self, org_id: str, invite_id: str) -> bool:
        rows = self._rest.select(
            "org_invitations",
            {"invite_id": f"eq.{invite_id}", "org_id": f"eq.{org_id}", "limit": "1"},
        )
        if not rows:
            return False
        self._rest.delete(
            "org_invitations",
            {"invite_id": f"eq.{invite_id}", "org_id": f"eq.{org_id}"},
        )
        return True

    @staticmethod
    def _invitation(row: dict) -> OrgInvitation:
        return OrgInvitation(
            invite_id=row["invite_id"],
            org_id=row["org_id"],
            email=row["email"],
            role=OrgRole(row["role"]),
            code=row["code"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            accepted_at=row.get("accepted_at"),
            accepted_by=row.get("accepted_by"),
        )

    @staticmethod
    def _member(row: dict) -> OrganizationMember:
        return OrganizationMember(
            org_id=row["org_id"],
            user_id=row["user_id"],
            role=OrgRole(row["role"]),
            created_at=row["created_at"],
        )

    # -- cases -------------------------------------------------------------- #

    def create_case(self, org_id: str, case: CaseRecord) -> None:
        self._rest.insert(
            "cases",
            [
                {
                    "case_id": case.case_id,
                    "org_id": org_id,
                    "client_name": case.client_name,
                    "period_start": case.period_start.isoformat() if case.period_start else None,
                    "period_end": case.period_end.isoformat() if case.period_end else None,
                    "status": case.status.value,
                    "created_by": case.created_by,
                    "created_at": case.created_at.isoformat(),
                }
            ],
            upsert=True,
        )

    def get_case(self, org_id: str, case_id: str) -> CaseRecord | None:
        rows = self._rest.select(
            "cases", {"case_id": f"eq.{case_id}", "org_id": f"eq.{org_id}", "limit": "1"}
        )
        if not rows:
            return None
        row = rows[0]
        return CaseRecord(
            case_id=row["case_id"],
            client_name=row["client_name"],
            period_start=row.get("period_start"),
            period_end=row.get("period_end"),
            status=CaseStatus(row["status"]),
            created_by=row["created_by"],
            created_at=row["created_at"],
            # `status_detail` is application state, not a column: the Postgres
            # schema keeps `status` alone so the check constraint stays simple.
            status_detail=None,
        )

    def list_cases(self, org_id: str) -> list[CaseRecord]:
        return [
            CaseRecord(
                case_id=row["case_id"],
                client_name=row["client_name"],
                period_start=row.get("period_start"),
                period_end=row.get("period_end"),
                status=CaseStatus(row["status"]),
                created_by=row["created_by"],
                created_at=row["created_at"],
                status_detail=None,
            )
            for row in self._rest.select(
                "cases", {"org_id": f"eq.{org_id}", "order": "created_at.desc"}
            )
        ]

    def set_case_status(
        self, org_id: str, case_id: str, status: CaseStatus, detail: str | None = None
    ) -> None:
        self._rest.update(
            "cases",
            {"case_id": f"eq.{case_id}", "org_id": f"eq.{org_id}"},
            {"status": status.value},
        )

    def latest_case_id(self, org_id: str, created_by: str | None = None) -> str | None:
        params = {
            "org_id": f"eq.{org_id}",
            "order": "created_at.desc",
            "limit": "1",
            "select": "case_id",
        }
        if created_by:
            rows = self._rest.select("cases", {**params, "created_by": f"eq.{created_by}"})
            if rows:
                return rows[0]["case_id"]
        rows = self._rest.select("cases", params)
        return rows[0]["case_id"] if rows else None

    def update_case(
        self,
        org_id: str,
        case_id: str,
        *,
        client_name: str,
        period_start: date | None,
        period_end: date | None,
    ) -> CaseRecord | None:
        if self.get_case(org_id, case_id) is None:
            return None
        self._rest.update(
            "cases",
            {"case_id": f"eq.{case_id}", "org_id": f"eq.{org_id}"},
            {
                "client_name": client_name,
                "period_start": period_start.isoformat() if period_start else None,
                "period_end": period_end.isoformat() if period_end else None,
            },
        )
        return self.get_case(org_id, case_id)

    def delete_case(self, org_id: str, case_id: str) -> bool:
        if self.get_case(org_id, case_id) is None:
            return False
        # The working tables go with the case (the Postgres schema cascades on
        # the case row; the explicit deletes keep the two stores identical in
        # behaviour). The audit trail and any reports are not touched: they are
        # append-only evidence, and there is no delete path for them in this
        # class or in the database privileges.
        for table in (
            "flags",
            "review_items",
            "extractions",
            "documents",
            "benford_results",
            "sales_analytics",
        ):
            self._rest.delete(table, {"org_id": f"eq.{org_id}", "case_id": f"eq.{case_id}"})
        self._rest.delete("cases", {"case_id": f"eq.{case_id}", "org_id": f"eq.{org_id}"})
        return True

    # -- documents and extractions ------------------------------------------ #

    def add_documents(
        self, org_id: str, case_id: str, documents: list[StoredDocument], uploaded_by: str
    ) -> None:
        if not documents:
            return
        self._rest.insert(
            "documents",
            [
                {
                    "document_id": document.document_id,
                    "org_id": org_id,
                    "case_id": case_id,
                    "document_type": document.document_type.value,
                    "filename": document.filename,
                    "storage_path": document.storage_path,
                    "size_bytes": document.size_bytes,
                    "uploaded_by": uploaded_by,
                }
                for document in documents
            ],
            upsert=True,
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
            for row in self._rest.select(
                "documents",
                {
                    "case_id": f"eq.{case_id}",
                    "org_id": f"eq.{org_id}",
                    "order": "created_at.asc",
                },
            )
        ]

    def get_document(self, org_id: str, document_id: str) -> CaseDocument | None:
        rows = self._rest.select(
            "documents",
            {"document_id": f"eq.{document_id}", "org_id": f"eq.{org_id}", "limit": "1"},
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
        self._rest.insert(
            "extractions",
            [
                {
                    "document_id": result.document_id,
                    "org_id": org_id,
                    "case_id": case_id,
                    "model": result.model,
                    "needs_human_review": result.needs_human_review,
                    "payload": json.loads(result.model_dump_json()),
                }
            ],
            upsert=True,
        )

    def list_extractions(self, org_id: str, case_id: str) -> list[ExtractionResult]:
        return [
            ExtractionResult.model_validate(row["payload"])
            for row in self._rest.select(
                "extractions",
                {
                    "case_id": f"eq.{case_id}",
                    "org_id": f"eq.{org_id}",
                    "order": "created_at.asc",
                },
            )
        ]

    # -- review items ------------------------------------------------------- #

    def save_review_items(self, org_id: str, case_id: str, items: list[ReviewItem]) -> None:
        # Replacing the queue is safe: review items are derived output. The
        # audit trail, which is not derived, is never touched here.
        scope = {"case_id": f"eq.{case_id}", "org_id": f"eq.{org_id}"}
        self._rest.delete("flags", scope)
        self._rest.delete("review_items", scope)
        if not items:
            return

        self._rest.insert(
            "review_items",
            [
                {
                    "review_item_id": item.review_item_id,
                    "org_id": org_id,
                    "case_id": case_id,
                    "match_status": item.match.status.value,
                    "match_strength": item.match.match_strength.value,
                    "extraction_confidence": item.extraction_confidence.value,
                    "flag_count": len(item.flags),
                    "decision": item.decision.value,
                    "decided_by": item.decided_by,
                    "decided_at": _iso(item.decided_at),
                    "rejection_reason": item.rejection_reason,
                    "payload": json.loads(item.model_dump_json()),
                }
                for item in items
            ],
            upsert=True,
        )

        flags = [
            {
                "flag_id": flag.flag_id,
                "org_id": org_id,
                "case_id": case_id,
                "review_item_id": item.review_item_id,
                "rule_id": flag.rule_id,
                "severity": flag.severity.value,
                "explanation": flag.explanation,
                "source_row_id": flag.source_row_id,
                "payload": json.loads(flag.model_dump_json()),
            }
            for item in items
            for flag in item.flags
        ]
        if flags:
            self._rest.insert("flags", flags, upsert=True)

    def list_review_items(self, org_id: str, case_id: str) -> list[ReviewItem]:
        return [
            ReviewItem.model_validate(row["payload"])
            for row in self._rest.select(
                "review_items",
                {
                    "case_id": f"eq.{case_id}",
                    "org_id": f"eq.{org_id}",
                    "order": "review_item_id.asc",
                },
            )
        ]

    def get_review_item(self, org_id: str, review_item_id: str) -> ReviewItem | None:
        rows = self._rest.select(
            "review_items",
            {
                "review_item_id": f"eq.{review_item_id}",
                "org_id": f"eq.{org_id}",
                "limit": "1",
            },
        )
        return ReviewItem.model_validate(rows[0]["payload"]) if rows else None

    def update_review_item(self, org_id: str, item: ReviewItem) -> None:
        self._rest.update(
            "review_items",
            {"review_item_id": f"eq.{item.review_item_id}", "org_id": f"eq.{org_id}"},
            {
                "decision": item.decision.value,
                "decided_by": item.decided_by,
                "decided_at": _iso(item.decided_at),
                "rejection_reason": item.rejection_reason,
                "payload": json.loads(item.model_dump_json()),
            },
        )

    # -- benford ------------------------------------------------------------ #

    def save_benford(self, org_id: str, case_id: str, result: BenfordResult) -> None:
        self._rest.insert(
            "benford_results",
            [
                {
                    "case_id": case_id,
                    "org_id": org_id,
                    "payload": json.loads(result.model_dump_json()),
                }
            ],
            upsert=True,
        )

    def get_benford(self, org_id: str, case_id: str) -> BenfordResult | None:
        rows = self._rest.select(
            "benford_results",
            {"case_id": f"eq.{case_id}", "org_id": f"eq.{org_id}", "limit": "1"},
        )
        return BenfordResult.model_validate(rows[0]["payload"]) if rows else None

    # -- sales analytics ------------------------------------------------------ #
    # Table from infra/supabase/0006-sales-analytics.sql. Upsert on the
    # (org_id, case_id) primary key, so a re-run replaces the previous readout.

    def save_sales_analytics(
        self, org_id: str, case_id: str, result: SalesAnalyticsResult
    ) -> None:
        self._rest.insert(
            "sales_analytics",
            [
                {
                    "org_id": org_id,
                    "case_id": case_id,
                    "payload": json.loads(result.model_dump_json()),
                }
            ],
            upsert=True,
        )

    def get_sales_analytics(
        self, org_id: str, case_id: str
    ) -> SalesAnalyticsResult | None:
        rows = self._rest.select(
            "sales_analytics",
            {"case_id": f"eq.{case_id}", "org_id": f"eq.{org_id}", "limit": "1"},
        )
        return SalesAnalyticsResult.model_validate(rows[0]["payload"]) if rows else None

    # -- reports ------------------------------------------------------------ #
    # Table from infra/supabase/0006-reports-and-assistant.sql. Insert only:
    # the migration revokes UPDATE and DELETE from every role, service role
    # included, so there is nothing an `update_report` here could do.

    def save_report(self, org_id: str, record: ReportRecord) -> None:
        self._rest.insert(
            "reports",
            [
                {
                    "report_id": record.report_id,
                    "org_id": org_id,
                    "case_id": record.case_id,
                    "generated_by": record.generated_by,
                    "generated_at": record.generated_at.astimezone(timezone.utc).isoformat(),
                    "pdf_path": record.pdf_path,
                    "excel_path": record.excel_path,
                    "pdf_sha256": record.pdf_sha256,
                    "excel_sha256": record.excel_sha256,
                    "item_count": record.item_count,
                    "approved_count": record.approved_count,
                    "rejected_count": record.rejected_count,
                    "pending_count": record.pending_count,
                    "flag_count": record.flag_count,
                    "audit_record_count": record.audit_record_count,
                }
            ],
        )

    def list_reports(self, org_id: str, case_id: str) -> list[ReportRecord]:
        return [
            self._report(row)
            for row in self._rest.select(
                "reports",
                {
                    "case_id": f"eq.{case_id}",
                    "org_id": f"eq.{org_id}",
                    "order": "generated_at.desc,report_id.desc",
                },
            )
        ]

    def get_report(self, org_id: str, report_id: str) -> ReportRecord | None:
        rows = self._rest.select(
            "reports",
            {"report_id": f"eq.{report_id}", "org_id": f"eq.{org_id}", "limit": "1"},
        )
        return self._report(rows[0]) if rows else None

    @staticmethod
    def _report(row: dict) -> ReportRecord:
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

    # -- api keys ----------------------------------------------------------- #

    def create_api_key(self, key: ApiKeyRecord) -> None:
        self._rest.insert(
            "api_keys",
            [
                {
                    "key_id": key.key_id,
                    "org_id": key.org_id,
                    "created_by": key.created_by,
                    "name": key.name,
                    "key_prefix": key.key_prefix,
                    "key_hash": key.key_hash,
                    "scopes": [scope.value for scope in key.scopes],
                    "last_used_at": _iso(key.last_used_at),
                    "revoked_at": _iso(key.revoked_at),
                    "created_at": key.created_at.isoformat(),
                }
            ],
        )

    def list_api_keys(self, org_id: str) -> list[ApiKeyRecord]:
        return [
            self._api_key(row)
            for row in self._rest.select(
                "api_keys", {"org_id": f"eq.{org_id}", "order": "created_at.desc"}
            )
        ]

    def get_api_key(self, org_id: str, key_id: str) -> ApiKeyRecord | None:
        rows = self._rest.select(
            "api_keys", {"key_id": f"eq.{key_id}", "org_id": f"eq.{org_id}", "limit": "1"}
        )
        return self._api_key(rows[0]) if rows else None

    def find_api_key_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        """Not org-scoped, because this is what decides the org. See the protocol."""
        rows = self._rest.select("api_keys", {"key_hash": f"eq.{key_hash}", "limit": "1"})
        return self._api_key(rows[0]) if rows else None

    def revoke_api_key(self, org_id: str, key_id: str, revoked_at: datetime) -> bool:
        existing = self.get_api_key(org_id, key_id)
        if existing is None:
            return False
        if existing.revoked_at is not None:
            # Already revoked; when it stopped working is a fact, and a second
            # call did not change it.
            return True
        self._rest.update(
            "api_keys",
            {"key_id": f"eq.{key_id}", "org_id": f"eq.{org_id}"},
            {"revoked_at": revoked_at.isoformat()},
        )
        return True

    def rename_api_key(self, org_id: str, key_id: str, name: str) -> bool:
        if self.get_api_key(org_id, key_id) is None:
            return False
        self._rest.update(
            "api_keys",
            {"key_id": f"eq.{key_id}", "org_id": f"eq.{org_id}"},
            {"name": name},
        )
        return True

    def delete_api_key(self, org_id: str, key_id: str) -> bool:
        if self.get_api_key(org_id, key_id) is None:
            # Missing and another org's key are refused the same way.
            return False
        self._rest.delete(
            "api_keys",
            {"key_id": f"eq.{key_id}", "org_id": f"eq.{org_id}"},
        )
        return True

    def touch_api_key(self, key_id: str, used_at: datetime) -> None:
        self._rest.update(
            "api_keys", {"key_id": f"eq.{key_id}"}, {"last_used_at": used_at.isoformat()}
        )

    @staticmethod
    def _api_key(row: dict) -> ApiKeyRecord:
        return ApiKeyRecord(
            key_id=row["key_id"],
            org_id=row["org_id"],
            created_by=row["created_by"],
            name=row["name"],
            key_prefix=row["key_prefix"],
            key_hash=row["key_hash"],
            scopes=row["scopes"],
            last_used_at=row.get("last_used_at"),
            revoked_at=row.get("revoked_at"),
            created_at=row["created_at"],
        )

    # -- user profiles ------------------------------------------------------- #
    # Table from infra/supabase/0004-user-profiles.sql.

    def get_user_profile(self, user_id: str) -> UserProfile | None:
        rows = self._rest.select(
            "user_profiles", {"user_id": f"eq.{user_id}", "limit": "1"}
        )
        if not rows:
            return None
        row = rows[0]

        def flag(column: str, default: bool) -> bool:
            value = row.get(column)
            return default if value is None else bool(value)

        return UserProfile(
            user_id=row["user_id"],
            full_name=row.get("full_name"),
            job_title=row.get("job_title"),
            phone=row.get("phone"),
            avatar=row.get("avatar"),
            gender=row.get("gender"),
            date_of_birth=row.get("date_of_birth"),
            location=row.get("location"),
            license_number=row.get("license_number"),
            language=row.get("language"),
            notify_case_ready=flag("notify_case_ready", True),
            notify_high_severity=flag("notify_high_severity", True),
            notify_weekly_digest=flag("notify_weekly_digest", False),
            updated_at=row.get("updated_at"),
        )

    def save_user_profile(self, profile: UserProfile) -> None:
        self._rest.insert(
            "user_profiles",
            [
                {
                    "user_id": profile.user_id,
                    "full_name": profile.full_name,
                    "job_title": profile.job_title,
                    "phone": profile.phone,
                    "avatar": profile.avatar,
                    "gender": profile.gender,
                    "date_of_birth": (
                        profile.date_of_birth.isoformat()
                        if profile.date_of_birth
                        else None
                    ),
                    "location": profile.location,
                    "license_number": profile.license_number,
                    "language": profile.language,
                    "notify_case_ready": profile.notify_case_ready,
                    "notify_high_severity": profile.notify_high_severity,
                    "notify_weekly_digest": profile.notify_weekly_digest,
                    "updated_at": _iso(profile.updated_at),
                }
            ],
            upsert=True,
        )

    # -- audit trail -------------------------------------------------------- #

    def append_audit(self, org_id: str, record: AuditRecord) -> None:
        """Insert one audit record. The only write this class makes to the trail."""
        self._rest.insert(
            "audit_trail",
            [
                {
                    "audit_id": record.audit_id,
                    "org_id": org_id,
                    "case_id": record.case_id,
                    "actor_type": record.actor_type.value,
                    "actor_id": record.actor_id,
                    "action": record.action.value,
                    "item_id": record.item_id,
                    "detail": record.detail,
                    "occurred_at": record.occurred_at.astimezone(timezone.utc).isoformat(),
                }
            ],
        )

    def list_audit(
        self, org_id: str, case_id: str, item_id: str | None = None
    ) -> list[AuditRecord]:
        params = {
            "case_id": f"eq.{case_id}",
            "org_id": f"eq.{org_id}",
            "order": "occurred_at.asc",
        }
        if item_id:
            params["item_id"] = f"eq.{item_id}"
        return [
            AuditRecord(
                audit_id=row["audit_id"],
                case_id=row["case_id"],
                actor_type=row["actor_type"],
                actor_id=row["actor_id"],
                action=row["action"],
                item_id=row.get("item_id"),
                detail=row.get("detail"),
                occurred_at=row["occurred_at"],
            )
            for row in self._rest.select("audit_trail", params)
        ]
