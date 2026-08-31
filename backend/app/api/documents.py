"""`/v1/documents` — the uploaded files, and their pages as images.

The evidence viewer draws a provenance box on the page a value was read from.
Until now it drew that box on a schematic outline; these routes serve the
real page, rendered by the same PyMuPDF code path the vision model's page
images came from, so the coordinates line up with the pixels a human sees.

Every lookup is scoped to the caller's organization. A document id from
another firm is `404`, as everywhere else. Bytes are served through the
backend rather than by a public URL, because client documents must never be
world-readable — the store's bucket is private and stays that way.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import Principal, get_case_id, get_repository, get_storage, require_read
from app.core.repository import CaseDocument, CaseRepository, DocumentStore
from app.modules.extraction import service as extraction
from app.pipeline import content_type_for
from app.shared.api import DocumentListResponse, DocumentSummary
from app.shared.schemas import DocumentType

__all__ = ["router"]

router = APIRouter(tags=["documents"])
logger = logging.getLogger(__name__)

#: Render resolution for the viewer. Enough to read a statement's small print
#: on a normal screen; a fraction of the model's 200 dpi.
VIEWER_DPI = 110


def _summary(document, page_count: int | None, needs_review: bool) -> DocumentSummary:
    base = f"/v1/documents/{document.document_id}"
    return DocumentSummary(
        document_id=document.document_id,
        document_type=document.document_type,
        filename=document.filename,
        size_bytes=document.size_bytes,
        page_count=page_count,
        needs_human_review=needs_review,
        file_url=f"{base}/file",
        page_url_template=(
            None if document.document_type is DocumentType.LEDGER else f"{base}/pages/{{page}}"
        ),
    )


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="The documents uploaded to a case",
)
async def list_documents(
    case_id: str = Depends(get_case_id),
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> DocumentListResponse:
    documents = repository.list_documents(principal.org_id, case_id)
    extractions = {
        result.document_id: result
        for result in repository.list_extractions(principal.org_id, case_id)
    }
    summaries = []
    for document in documents:
        result = extractions.get(document.document_id)
        summaries.append(
            _summary(
                document,
                page_count=result.page_count if result else None,
                needs_review=bool(result and result.needs_human_review),
            )
        )
    return DocumentListResponse(case_id=case_id, total=len(summaries), documents=summaries)


def _require_document(
    repository: CaseRepository, principal: Principal, document_id: str
) -> CaseDocument:
    document = repository.get_document(principal.org_id, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No document with id {document_id!r}.",
        )
    return document


def _read(storage: DocumentStore, document: CaseDocument) -> bytes:
    try:
        return storage.get(document.storage_path)
    except Exception as error:  # noqa: BLE001 - missing bytes are a 404, whatever raised
        logger.warning("Document %s is missing from storage: %s", document.document_id, error)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The document's file is no longer in storage.",
        ) from error


@router.get(
    "/documents/{document_id}/file",
    summary="The original uploaded file",
    response_class=Response,
)
async def get_document_file(
    document_id: str,
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
    storage: DocumentStore = Depends(get_storage),
) -> Response:
    document = _require_document(repository, principal, document_id)
    content = _read(storage, document)
    return Response(
        content=content,
        media_type=content_type_for(document.filename),
        headers={"Content-Disposition": f'inline; filename="{document.filename}"'},
    )


@router.get(
    "/documents/{document_id}/pages/{page}",
    summary="One page of a document, rendered as an image",
    response_class=Response,
)
async def get_document_page(
    document_id: str,
    page: int,
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
    storage: DocumentStore = Depends(get_storage),
) -> Response:
    """A PNG of the page (or the photo itself), for the evidence viewer.

    Pages are 1-based, matching `Provenance.page`. The ledger has rows, not
    pages, and is `404` here; the viewer shows it as a sheet.
    """
    document = _require_document(repository, principal, document_id)
    if document.document_type is DocumentType.LEDGER:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The ledger is a spreadsheet: it has rows, not pages.",
        )
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Pages are numbered from 1."
        )
    content = _read(storage, document)
    try:
        image = extraction.render_document_page(content, document.filename, page, dpi=VIEWER_DPI)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return Response(
        content=image.content,
        media_type=image.mime_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )
