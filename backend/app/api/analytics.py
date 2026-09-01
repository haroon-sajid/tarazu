"""`/v1/cases/{case_id}/analytics` and `/v1/cases/{case_id}/sales-data`.

Sales analytics has its own data source: sales exports uploaded separately
from the audit documents. The analytics routes read those exports, compute a
deterministic readout with pandas, persist it per case, and hand it back as a
file on request. Uploading a sales export does not touch the audit pipeline —
it is analytical material, not evidence.

An upload is read once, immediately, before it is stored: a file the reader
cannot make sense of is refused on the spot with the reason, rather than
sitting in the case until a later run trips over it.
"""

from __future__ import annotations

import logging
import mimetypes
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status

from app.api.deps import Principal, get_repository, get_storage, require_read, require_write
from app.core.audit import record_actor_action
from app.core.repository import CaseRepository, DocumentStore
from app.modules.analytics import service as analytics
from app.shared.api import SalesDataUploadListResponse, SalesDataUploadResponse
from app.shared.schemas import AuditAction, SalesAnalyticsResult, SalesDataUpload

__all__ = ["router"]

router = APIRouter(tags=["analytics"])
logger = logging.getLogger(__name__)

#: What a sales export may look like — the reader's own list, so the API and
#: the module cannot disagree. The upload screen offers the same set.
SALES_DATA_SUFFIXES = analytics.SUPPORTED_SUFFIXES

#: Guards against a mis-selected file exhausting memory.
MAX_FILE_BYTES = 25 * 1024 * 1024

_EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _suffix(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[1].lower()


def _ensure_case_exists(
    repository: CaseRepository, org_id: str, case_id: str
) -> None:
    """Return quietly if the case is in the caller's org, else 404."""
    if repository.get_case(org_id, case_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No case with id {case_id!r}.",
        )


def _sales_uploads(
    repository: CaseRepository, org_id: str, case_id: str
) -> list[SalesDataUpload]:
    """The case's uploaded sales exports, or a 422 when there are none."""
    _ensure_case_exists(repository, org_id, case_id)
    uploads = repository.list_sales_data_uploads(org_id, case_id)
    if not uploads:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "This case has no sales data yet. Upload a sales export first: "
                "Excel, CSV, TSV, ODS, or JSON."
            ),
        )
    return uploads


def _to_response(upload: SalesDataUpload) -> SalesDataUploadResponse:
    return SalesDataUploadResponse(
        sales_data_id=upload.sales_data_id,
        case_id=upload.case_id,
        filename=upload.filename,
        size_bytes=upload.size_bytes,
        uploaded_by=upload.uploaded_by,
        uploaded_at=upload.uploaded_at,
    )


@router.post(
    "/cases/{case_id}/sales-data",
    response_model=SalesDataUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a sales export for a case",
)
async def upload_sales_data(
    case_id: str,
    file: UploadFile = File(
        ..., description="Sales export: Excel, CSV, TSV, ODS, or JSON"
    ),
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
    storage: DocumentStore = Depends(get_storage),
) -> SalesDataUploadResponse:
    """Store a sales export as a separate source for sales analytics.

    The file is checked, read once to prove the reader can make sense of it,
    then stored and tracked in its own table; it never becomes a case document.
    After uploading, `POST /analytics` produces the readout — the upload screen
    does that automatically.
    """
    _ensure_case_exists(repository, principal.org_id, case_id)

    if _suffix(file.filename) not in SALES_DATA_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"{file.filename!r} is not a supported sales data file. "
                f"Allowed: {', '.join(sorted(SALES_DATA_SUFFIXES))}"
            ),
        )

    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{file.filename!r} is larger than {MAX_FILE_BYTES // 1024 // 1024} MB.",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{file.filename!r} is empty.",
        )

    sales_data_id = f"SLS-{uuid4().hex[:8]}"
    filename = file.filename or "unnamed"

    # Read it now, so a file the reader cannot use is refused with the reason
    # instead of being stored and failing every later run.
    try:
        analytics.read_sales_export(sales_data_id, filename, content)
    except analytics.SalesReadError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The sales data could not be read: {error}",
        ) from error

    storage_path = f"{case_id}/sales-data/{sales_data_id}/{filename}"
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    storage.put(storage_path, content, content_type)

    upload = SalesDataUpload(
        sales_data_id=sales_data_id,
        org_id=principal.org_id,
        case_id=case_id,
        filename=filename,
        size_bytes=len(content),
        storage_path=storage_path,
        uploaded_by=principal.user_id,
        uploaded_at=datetime.now(timezone.utc),
    )
    repository.add_sales_data_upload(principal.org_id, case_id, upload)
    return _to_response(upload)


@router.get(
    "/cases/{case_id}/sales-data",
    response_model=SalesDataUploadListResponse,
    summary="List the sales exports uploaded for a case",
)
async def list_sales_data(
    case_id: str,
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> SalesDataUploadListResponse:
    """Every sales export uploaded to the case, newest first."""
    _ensure_case_exists(repository, principal.org_id, case_id)
    uploads = repository.list_sales_data_uploads(principal.org_id, case_id)
    return SalesDataUploadListResponse(uploads=[_to_response(upload) for upload in uploads])


@router.delete(
    "/cases/{case_id}/sales-data/{sales_data_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Remove a sales export from a case",
)
async def delete_sales_data(
    case_id: str,
    sales_data_id: str,
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
) -> None:
    """Remove a sales export from the case.

    The stored bytes are not deleted from the underlying store; removing the
    metadata is enough to stop the analysis from reading them. Re-running the
    analysis after deletion recomputes from the remaining exports.
    """
    _ensure_case_exists(repository, principal.org_id, case_id)
    found = repository.get_sales_data_upload(principal.org_id, sales_data_id)
    if found is None or found.case_id != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No sales data upload {sales_data_id!r} for this case.",
        )
    repository.delete_sales_data_upload(principal.org_id, sales_data_id)


@router.post(
    "/cases/{case_id}/analytics",
    response_model=SalesAnalyticsResult,
    status_code=status.HTTP_201_CREATED,
    summary="Run the sales analytics for a case and save the result",
)
async def run_sales_analytics(
    case_id: str,
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
    storage: DocumentStore = Depends(get_storage),
) -> SalesAnalyticsResult:
    """Re-read the case's sales exports and compute the readout from scratch.

    Every sales export in the case is read — several exports are concatenated
    in upload order, so a month split across two files still sums whole. The
    result replaces whatever an earlier run saved, carries one data-quality
    report per file, and the run is recorded in the case's trail with the
    counts behind it.
    """
    uploads = _sales_uploads(repository, principal.org_id, case_id)

    records = []
    reports = []
    for upload in reversed(uploads):  # the list is newest first; read in upload order
        try:
            content = storage.get(upload.storage_path)
        except Exception as error:  # noqa: BLE001 - a missing file is a 404, whatever raised
            logger.warning(
                "Sales data upload %s is missing from storage: %s",
                upload.sales_data_id,
                error,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"The sales data file {upload.filename!r} is no longer in "
                    "storage. Upload it again."
                ),
            ) from error
        try:
            file_records, report = analytics.read_sales_export(
                upload.sales_data_id, upload.filename, content
            )
        except analytics.SalesReadError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"The sales data in {upload.filename!r} could not be read: {error}",
            ) from error
        records.extend(file_records)
        reports.append(report)

    result = analytics.analyze_sales(records, reports)
    repository.save_sales_analytics(principal.org_id, case_id, result)
    record_actor_action(
        repository,
        principal.org_id,
        case_id,
        principal.actor,
        AuditAction.SALES_ANALYTICS_RUN,
        detail=(
            f"{result.record_count} sales records over {len(uploads)} "
            f"file(s): total revenue {result.total_revenue}, "
            f"{len(result.anomalies)} anomalies, "
            f"{sum(report.rows_skipped for report in reports)} row(s) skipped"
        ),
    )
    return result


@router.get(
    "/cases/{case_id}/analytics",
    response_model=SalesAnalyticsResult,
    summary="The saved sales-analytics result for a case",
)
async def get_sales_analytics(
    case_id: str,
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> SalesAnalyticsResult:
    """The readout exactly as it was saved. Computes nothing, reads no files.

    `404` until the analysis has been run by `POST /v1/cases/{case_id}/analytics`.
    """
    _ensure_case_exists(repository, principal.org_id, case_id)
    result = repository.get_sales_analytics(principal.org_id, case_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No sales analytics for case {case_id!r} yet. Run them at "
                f"POST /v1/cases/{case_id}/analytics."
            ),
        )
    return result


@router.get(
    "/cases/{case_id}/analytics/download",
    summary="Download the saved sales-analytics readout as a file",
    response_class=Response,
)
async def download_sales_analytics(
    case_id: str,
    format: Literal["xlsx", "json"] = Query(
        default="xlsx",
        description="`xlsx` for a workbook with one sheet per breakdown; `json` for the readout as saved.",
    ),
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> Response:
    """The saved readout as a file. Nothing is recomputed: the workbook copies
    the persisted figures sheet by sheet — summary, monthly revenue, products,
    regions, top customers, anomalies, and the data-quality report of every
    export — and the JSON is the readout exactly as `GET` returns it.
    """
    _ensure_case_exists(repository, principal.org_id, case_id)
    result = repository.get_sales_analytics(principal.org_id, case_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No sales analytics for case {case_id!r} yet; nothing to download.",
        )

    stem = f"tarazu-{case_id}-sales-analytics"
    if format == "json":
        return Response(
            content=result.model_dump_json(indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{stem}.json"'},
        )
    return Response(
        content=analytics.export_workbook(result),
        media_type=_EXCEL_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{stem}.xlsx"'},
    )
