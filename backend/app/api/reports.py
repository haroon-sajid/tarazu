"""`/v1/reports` — generate the deliverable, list the history, download a file.

A report is a rendering of decided data. Generating one changes nothing about
the case: it reads the queue, the flags, Benford, and the trail, renders two
files, stores them, and appends an immutable `reports` row and a
`report_generated` trail entry. That is why a `read`-scoped key may generate
one — the monthly-report automation should not need a credential that can
approve items — and why the trail still records who did.

Reports are never updated or deleted. Regenerating after more decisions makes
a new row; the old file stays downloadable and its digest stays on record.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import (
    Principal,
    get_case_id,
    get_repository,
    get_storage,
    require_read,
    resolve_case_id,
)
from app.api.sign_offs import sign_off_state
from app.core.audit import record_actor_action
from app.core.repository import CaseRepository, DocumentStore
from app.modules.reports import service as reports
from app.modules.reports.content import ReportBranding
from app.shared.api import GenerateReportRequest, ReportListResponse, ReportSummary
from app.shared.schemas import (
    AssistantLanguage,
    AuditAction,
    CaseStatus,
    ReportFormat,
)

__all__ = ["router"]

router = APIRouter(tags=["reports"])
logger = logging.getLogger(__name__)

_MEDIA_TYPES = {
    ReportFormat.PDF: "application/pdf",
    ReportFormat.EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_EXTENSIONS = {ReportFormat.PDF: "pdf", ReportFormat.EXCEL: "xlsx"}


def _branding(repository: CaseRepository, org_id: str) -> ReportBranding | None:
    """The firm's letterhead for this report, or None for the plain heading.

    Read at generation time and baked into the file, deliberately: a report is
    evidence of what was delivered on a date, so changing the firm's logo next
    year must not change what last year's report looks like.
    """
    organization = repository.get_organization(org_id)
    profile = repository.get_org_profile(org_id)
    if organization is None and profile is None:
        return None
    return ReportBranding(
        firm_name=organization.name if organization else "Your firm",
        legal_name=profile.legal_name if profile else None,
        address=profile.address if profile else None,
        contact_email=profile.contact_email if profile else None,
        phone=profile.phone if profile else None,
        website=profile.website if profile else None,
        registration_number=profile.registration_number if profile else None,
        logo=profile.logo if profile else None,
        footer=profile.report_footer if profile else None,
    )


@router.post(
    "/reports",
    response_model=ReportSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Generate the PDF and Excel report for a case",
)
async def generate_report(
    body: GenerateReportRequest | None = None,
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
    storage: DocumentStore = Depends(get_storage),
) -> ReportSummary:
    """Render both files from the case as it stands, store them, and record it.

    Only items with an explicit human decision are reported as findings;
    pending items are counted and named as pending. The audit trail in the
    file is the trail up to the moment of generation — the `report_generated`
    entry this call appends is, necessarily, the first thing not in it.
    """
    case_id = resolve_case_id(repository, principal, body.case_id if body else None)
    case = repository.get_case(principal.org_id, case_id)
    assert case is not None  # resolve_case_id has just confirmed it

    # Maker-checker, where the firm has asked for it on this client. The gate
    # is here rather than in the UI because a report is the thing that leaves
    # the building: a client can be handed a PDF nobody senior ever looked at
    # only if the firm decided that is acceptable.
    required, satisfied = sign_off_state(repository, principal.org_id, case_id)
    if required and not satisfied:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This client requires a sign-off before a report can be generated. "
                "Have a colleague who did not decide these items sign the engagement "
                "off at POST /v1/sign-offs."
            ),
        )

    items = repository.list_review_items(principal.org_id, case_id)
    audit = repository.list_audit(principal.org_id, case_id)
    benford = repository.get_benford(principal.org_id, case_id)
    corrections = repository.list_corrections(principal.org_id, case_id)
    sign_offs = repository.list_sign_offs(principal.org_id, case_id)

    # The business owner's summary is written in the language their client
    # record says they read. A one-off engagement has no client and gets the
    # English report it always did.
    client = (
        repository.get_client(principal.org_id, case.client_id)
        if case.client_id
        else None
    )
    urdu = bool(client and client.language is AssistantLanguage.URDU)

    report_id = f"RPT-{uuid4().hex[:10]}"
    generated_at = datetime.now(timezone.utc)
    files = reports.generate_report(
        case, items, audit, benford,
        report_id=report_id, generated_by=principal.user_id, generated_at=generated_at,
        branding=_branding(repository, principal.org_id),
        corrections=corrections,
        sign_offs=sign_offs,
        urdu=urdu,
    )

    storage.put(files.record.pdf_path, files.pdf, _MEDIA_TYPES[ReportFormat.PDF])
    storage.put(files.record.excel_path, files.excel, _MEDIA_TYPES[ReportFormat.EXCEL])
    repository.save_report(principal.org_id, files.record)
    record_actor_action(
        repository, principal.org_id, case_id, principal.actor,
        AuditAction.REPORT_GENERATED, item_id=report_id,
        detail=(
            f"PDF and Excel over {files.record.item_count} items "
            f"({files.record.approved_count} approved, {files.record.rejected_count} "
            f"rejected, {files.record.pending_count} pending, not reported); "
            f"pdf sha256 {files.record.pdf_sha256[:12]}…"
        ),
    )
    # A case that has produced a deliverable is `reported`. The status moves
    # only forwards: a failed case is left saying so.
    if case.status not in (CaseStatus.FAILED, CaseStatus.REPORTED):
        repository.set_case_status(principal.org_id, case_id, CaseStatus.REPORTED)
    return ReportSummary.of(files.record)


@router.get(
    "/reports",
    response_model=ReportListResponse,
    summary="Every report generated for a case, newest first",
)
async def list_reports(
    case_id: str = Depends(get_case_id),
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> ReportListResponse:
    records = repository.list_reports(principal.org_id, case_id)
    return ReportListResponse(
        case_id=case_id,
        total=len(records),
        reports=[ReportSummary.of(record) for record in records],
    )


@router.get(
    "/cases/{case_id}/bundle",
    summary="Download the whole engagement as one verifiable zip",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
)
async def download_evidence_bundle(
    case_id: str,
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
    storage: DocumentStore = Depends(get_storage),
) -> Response:
    """Everything needed to defend the engagement, in one archive.

    The source documents, every generated report, the decided review queue, the
    corrections, the sign-offs, and the complete append-only trail — plus a
    `MANIFEST.txt` giving a SHA-256 for every file in the bundle. A firm hands
    this to a reviewer, a client, or a court, and each file in it can be shown
    to be the file that was made.

    The archive is byte-reproducible from the same inputs and export time, so
    two exports of an unchanged engagement are the same bytes and can be
    compared directly.

    A file missing from storage is skipped rather than failing the export: a
    bundle that is complete except for one unreadable document is worth far
    more than no bundle at all, and the manifest lists exactly what is in it.
    """
    case = repository.get_case(principal.org_id, case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No case with id {case_id!r}."
        )

    def _read(path: str, label: str) -> bytes | None:
        try:
            return storage.get(path)
        except Exception as error:  # noqa: BLE001 - a missing file is not fatal
            logger.warning("Bundle for %s: %s is unreadable: %s", case_id, label, error)
            return None

    documents: list[tuple[str, bytes]] = []
    for document in repository.list_documents(principal.org_id, case_id):
        content = _read(document.storage_path, document.filename)
        if content is not None:
            documents.append((document.filename, content))

    records = repository.list_reports(principal.org_id, case_id)
    report_files: list[tuple[str, bytes]] = []
    for record in records:
        for path, suffix in (
            (record.pdf_path, "pdf"),
            (record.excel_path, "xlsx"),
        ):
            content = _read(path, f"{record.report_id}.{suffix}")
            if content is not None:
                report_files.append((f"{record.report_id}.{suffix}", content))

    generated_at = datetime.now(timezone.utc)
    archive = reports.build_bundle(
        case,
        repository.list_review_items(principal.org_id, case_id),
        repository.list_audit(principal.org_id, case_id),
        records,
        repository.list_corrections(principal.org_id, case_id),
        repository.list_sign_offs(principal.org_id, case_id),
        documents,
        report_files,
        generated_by=principal.user_id,
        generated_at=generated_at,
    )

    record_actor_action(
        repository, principal.org_id, case_id, principal.actor,
        AuditAction.BUNDLE_EXPORTED,
        detail=(
            f"{len(documents)} document(s), {len(report_files)} report file(s), "
            f"{len(records)} report record(s); "
            f"zip sha256 {hashlib.sha256(archive).hexdigest()[:12]}…"
        ),
    )
    filename = f"tarazu-{case_id}-evidence-bundle.zip"
    return Response(
        content=archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/reports/{report_id}/download",
    summary="Download a generated report file",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}, _MEDIA_TYPES[ReportFormat.EXCEL]: {}}}},
)
async def download_report(
    report_id: str,
    format: ReportFormat = Query(default=ReportFormat.PDF, description="pdf or excel"),
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
    storage: DocumentStore = Depends(get_storage),
) -> Response:
    """The bytes exactly as generated. Another firm's report is `404`."""
    record = repository.get_report(principal.org_id, report_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No report with id {report_id!r}."
        )
    path = record.pdf_path if format is ReportFormat.PDF else record.excel_path
    try:
        content = storage.get(path)
    except Exception as error:  # noqa: BLE001 - a missing file is a 404, whatever raised
        logger.warning("Report file %s is missing from storage: %s", path, error)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The report's file is no longer in storage. Generate it again.",
        ) from error
    filename = f"tarazu-{record.case_id}-{record.report_id}.{_EXTENSIONS[format]}"
    return Response(
        content=content,
        media_type=_MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
