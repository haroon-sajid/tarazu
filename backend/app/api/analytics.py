"""`/v1/cases/{case_id}/analytics` — run the sales analytics, or read the saved one.

Sales analytics is deterministic pandas over a SALES_DATA document, exactly as
Benford is over the ledger: no model reads the export and no model scores the
result. The routes here are thin — resolve the case within the caller's
organization, hand the stored export bytes to `modules/analytics/`, persist the
readout, and put the run on the audit trail.

`POST` re-reads the stored export and re-runs the analysis, replacing whatever
the previous run saved. `GET` returns the saved readout without touching the
documents, so a dashboard can poll it for free. Both are scoped like every
other route: another firm's case is a `404`, indistinguishable from one that
never existed.

The trail records `sales_analytics_run` either way. The `actor_id` says who ran
it — a person, `api-key:<prefix>`, or `analytics.service` when the pipeline ran
it at upload time — which is what makes "who produced this number" answerable
months later.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import Principal, get_repository, get_storage, require_read, require_write
from app.core.audit import record_actor_action
from app.core.repository import CaseRepository, DocumentStore, StoredDocument
from app.modules.analytics import service as analytics
from app.shared.schemas import AuditAction, DocumentType, SalesAnalyticsResult

__all__ = ["router"]

router = APIRouter(tags=["analytics"])
logger = logging.getLogger(__name__)


def _sales_documents(
    repository: CaseRepository, org_id: str, case_id: str
) -> list[StoredDocument]:
    """The case's SALES_DATA documents, or a 422 when there are none.

    The case itself is checked first, so a case that does not exist — or
    belongs to another firm — stays a `404` rather than quietly becoming "no
    sales data", which would leak that the case exists.
    """
    if repository.get_case(org_id, case_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No case with id {case_id!r}.",
        )
    documents = [
        document
        for document in repository.list_documents(org_id, case_id)
        if document.document_type is DocumentType.SALES_DATA
    ]
    if not documents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Case {case_id!r} has no sales data document. Upload one "
                "(type sales_data) and run the analysis again."
            ),
        )
    return documents


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

    Every SALES_DATA document in the case is read — several exports are
    concatenated in document order, so a month split across two files still
    sums whole. The result replaces whatever an earlier run saved, and the run
    is recorded in the case's trail with the counts behind it.
    """
    documents = _sales_documents(repository, principal.org_id, case_id)

    records = []
    for document in documents:
        try:
            content = storage.get(document.storage_path)
        except Exception as error:  # noqa: BLE001 - a missing file is a 404, whatever raised
            logger.warning(
                "Sales document %s is missing from storage: %s",
                document.document_id,
                error,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"The sales document {document.filename!r} is no longer in "
                    "storage. Upload it again."
                ),
            ) from error
        try:
            records.extend(
                analytics.read_sales_data(
                    document.document_id, document.filename, content
                )
            )
        except analytics.SalesReadError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"The sales data could not be read: {error}",
            ) from error

    result = analytics.analyze_sales(records)
    repository.save_sales_analytics(principal.org_id, case_id, result)
    record_actor_action(
        repository,
        principal.org_id,
        case_id,
        principal.actor,
        AuditAction.SALES_ANALYTICS_RUN,
        detail=(
            f"{result.record_count} sales records over {len(documents)} "
            f"document(s): total revenue {result.total_revenue}, "
            f"{len(result.anomalies)} anomalies"
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

    `404` until the analysis has been run — by this route's `POST`, or at upload
    time by the pipeline.
    """
    if repository.get_case(principal.org_id, case_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No case with id {case_id!r}.",
        )
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
