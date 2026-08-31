"""`POST /v1/upload` — accept three documents and run the case through the pipeline.

The route validates what arrived and hands it to `app.pipeline`. It contains no
extraction, matching, or rule logic: everything below the validation is one call.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.deps import Principal, get_repository, get_storage, require_write
from app.core.repository import CaseRepository, DocumentStore, StoredDocument
from app.modules.extraction.service import ExtractionError, LedgerReadError, QwenError
from app.pipeline import run_pipeline
from app.shared.api import UploadResponse
from app.shared.schemas import CaseStatus, DocumentType

router = APIRouter(tags=["upload"])
logger = logging.getLogger(__name__)

#: What each slot will accept. The frontend enforces the same list client-side.
ACCEPTED_SUFFIXES: dict[DocumentType, frozenset[str]] = {
    DocumentType.BANK_STATEMENT: frozenset({".pdf"}),
    DocumentType.INVOICE: frozenset({".pdf", ".png", ".jpg", ".jpeg", ".webp"}),
    DocumentType.LEDGER: frozenset({".xlsx", ".xlsm", ".xls", ".csv"}),
}

#: Guards against a mis-selected file exhausting memory or the model's context.
MAX_FILE_BYTES = 25 * 1024 * 1024


def _suffix(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[1].lower()


def _accept(
    upload: UploadFile, document_type: DocumentType, case_id: str
) -> tuple[StoredDocument, bytes]:
    """Validate one uploaded file and read its bytes."""
    allowed = ACCEPTED_SUFFIXES[document_type]
    if _suffix(upload.filename) not in allowed:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"{upload.filename!r} is not accepted as a {document_type.value}. "
                f"Allowed: {', '.join(sorted(allowed))}"
            ),
        )

    content = upload.file.read()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{upload.filename!r} is larger than {MAX_FILE_BYTES // 1024 // 1024} MB.",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{upload.filename!r} is empty.",
        )

    prefix = {
        DocumentType.BANK_STATEMENT: "DOC-BNK",
        DocumentType.INVOICE: "DOC-INV",
        DocumentType.LEDGER: "DOC-LED",
    }[document_type]
    document_id = f"{prefix}-{uuid4().hex[:8]}"
    filename = upload.filename or "unnamed"
    document = StoredDocument(
        document_id=document_id,
        document_type=document_type,
        filename=filename,
        size_bytes=len(content),
        storage_path=f"{case_id}/{document_id}/{filename}",
    )
    return document, content


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a bank statement, invoices, and a ledger, and process them",
)
async def upload_documents(
    bank_statement: UploadFile = File(..., description="Bank statement PDF"),
    ledger: UploadFile = File(..., description="Ledger, Excel or CSV"),
    invoices: list[UploadFile] = File(..., description="One or more invoice PDFs or images"),
    client_name: str = Form("Haroon Textiles", description="The audited client"),
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
    storage: DocumentStore = Depends(get_storage),
) -> UploadResponse:
    """Store the documents, extract them, match, flag, and save the review queue.

    The case is opened inside the caller's organization. Nothing it produces is
    visible to any other firm, and the case id is never reused across firms.

    An integration holding a `write` key can post here — a nightly job that
    drops last month's statement, ledger, and invoices in. The case is created
    by the auditor whose key it is, and the trail says the upload arrived from
    `api-key:<prefix>`.
    """
    if not invoices:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one invoice is required.",
        )

    case_id = f"CASE-{uuid4().hex[:10]}"
    documents = [
        _accept(bank_statement, DocumentType.BANK_STATEMENT, case_id),
        _accept(ledger, DocumentType.LEDGER, case_id),
        *(_accept(invoice, DocumentType.INVOICE, case_id) for invoice in invoices),
    ]

    try:
        outcome = run_pipeline(
            principal.org_id, case_id, client_name, documents, principal.actor,
            repository, storage,
        )
    except LedgerReadError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The ledger could not be read: {error}",
        ) from error
    except QwenError as error:
        logger.exception("Extraction failed for case %s", case_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"The document reader is unavailable: {error}. "
                "Set DEMO_MODE=true to run on cached extractions."
            ),
        ) from error
    except ExtractionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except Exception as error:  # noqa: BLE001 - a deterministic step failed
        # The pipeline has already marked the case `failed` with the reason and
        # logged the traceback; the caller gets a plain statement of it.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"The case could not be processed: {error}",
        ) from error

    return UploadResponse(
        case_id=outcome.case_id,
        documents=outcome.documents,
        status=outcome.status,
        review_item_count=len(outcome.review_items),
        needs_human_review_count=outcome.needs_human_review_count,
        message=_message(outcome.status, outcome.detail, len(outcome.review_items)),
    )


def _message(status_: CaseStatus, detail: str | None, item_count: int) -> str:
    if status_ is CaseStatus.READY_FOR_REVIEW:
        return f"{item_count} item{'s are' if item_count != 1 else ' is'} ready for review."
    if detail:
        return f"Case is {status_.value}: {detail}"
    return f"Case is {status_.value}."
