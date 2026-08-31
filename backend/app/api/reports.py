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
from app.core.audit import record_actor_action
from app.core.repository import CaseRepository, DocumentStore
from app.modules.reports import service as reports
from app.shared.api import GenerateReportRequest, ReportListResponse, ReportSummary
from app.shared.schemas import AuditAction, ReportFormat

__all__ = ["router"]

router = APIRouter(tags=["reports"])
logger = logging.getLogger(__name__)

_MEDIA_TYPES = {
    ReportFormat.PDF: "application/pdf",
    ReportFormat.EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_EXTENSIONS = {ReportFormat.PDF: "pdf", ReportFormat.EXCEL: "xlsx"}


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
    items = repository.list_review_items(principal.org_id, case_id)
    audit = repository.list_audit(principal.org_id, case_id)
    benford = repository.get_benford(principal.org_id, case_id)

    report_id = f"RPT-{uuid4().hex[:10]}"
    generated_at = datetime.now(timezone.utc)
    files = reports.generate_report(
        case, items, audit, benford,
        report_id=report_id, generated_by=principal.user_id, generated_at=generated_at,
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
