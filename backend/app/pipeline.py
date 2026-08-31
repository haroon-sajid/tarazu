"""The case pipeline: upload → extract → match → flag → persist review items.

App-level orchestration, per [ADR 0001](../../docs/decisions/0001-http-routers-live-in-app-api.md).
It calls each module's `service.py` and nothing else, and it contains no
matching, no rule logic, and no arithmetic over amounts. Composing the
modules is all it does.

The three deterministic steps — `matching.run_matching`, `rules.evaluate_flags`,
and `rules.benford_analysis` — run on every upload. A fourth,
`analytics.analyze_sales`, runs when the upload includes a SALES_DATA
document: its readout is saved beside the Benford result, and a case without
sales data simply has none. A case that gets past extraction always ends
`ready_for_review`; if one of those steps fails the case is marked `failed`
with the reason, and the error is raised so the caller can report it, rather
than a half-built review queue being saved as if it were whole.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from app.core.audit import Actor, record_action, record_actor_action, record_ai_action
from app.core.repository import CaseRepository, DocumentStore, StoredDocument
from app.modules.analytics import service as analytics
from app.modules.extraction import service as extraction
from app.modules.matching import service as matching
from app.modules.rules import service as rules
from app.shared.schemas import (
    ActorType,
    AuditAction,
    BankTransaction,
    CaseRecord,
    CaseStatus,
    Confidence,
    DocumentType,
    ExtractionResult,
    Flag,
    Invoice,
    LedgerEntry,
    MatchResult,
    ReviewItem,
    SalesRecord,
)

__all__ = [
    "PipelineOutcome",
    "RULES_CONFIG",
    "content_type_for",
    "run_pipeline",
]

logger = logging.getLogger(__name__)

#: The rule configuration handed to `rules.service.evaluate_flags`: the module's
#: defaults, with any `RULES_*` environment overrides. Kept as a module-level
#: name because the API contract documents it; read once at import, like every
#: other setting in this process.
#:
#: This is the firm-wide fallback. A case that belongs to a client uses that
#: client's own thresholds instead (ADR 0005) — the caller passes them in as
#: `rules_config`, which is the change the ADR anticipated when it said the
#: configuration was "already a dictionary the pipeline passes in".
RULES_CONFIG: dict[str, Any] = rules.default_config()

#: Reported as the pipeline moves, so a queued upload can show a real stage
#: rather than a spinner. Presentation only: no result is read from it.
ProgressReporter = Callable[[int, str], None]


def _noop_progress(percent: int, step: str) -> None:
    """The default reporter: the pipeline runs the same either way."""


@dataclass
class PipelineOutcome:
    """What the pipeline managed to do, and where it stopped."""

    case_id: str
    status: CaseStatus
    documents: list[StoredDocument] = field(default_factory=list)
    extractions: list[ExtractionResult] = field(default_factory=list)
    ledger_entries: list[LedgerEntry] = field(default_factory=list)
    review_items: list[ReviewItem] = field(default_factory=list)
    detail: str | None = None

    @property
    def needs_human_review_count(self) -> int:
        return sum(1 for result in self.extractions if result.needs_human_review)


def run_pipeline(
    org_id: str,
    case_id: str,
    client_name: str,
    documents: list[tuple[StoredDocument, bytes]],
    actor: Actor,
    repository: CaseRepository,
    storage: DocumentStore,
    *,
    client_id: str | None = None,
    rules_config: dict[str, Any] | None = None,
    on_progress: ProgressReporter | None = None,
    create_case: bool = True,
) -> PipelineOutcome:
    """Run one case from uploaded bytes to a persisted review queue.

    Args:
        org_id: The organization (accounting firm) this case belongs to. Every
            row the pipeline writes — case, documents, extractions, review
            items, flags, Benford, and every audit record — is stamped with it,
            and nothing it writes is readable outside it.
        case_id: The case these documents belong to.
        client_name: Shown on the dashboard and the report.
        documents: Each uploaded document with its bytes.
        actor: Who uploaded these. `actor.user_id` is the accountable auditor
            and lands on `cases.created_by`; `actor.actor_type` and
            `actor.actor_id` are what the trail records, so an upload posted by
            an integration reads as `api-key:<prefix>` rather than as a person.
        repository: Where cases, extractions, and review items are persisted.
        storage: Where document bytes are persisted.
        client_id: The recurring client this period belongs to (ADR 0005), or
            None for a one-off engagement.
        rules_config: The red-flag thresholds to evaluate against. Defaults to
            the firm-wide `RULES_CONFIG`; a case belonging to a client is run
            with that client's own limits instead, which is what makes the
            rules the firm's rather than the product's.
        on_progress: Called as `(percent, step)` as the pipeline advances, so a
            queued upload can report a stage. Never influences a result.
        create_case: Whether to create the case row. False when the caller has
            already created it — the background path does, so that the case is
            visible and pollable the instant the upload request returns rather
            than only once the worker gets to it.

    Returns:
        A `PipelineOutcome` describing what was produced. Extraction errors
        propagate to the caller, which turns them into HTTP responses; a
        failure in a deterministic step marks the case `failed` and re-raises.
    """
    progress = on_progress or _noop_progress
    config = RULES_CONFIG if rules_config is None else rules_config
    created_at = datetime.now(timezone.utc)
    if create_case:
        repository.create_case(
            org_id,
            CaseRecord(
                case_id=case_id,
                client_name=client_name,
                client_id=client_id,
                status=CaseStatus.UPLOADED,
                created_by=actor.user_id,
                created_at=created_at,
            ),
        )
    record_actor_action(repository, org_id, case_id, actor, AuditAction.CASE_CREATED,
                        detail=f"{len(documents)} documents for {client_name}")

    outcome = PipelineOutcome(case_id=case_id, status=CaseStatus.UPLOADED)

    # -- 1. Store the bytes ------------------------------------------------- #
    progress(5, f"Storing {len(documents)} documents")
    stored: list[StoredDocument] = []
    for document, content in documents:
        storage.put(document.storage_path, content, content_type_for(document.filename))
        stored.append(document)
        record_actor_action(
            repository, org_id, case_id, actor, AuditAction.DOCUMENT_UPLOADED,
            item_id=document.document_id,
            detail=f"{document.document_type.value}: {document.filename}",
        )
    repository.add_documents(org_id, case_id, stored, actor.user_id)
    outcome.documents = stored

    # -- 2. Extract --------------------------------------------------------- #
    repository.set_case_status(org_id, case_id, CaseStatus.EXTRACTING)
    progress(15, "Reading documents")
    ledger: list[LedgerEntry] = []
    bank: list[BankTransaction] = []
    invoices: list[Invoice] = []
    sales: list[SalesRecord] = []

    total_documents = max(1, len(documents))
    for index, (document, content) in enumerate(documents, start=1):
        # 15% → 65% across the documents, so a 40-invoice case still moves.
        progress(
            15 + int(50 * (index - 1) / total_documents),
            f"Reading {document.filename}",
        )
        if document.document_type is DocumentType.LEDGER:
            # No AI on this path. A spreadsheet is already structured.
            ledger.extend(
                extraction.read_ledger(document.document_id, document.filename, content)
            )
            record_action(
                repository, org_id, case_id, ActorType.SYSTEM, "pandas",
                AuditAction.EXTRACTION_COMPLETED, item_id=document.document_id,
                detail=f"{len(ledger)} ledger rows read with pandas, no model involved",
            )
            continue

        if document.document_type is DocumentType.SALES_DATA:
            # No AI on this path either, for the same reason: the export is
            # already structured. The analysis happens in step 3-5 below, once
            # every sales document has been read.
            sales.extend(
                analytics.read_sales_data(document.document_id, document.filename, content)
            )
            record_action(
                repository, org_id, case_id, ActorType.SYSTEM, "pandas",
                AuditAction.EXTRACTION_COMPLETED, item_id=document.document_id,
                detail=f"{len(sales)} sales rows read with pandas, no model involved",
            )
            continue

        if document.document_type is DocumentType.BANK_STATEMENT and (
            extraction.statement_is_a_spreadsheet(document.filename)
        ):
            # The same reasoning as the ledger, applied to the riskiest document
            # in the case. Every Pakistani bank exports the statement as CSV or
            # Excel from internet banking, and a statement read by pandas has no
            # extraction confidence to weigh, no model to be unavailable, and no
            # page to be misread — so when the machine-readable form exists, the
            # vision model is the wrong tool.
            rows = extraction.read_bank_statement(
                document.document_id, document.filename, content
            )
            bank.extend(rows)
            record_action(
                repository, org_id, case_id, ActorType.SYSTEM, "pandas",
                AuditAction.EXTRACTION_COMPLETED, item_id=document.document_id,
                detail=(
                    f"{len(rows)} bank transactions read with pandas from "
                    f"{document.filename}, no model involved"
                ),
            )
            continue

        result = extraction.extract_document(
            document.document_id, document.document_type, document.filename, content
        )
        repository.save_extraction(org_id, case_id, result)
        outcome.extractions.append(result)
        bank.extend(extraction.bank_transactions_from(result))
        invoices.extend(extraction.invoices_from(result))

        record_ai_action(
            repository, org_id, case_id, result.model, AuditAction.EXTRACTION_COMPLETED,
            item_id=document.document_id,
            detail=f"{len(result.fields)} fields, {len(result.rows)} rows",
        )
        if result.second_opinion and result.second_opinion.ran:
            record_ai_action(
                repository, org_id, case_id, result.second_opinion.model,
                AuditAction.SECOND_OPINION_COMPLETED, item_id=document.document_id,
                detail=(
                    "agrees"
                    if result.second_opinion.agrees
                    else f"disagrees on {len(result.second_opinion.disagreements)} field(s); "
                         "escalated to a human"
                ),
            )

    outcome.ledger_entries = ledger

    # -- 3-5. Match, flag, and assemble — all deterministic ------------------ #
    repository.set_case_status(org_id, case_id, CaseStatus.MATCHING)
    progress(70, "Matching transactions")
    try:
        matches = matching.run_matching(ledger, bank, invoices)
        record_action(
            repository, org_id, case_id, ActorType.SYSTEM, "matching.service",
            AuditAction.MATCHING_COMPLETED,
            detail=(
                f"{len(matches)} results over {len(ledger)} ledger rows, "
                f"{len(bank)} bank transactions, {len(invoices)} invoices"
            ),
        )

        progress(82, "Applying audit rules")
        flags = rules.evaluate_flags(
            ledger, matches, config, invoices=invoices, bank=bank
        )
        for flag in flags:
            record_action(
                repository, org_id, case_id, ActorType.SYSTEM, "rules.service",
                AuditAction.FLAG_RAISED, item_id=flag.source_row_id,
                detail=f"{flag.rule_id} ({flag.severity.value}): {flag.explanation}",
            )

        progress(90, "Running Benford analysis")
        repository.save_benford(org_id, case_id, rules.benford_analysis(ledger))

        if sales:
            # Deterministic like Benford, and saved beside it. The trail names
            # `analytics.service` as the actor, so a readout produced at upload
            # time reads differently from one a person re-ran through the API.
            sales_result = analytics.analyze_sales(sales)
            repository.save_sales_analytics(org_id, case_id, sales_result)
            record_action(
                repository, org_id, case_id, ActorType.SYSTEM, "analytics.service",
                AuditAction.SALES_ANALYTICS_RUN,
                detail=(
                    f"{sales_result.record_count} sales records over "
                    f"{len(sales_result.document_ids)} document(s): total revenue "
                    f"{sales_result.total_revenue}, "
                    f"{len(sales_result.anomalies)} anomalies"
                ),
            )

        progress(95, "Assembling the review queue")
        items = build_review_items(case_id, ledger, bank, invoices, matches, flags,
                                   outcome.extractions)
        repository.save_review_items(org_id, case_id, items)
    except Exception as error:
        # Nothing half-done is left looking whole: the case says it failed and
        # why, and the caller gets the error. The trail above still records
        # everything that did happen.
        detail = f"{type(error).__name__}: {error}"
        logger.exception("Case %s failed after extraction: %s", case_id, detail)
        repository.set_case_status(org_id, case_id, CaseStatus.FAILED, detail)
        outcome.status = CaseStatus.FAILED
        outcome.detail = detail
        raise

    repository.set_case_status(org_id, case_id, CaseStatus.READY_FOR_REVIEW)
    progress(100, f"{len(items)} items ready for review")
    outcome.review_items = items
    outcome.status = CaseStatus.READY_FOR_REVIEW
    return outcome


def build_review_items(
    case_id: str,
    ledger: list[LedgerEntry],
    bank: list[BankTransaction],
    invoices: list[Invoice],
    matches: list[MatchResult],
    flags: list[Flag],
    extractions: list[ExtractionResult],
) -> list[ReviewItem]:
    """Join deterministic output into the rows a human will decide on.

    Pure assembly: it looks up objects by id and attaches them. It computes no
    match, applies no rule, and changes no number.
    """
    ledger_by_id = {entry.ledger_row_id: entry for entry in ledger}
    bank_by_id = {row.bank_row_id: row for row in bank}
    invoice_by_id = {invoice.invoice_id: invoice for invoice in invoices}
    evidence_by_document = _evidence_index(extractions)

    flags_by_row: dict[str, list[Flag]] = {}
    for flag in flags:
        for row_id in {flag.source_row_id, *flag.related_row_ids}:
            flags_by_row.setdefault(row_id, []).append(flag)

    items: list[ReviewItem] = []
    for position, match in enumerate(matches, start=1):
        entry = ledger_by_id.get(match.ledger_row_id)
        if entry is None:
            logger.warning(
                "Match references unknown ledger row %s; skipping", match.ledger_row_id
            )
            continue

        transaction = bank_by_id.get(match.bank_row_id) if match.bank_row_id else None
        invoice = invoice_by_id.get(match.invoice_id) if match.invoice_id else None

        # Only the readings behind *this* item. Indexing by statement row rather
        # than by document is what stops a 40-transaction statement attaching all
        # 160 of its fields to every row it produced.
        evidence: list = []
        if transaction is not None:
            evidence.extend(evidence_by_document.get(transaction.bank_row_id, []))
        if invoice is not None:
            evidence.extend(evidence_by_document.get(invoice.invoice_id, []))

        items.append(
            ReviewItem(
                # Qualified by the case, because `POST
                # /v1/review-items/{id}/approve` names an item and nothing else.
                # A bare `RI-0001` is only unique within one case, so with two
                # cases open — the same firm's second engagement, or another
                # firm's entirely — that route would be ambiguous, and an
                # ambiguous approve is a decision recorded against the wrong row.
                review_item_id=f"{case_id}-RI-{position:04d}",
                case_id=case_id,
                ledger_entry=entry,
                bank_transaction=transaction,
                invoice=invoice,
                match=match,
                flags=flags_by_row.get(match.ledger_row_id, []),
                # The weakest reading behind this item. Deliberately separate
                # from match.match_strength, which no AI value influenced.
                extraction_confidence=_weakest(evidence),
                evidence=evidence,
            )
        )
    return items


def _evidence_index(extractions: list[ExtractionResult]) -> dict[str, list]:
    """Source id -> the fields read from it.

    Keyed two ways, matching how the deterministic modules refer back to a
    reading: document-level fields (an invoice's total) under the document id,
    which is also the `invoice_id`; and each statement row's fields under its
    `row_id`, which is also the `bank_row_id`.
    """
    index: dict[str, list] = {}
    for result in extractions:
        if result.fields:
            index.setdefault(result.document_id, []).extend(result.fields)
        for row in result.rows:
            index.setdefault(row.row_id, []).extend(row.fields)
    return index


def _weakest(evidence: list) -> Confidence:
    """The lowest confidence among the readings behind an item.

    An item resting on nothing the AI read — a ledger row with no counterpart —
    is `high`: pandas read that cell, and there is no reading uncertainty when
    no model was involved.
    """
    levels = {field.extraction_confidence for field in evidence}
    for level in (Confidence.LOW, Confidence.MEDIUM):
        if level in levels:
            return level
    return Confidence.HIGH


def content_type_for(filename: str) -> str:
    """The MIME type a stored document is served with, from its extension."""
    lowered = filename.lower()
    for suffix, content_type in (
        (".pdf", "application/pdf"),
        (".png", "image/png"),
        (".jpg", "image/jpeg"),
        (".jpeg", "image/jpeg"),
        (".webp", "image/webp"),
        (".csv", "text/csv"),
        (".xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        (".xls", "application/vnd.ms-excel"),
    ):
        if lowered.endswith(suffix):
            return content_type
    return "application/octet-stream"
