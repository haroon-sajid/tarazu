"""The case pipeline: upload → extract → match → flag → persist review items.

App-level orchestration, per [ADR 0001](../../docs/decisions/0001-http-routers-live-in-app-api.md).
It calls each module's `service.py` and nothing else, and it contains no
matching, no rule logic, and no arithmetic over amounts. Composing three
modules is all it does.

**`matching/` and `rules/` are owned by Dev-D and are not implemented yet.**
This module calls them for real. When they raise `NotImplementedError` the case
is parked at `awaiting_matching` with its extractions saved, and the API says so
plainly rather than inventing results. The moment those two functions land, the
same code path completes with no change here.

Benford comes from `rules/` too, through an optional interface: if
`rules.service` exposes `benford_analysis(ledger)`, the pipeline calls it and
stores the result for the dashboard. Until it does, the dashboard reports no
Benford rather than computing it here — first-digit analysis is deterministic
arithmetic over ledger amounts, and that belongs in `rules/`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.audit import Actor, record_action, record_actor_action, record_ai_action
from app.core.repository import CaseRepository, DocumentStore, StoredDocument
from app.modules.extraction import service as extraction
from app.modules.matching import service as matching
from app.modules.rules import service as rules
from app.shared.schemas import (
    ActorType,
    AuditAction,
    BankTransaction,
    BenfordResult,
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
)

__all__ = ["PipelineOutcome", "RULES_CONFIG", "run_pipeline"]

logger = logging.getLogger(__name__)

#: Rule configuration handed to `rules.service.evaluate_flags`. The approval
#: limits are the ones a Pakistani SME audit typically works to; they belong in
#: per-client config once there is more than one client.
RULES_CONFIG: dict[str, Any] = {
    "approval_limits": [50_000, 100_000, 500_000],
    "round_number_floor": 10_000,
    "date_tolerance_days": 3,
    "duplicate_window_days": 3,
    "near_limit_tolerance": 0.02,
}


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

    Returns:
        A `PipelineOutcome` describing how far it got. The caller turns that
        into an HTTP response; it never raises for an expected stopping point.
    """
    created_at = datetime.now(timezone.utc)
    repository.create_case(
        org_id,
        CaseRecord(
            case_id=case_id,
            client_name=client_name,
            status=CaseStatus.UPLOADED,
            created_by=actor.user_id,
            created_at=created_at,
        ),
    )
    record_actor_action(repository, org_id, case_id, actor, AuditAction.CASE_CREATED,
                        detail=f"{len(documents)} documents for {client_name}")

    outcome = PipelineOutcome(case_id=case_id, status=CaseStatus.UPLOADED)

    # -- 1. Store the bytes ------------------------------------------------- #
    stored: list[StoredDocument] = []
    for document, content in documents:
        storage.put(document.storage_path, content, _content_type(document.filename))
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
    ledger: list[LedgerEntry] = []
    bank: list[BankTransaction] = []
    invoices: list[Invoice] = []

    for document, content in documents:
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

    # -- 3. Match, deterministically ---------------------------------------- #
    try:
        matches = matching.run_matching(ledger, bank, invoices)
    except NotImplementedError as error:
        return _park(repository, org_id, outcome, CaseStatus.AWAITING_MATCHING, str(error))

    record_action(
        repository, org_id, case_id, ActorType.SYSTEM, "matching.service",
        AuditAction.MATCHING_COMPLETED,
        detail=f"{len(matches)} results over {len(ledger)} ledger rows",
    )

    # -- 4. Flag, deterministically ----------------------------------------- #
    try:
        flags = rules.evaluate_flags(ledger, matches, RULES_CONFIG)
    except NotImplementedError as error:
        return _park(repository, org_id, outcome, CaseStatus.AWAITING_MATCHING, str(error))

    for flag in flags:
        record_action(
            repository, org_id, case_id, ActorType.SYSTEM, "rules.service",
            AuditAction.FLAG_RAISED, item_id=flag.source_row_id,
            detail=f"{flag.rule_id} ({flag.severity.value}): {flag.explanation}",
        )

    benford = _benford(ledger)
    if benford is not None:
        repository.save_benford(org_id, case_id, benford)

    # -- 5. Assemble and persist the review queue --------------------------- #
    items = build_review_items(case_id, ledger, bank, invoices, matches, flags,
                               outcome.extractions)
    repository.save_review_items(org_id, case_id, items)
    repository.set_case_status(org_id, case_id, CaseStatus.READY_FOR_REVIEW)

    outcome.review_items = items
    outcome.status = CaseStatus.READY_FOR_REVIEW
    return outcome


def _park(
    repository: CaseRepository,
    org_id: str,
    outcome: PipelineOutcome,
    status: CaseStatus,
    detail: str,
) -> PipelineOutcome:
    """Stop cleanly at a known gap, keeping everything already done."""
    logger.warning("Case %s parked at %s: %s", outcome.case_id, status.value, detail)
    repository.set_case_status(org_id, outcome.case_id, status, detail)
    outcome.status = status
    outcome.detail = detail
    return outcome


def _benford(ledger: list[LedgerEntry]) -> BenfordResult | None:
    """Ask `rules/` for the Benford analysis, if it offers one yet.

    First-digit analysis is deterministic arithmetic over ledger amounts, so it
    belongs in `rules/` beside every other deterministic test — not here. This
    calls an optional public function rather than reimplementing it at the app
    layer, and reports nothing until that function exists.

    The agreed signature is::

        def benford_analysis(ledger: list[LedgerEntry]) -> BenfordResult: ...
    """
    analyse = getattr(rules, "benford_analysis", None)
    if analyse is None:
        logger.info("rules.service has no benford_analysis yet; skipping Benford")
        return None
    try:
        return analyse(ledger)
    except NotImplementedError:
        return None


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


def _content_type(filename: str) -> str:
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
