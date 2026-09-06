"""`POST /v1/upload` — accept documents and run the case through the pipeline.

The route validates the audit documents and hands them to `app.pipeline`. It
contains no extraction, matching, or rule logic: everything below the validation
is one call. Sales data exports are uploaded separately via the analytics routes;
they are analytical material, not audit evidence.

**Every file is read before a case exists.** The ledger and a spreadsheet
statement go through the same deterministic readers the pipeline uses; a PDF or
a photo is opened to prove it is one. A file that cannot be used is refused on
the spot with a `422` whose body carries a `ReadProblem` — which document, what
it held, what it lacked, what to do — and nothing is created: no case row, no
job, no half-read documents for the case list to show as stuck. The pipeline
reads the files again afterwards; both reads are deterministic, and the second
one is what the trail records.

Two ways to run the pipeline:

- **Synchronously** (the default). The pipeline finishes before the response is
  written, and the counts on it are final. This is what an integration polling
  for a finished case wants, and it is what every existing caller gets.
- **In the background** (`?background=true`). The case row is created, the work
  is queued, and the response carries a `job_id` to poll at `GET /v1/jobs/{id}`.
  Extraction over a real bank statement takes tens of seconds; a browser should
  not hold a request open for it, so this is what the upload screen uses.

Either way the pipeline is the same code doing the same work in the same order,
writing the same audit trail. The only difference is which thread it runs on.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from app.api.deps import Principal, get_repository, get_storage, require_write
from app.api.files import safe_filename, suffix_of
from app.api.problems import ProblemHTTPException, raise_for
from app.core import jobs
from app.core.repository import CaseRepository, DocumentStore, StoredDocument
from app.modules.extraction import service as extraction
from app.pipeline import RULES_CONFIG, PipelineError, run_pipeline
from app.shared import problems
from app.shared.api import UploadResponse
from app.shared.problems import ReadProblemError
from app.shared.schemas import (
    CaseRecord,
    CaseStatus,
    Client,
    DocumentType,
    JobKind,
    JobRecord,
    JobStatus,
)

router = APIRouter(tags=["upload"])
logger = logging.getLogger(__name__)

#: What each slot will accept. The frontend enforces the same list client-side.
#:
#: A bank statement may arrive as a PDF, which the vision model reads, or as
#: the CSV/Excel export every Pakistani bank offers from internet banking,
#: which pandas reads deterministically. Preferring the export where it exists
#: removes the extraction risk from the riskiest document in the case.
ACCEPTED_SUFFIXES: dict[DocumentType, frozenset[str]] = {
    DocumentType.BANK_STATEMENT: frozenset(
        {".pdf", ".csv", ".xlsx", ".xlsm", ".xls"}
    ),
    DocumentType.INVOICE: frozenset({".pdf", ".png", ".jpg", ".jpeg", ".webp"}),
    DocumentType.LEDGER: frozenset({".xlsx", ".xlsm", ".xls", ".csv"}),
}

#: Guards against a mis-selected file exhausting memory or the model's context.
MAX_FILE_BYTES = 25 * 1024 * 1024


def _accept(
    upload: UploadFile, document_type: DocumentType, case_id: str
) -> tuple[StoredDocument, bytes]:
    """Validate one uploaded file's name and size, and read its bytes.

    The name is made safe first (`safe_filename`): it becomes part of the
    storage path and of a download header, so it may not carry a directory,
    a control character, or more length than a filesystem takes.
    """
    allowed = ACCEPTED_SUFFIXES[document_type]
    slot = document_type.value
    filename = safe_filename(upload.filename)
    if suffix_of(filename) not in allowed:
        raise ProblemHTTPException(
            problems.unsupported_format(slot, filename, sorted(allowed)),
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    content = upload.file.read()
    if len(content) > MAX_FILE_BYTES:
        raise ProblemHTTPException(
            problems.too_large(
                slot, filename, len(content) / 1024 / 1024, MAX_FILE_BYTES // 1024 // 1024
            ),
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    if not content:
        raise ProblemHTTPException(problems.empty_upload(slot, filename))

    prefix = {
        DocumentType.BANK_STATEMENT: "DOC-BNK",
        DocumentType.INVOICE: "DOC-INV",
        DocumentType.LEDGER: "DOC-LED",
    }[document_type]
    document_id = f"{prefix}-{uuid4().hex[:8]}"
    document = StoredDocument(
        document_id=document_id,
        document_type=document_type,
        filename=filename,
        size_bytes=len(content),
        storage_path=f"{case_id}/{document_id}/{filename}",
    )
    return document, content


def _preflight(documents: list[tuple[StoredDocument, bytes]]) -> None:
    """Read every file now, so a bad one is refused before a case exists.

    The spreadsheets go through the readers the pipeline will use; a PDF or a
    photo is opened to prove it is one. The same bytes in the ledger and the
    statement slots are refused too — reconciling a file against itself would
    match every row and prove nothing.
    """
    by_type: dict[DocumentType, tuple[StoredDocument, bytes]] = {}
    for document, content in documents:
        slot = document.document_type.value
        by_type.setdefault(document.document_type, (document, content))
        try:
            if document.document_type is DocumentType.LEDGER:
                extraction.read_ledger(document.document_id, document.filename, content)
            elif document.document_type is DocumentType.BANK_STATEMENT and (
                extraction.statement_is_a_spreadsheet(document.filename)
            ):
                extraction.read_bank_statement(
                    document.document_id, document.filename, content
                )
            else:
                kind = "PDF" if document.filename.lower().endswith(".pdf") else "image"
                if extraction.document_page_count(content, document.filename) == 0:
                    raise ValueError(f"the {kind} has no pages")
        except ReadProblemError as error:
            raise raise_for(error) from error
        except ValueError as error:
            kind = "PDF" if document.filename.lower().endswith(".pdf") else "image"
            raise ProblemHTTPException(
                problems.unreadable_file(slot, document.filename, str(error), kind=kind)
            ) from error

    ledger = by_type.get(DocumentType.LEDGER)
    statement = by_type.get(DocumentType.BANK_STATEMENT)
    if ledger and statement and ledger[1] == statement[1]:
        raise ProblemHTTPException(
            problems.duplicate_file("ledger", "bank_statement", statement[0].filename)
        )


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload documents and process them through the pipeline",
)
async def upload_documents(
    bank_statement: UploadFile = File(..., description="Bank statement PDF"),
    ledger: UploadFile = File(..., description="Ledger, Excel or CSV"),
    invoices: list[UploadFile] = File(..., description="One or more invoice PDFs or images"),
    client_name: str = Form(
        "One-off engagement",
        description="Names the case when no recurring client is attached.",
    ),
    client_id: str | None = Form(
        default=None,
        description="Attach this period to a recurring client (ADR 0005).",
    ),
    background: bool = Query(
        default=False,
        description=(
            "Queue the processing and return a job_id to poll instead of "
            "waiting for it. The upload screen uses this; integrations that "
            "want the finished counts in the response should not."
        ),
    ),
    principal: Principal = Depends(require_write),
    repository: CaseRepository = Depends(get_repository),
    storage: DocumentStore = Depends(get_storage),
) -> UploadResponse:
    """Store the documents, extract them, match, flag, and save the review queue.

    The case is opened inside the caller's organization. Nothing it produces is
    visible to any other firm, and the case id is never reused across firms.

    With `client_id`, the case is one period of a recurring client and is
    evaluated against **that client's own rule thresholds** rather than the
    firm-wide defaults — the point of ADR 0005's client row, and what makes the
    flags the firm's rules instead of the product's.

    An integration holding a `write` key can post here — a nightly job that
    drops last month's statement, ledger, and invoices in. The case is created
    by the auditor whose key it is, and the trail says the upload arrived from
    `api-key:<prefix>`.

    A file that cannot be used is refused with `422` before anything is
    created; the body's `problem` says which file, what it held, what it
    lacked, and what to do.
    """
    if not invoices:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "At least one invoice is required: the ledger's payments are "
                "matched against the invoices they settle."
            ),
        )

    client = _resolve_client(repository, principal, client_id)
    if client is not None:
        # The client's name is the one on its record: a period that disagreed
        # with the client it belongs to would show two names for one business.
        client_name = client.name
    rules_config = client.rules.to_rules_config() if client else RULES_CONFIG

    case_id = f"CASE-{uuid4().hex[:10]}"
    documents = [
        _accept(bank_statement, DocumentType.BANK_STATEMENT, case_id),
        _accept(ledger, DocumentType.LEDGER, case_id),
        *(_accept(invoice, DocumentType.INVOICE, case_id) for invoice in invoices),
    ]
    _preflight(documents)

    if background:
        return _queue(
            repository, storage, principal, case_id, client_name,
            client.client_id if client else None, rules_config, documents,
        )

    try:
        outcome = run_pipeline(
            principal.org_id, case_id, client_name, documents, principal.actor,
            repository, storage,
            client_id=client.client_id if client else None,
            rules_config=rules_config,
        )
    except PipelineError as error:
        # The pipeline has already marked the case `failed` with the reason and
        # logged the traceback; the caller gets the same reason as a guide.
        raise ProblemHTTPException(error.problem) from error

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


def _resolve_client(
    repository: CaseRepository, principal: Principal, client_id: str | None
) -> Client | None:
    """The client this period belongs to, or None for a one-off engagement.

    Scoped like every other lookup: a `client_id` belonging to another firm is
    a `404`, indistinguishable from one that was never created. An archived
    client is refused too — a relationship that has ended should not quietly
    acquire new periods, and saying so is more useful than silently filing the
    work somewhere the auditor will not look for it.
    """
    if not client_id:
        return None
    client = repository.get_client(principal.org_id, client_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No client with id {client_id!r}. Pick a client from the list, "
                "or leave the client blank for a one-off engagement."
            ),
        )
    if not client.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Client {client.name!r} is archived. Restore it on the Clients "
                "screen before running a new period for it."
            ),
        )
    return client


def _queue(
    repository: CaseRepository,
    storage: DocumentStore,
    principal: Principal,
    case_id: str,
    client_name: str,
    client_id: str | None,
    rules_config: dict[str, Any],
    documents: list[tuple[StoredDocument, bytes]],
) -> UploadResponse:
    """Create the case, hand the work to the job runner, and answer at once.

    The case row is written **here**, on the request thread, rather than by the
    pipeline: the upload screen navigates to the case the moment this returns,
    and a case that did not exist yet would be a 404 in the half-second before
    a worker picked the job up. The pipeline is therefore called with
    `create_case=False` and finds its row already waiting.

    The uploaded bytes are already fully read into memory by `_accept`, so
    nothing here depends on the request's file handles, which FastAPI closes as
    soon as the response is written.
    """
    now = datetime.now(timezone.utc)
    repository.create_case(
        principal.org_id,
        CaseRecord(
            case_id=case_id,
            client_name=client_name,
            client_id=client_id,
            status=CaseStatus.UPLOADED,
            created_by=principal.user_id,
            created_at=now,
        ),
    )
    job = JobRecord(
        job_id=f"JOB-{uuid4().hex[:10]}",
        case_id=case_id,
        kind=JobKind.PIPELINE,
        status=JobStatus.QUEUED,
        progress=0,
        step="Queued",
        created_by=principal.user_id,
        created_at=now,
    )

    def work(progress: jobs.Progress) -> None:
        # A `PipelineError` carries its `problem`; the job runner records it,
        # so the upload screen polling the job shows the same guide a refused
        # upload gets.
        run_pipeline(
            principal.org_id, case_id, client_name, documents, principal.actor,
            repository, storage,
            client_id=client_id,
            rules_config=rules_config,
            on_progress=progress,
            create_case=False,
        )

    jobs.submit(repository, principal.org_id, job, work)
    logger.info("Queued job %s for case %s", job.job_id, case_id)

    # The job may already have finished — it runs inline in the test suite, and
    # a small case on a fast machine can beat the response out of the door — so
    # the state reported is read back rather than assumed.
    current = repository.get_job(principal.org_id, job.job_id) or job
    case = repository.get_case(principal.org_id, case_id)
    items = (
        repository.list_review_items(principal.org_id, case_id)
        if current.status is JobStatus.SUCCEEDED
        else []
    )
    return UploadResponse(
        case_id=case_id,
        documents=[document for document, _ in documents],
        status=case.status if case else CaseStatus.UPLOADED,
        review_item_count=len(items),
        needs_human_review_count=0,
        message=(
            f"{len(items)} item{'s are' if len(items) != 1 else ' is'} ready for review."
            if current.status is JobStatus.SUCCEEDED
            else "Processing started. Poll GET /v1/jobs/{job_id} for progress."
        ),
        job_id=job.job_id,
    )
