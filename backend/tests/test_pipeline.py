"""The pipeline: upload → extract → match → flag → persisted review queue.

These tests drive the real `matching/` and `rules/` modules over the real local
store. Extraction runs in `DEMO_MODE`, so nothing here touches the network, and
the only stand-in is the cached extraction fixture.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import pandas as pd
import pymupdf
import pytest

from app.core.audit import Actor
from app.core.config import DEFAULT_ORG_ID as ORG
from app.core.repository import StoredDocument
from app.core.sqlite_store import LocalDocumentStore, SqliteCaseRepository
from app.modules.matching import service as matching
from app.pipeline import build_review_items, run_pipeline
from app.shared.schemas import (
    AuditAction,
    CaseStatus,
    Confidence,
    DocumentType,
    ExtractedField,
    Flag,
    LedgerEntry,
    MatchResult,
    MatchStatus,
    MatchStrength,
    Provenance,
    Severity,
)

USER_ID = "00000000-0000-4000-8000-000000000001"
#: The auditor, signed in and acting as themselves. `test_api_keys.py` covers
#: the other kind of actor the pipeline accepts.
AUDITOR = Actor.human(USER_ID)


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #


def a_pdf(text: str = "STATEMENT") -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((72, 120), text, fontsize=16)
    data = document.tobytes()
    document.close()
    return data


def a_ledger() -> bytes:
    buffer = io.BytesIO()
    pd.DataFrame(
        {
            "Date": ["02/06/2026", "10/06/2026", "14/06/2026"],
            "Party Name": [
                "Gulberg Traders (Pvt) Ltd",
                "Al-Habib Stationers",
                "Indus Power Solutions",
            ],
            "Amount": [284000, 45900, 1500000],
            "Particulars": ["Yarn purchase", "Office supplies", "Generator advance"],
        }
    ).to_excel(buffer, index=False)
    return buffer.getvalue()


def documents(case_id: str) -> list[tuple[StoredDocument, bytes]]:
    return [
        (
            StoredDocument(
                document_id="DOC-BNK-001",
                document_type=DocumentType.BANK_STATEMENT,
                filename="statement.pdf",
                size_bytes=1,
                storage_path=f"{case_id}/DOC-BNK-001/statement.pdf",
            ),
            a_pdf(),
        ),
        (
            StoredDocument(
                document_id="DOC-LED-001",
                document_type=DocumentType.LEDGER,
                filename="ledger.xlsx",
                size_bytes=1,
                storage_path=f"{case_id}/DOC-LED-001/ledger.xlsx",
            ),
            a_ledger(),
        ),
        (
            StoredDocument(
                document_id="DOC-INV-0431",
                document_type=DocumentType.INVOICE,
                filename="invoice.pdf",
                size_bytes=1,
                storage_path=f"{case_id}/DOC-INV-0431/invoice.pdf",
            ),
            a_pdf("INVOICE"),
        ),
    ]


# --------------------------------------------------------------------------- #
# The full flow, over the real deterministic modules
# --------------------------------------------------------------------------- #


def test_the_full_flow_produces_a_persisted_review_queue(
    repository: SqliteCaseRepository, storage: LocalDocumentStore, demo_mode
) -> None:
    outcome = run_pipeline(
        ORG, "CASE-C", "Haroon Textiles", documents("CASE-C"), AUDITOR,
        repository, storage,
    )

    assert outcome.status is CaseStatus.READY_FOR_REVIEW
    assert len(outcome.review_items) == 3, "one review item per ledger row"

    persisted = repository.list_review_items(ORG, "CASE-C")
    assert len(persisted) == len(outcome.review_items)
    assert repository.get_case(ORG, "CASE-C").status is CaseStatus.READY_FOR_REVIEW


def test_live_uploads_no_longer_park(
    client, repository: SqliteCaseRepository, demo_mode
) -> None:
    """The acceptance criterion for finishing the core: nothing waits on a module."""
    response = client.post(
        "/v1/upload",
        files=[
            ("bank_statement", ("statement.pdf", io.BytesIO(a_pdf()))),
            ("ledger", ("ledger.xlsx", io.BytesIO(a_ledger()))),
            ("invoices", ("invoice.pdf", io.BytesIO(a_pdf("INVOICE")))),
        ],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ready_for_review"
    assert body["review_item_count"] == 3
    assert body["message"] == "3 items are ready for review."


def test_the_full_flow_records_every_stage_in_the_trail(
    repository: SqliteCaseRepository, storage: LocalDocumentStore, demo_mode
) -> None:
    run_pipeline(ORG, "CASE-D", "Client", documents("CASE-D"), AUDITOR, repository, storage)

    records = repository.list_audit(ORG, "CASE-D")
    actions = [record.action for record in records]
    assert AuditAction.CASE_CREATED in actions
    assert actions.count(AuditAction.DOCUMENT_UPLOADED) == 3
    assert AuditAction.EXTRACTION_COMPLETED in actions
    assert AuditAction.MATCHING_COMPLETED in actions
    # The round 1,500,000 posted on Sunday 14 June fires two rules.
    raised = [record for record in records if record.action is AuditAction.FLAG_RAISED]
    assert {record.detail.split(" ")[0] for record in raised} >= {
        "round-number", "weekend-entry"
    }
    assert all(record.actor_id == "rules.service" for record in raised)


def test_the_flags_on_the_queue_are_the_rules_output(
    repository: SqliteCaseRepository, storage: LocalDocumentStore, demo_mode
) -> None:
    outcome = run_pipeline(
        ORG, "CASE-G", "Client", documents("CASE-G"), AUDITOR, repository, storage
    )
    by_party = {item.ledger_entry.party_name: item for item in outcome.review_items}
    indus = by_party["Indus Power Solutions"]
    assert {flag.rule_id for flag in indus.flags} == {"round-number", "weekend-entry"}
    assert all(flag.source_row_id == indus.ledger_entry.ledger_row_id for flag in indus.flags)


def test_benford_is_computed_and_stored_for_a_new_case(
    repository: SqliteCaseRepository, storage: LocalDocumentStore, demo_mode
) -> None:
    run_pipeline(ORG, "CASE-H", "Client", documents("CASE-H"), AUDITOR, repository, storage)
    benford = repository.get_benford(ORG, "CASE-H")
    assert benford is not None
    assert benford.sample_size == 3
    assert [d.observed_count for d in benford.digits] == [1, 1, 0, 1, 0, 0, 0, 0, 0]


def test_the_ledger_is_read_by_pandas_and_recorded_as_such(
    repository: SqliteCaseRepository, storage: LocalDocumentStore, demo_mode
) -> None:
    """The trail should show plainly that no model touched the ledger."""
    outcome = run_pipeline(
        ORG, "CASE-E", "Client", documents("CASE-E"), AUDITOR, repository, storage
    )

    assert len(outcome.ledger_entries) == 3
    assert outcome.ledger_entries[0].party_name == "Gulberg Traders (Pvt) Ltd"
    assert outcome.ledger_entries[0].source.row_number == 2
    assert outcome.ledger_entries[0].source.page is None

    pandas_entries = [
        record
        for record in repository.list_audit(ORG, "CASE-E")
        if record.actor_id == "pandas"
    ]
    assert pandas_entries
    assert "no model involved" in pandas_entries[0].detail


def test_documents_are_stored(
    repository: SqliteCaseRepository, storage: LocalDocumentStore, demo_mode
) -> None:
    run_pipeline(ORG, "CASE-F", "Client", documents("CASE-F"), AUDITOR, repository, storage)
    stored = storage.get("CASE-F/DOC-LED-001/ledger.xlsx")
    assert stored[:2] == b"PK"  # an xlsx is a zip


def test_an_approve_after_a_real_pipeline_run_lands_in_the_trail(
    client, repository: SqliteCaseRepository, demo_mode
) -> None:
    """The acceptance criterion, over the real pipeline rather than a seed."""
    upload = client.post(
        "/v1/upload",
        files=[
            ("bank_statement", ("statement.pdf", io.BytesIO(a_pdf()))),
            ("ledger", ("ledger.xlsx", io.BytesIO(a_ledger()))),
            ("invoices", ("invoice.pdf", io.BytesIO(a_pdf("INVOICE")))),
        ],
    )
    assert upload.status_code == 201
    case_id = upload.json()["case_id"]

    items = client.get("/v1/review-items", params={"case_id": case_id}).json()["items"]
    assert items, "the pipeline should have produced a review queue"

    before = len(repository.list_audit(ORG, case_id))
    approve = client.post(
        f"/v1/review-items/{items[0]['review_item_id']}/approve", json={"note": "ok"}
    )
    assert approve.status_code == 200

    trail = repository.list_audit(ORG, case_id)
    assert len(trail) == before + 1
    assert trail[-1].action is AuditAction.ITEM_APPROVED
    assert trail[-1].actor_id == USER_ID


def test_a_failing_deterministic_step_marks_the_case_failed(
    repository: SqliteCaseRepository,
    storage: LocalDocumentStore,
    demo_mode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing half-done is saved as if it were whole."""

    def explode(*_args, **_kwargs):
        raise RuntimeError("simulated matcher fault")

    monkeypatch.setattr(matching, "run_matching", explode)
    with pytest.raises(RuntimeError, match="simulated matcher fault"):
        run_pipeline(ORG, "CASE-X", "Client", documents("CASE-X"), AUDITOR, repository, storage)

    case = repository.get_case(ORG, "CASE-X")
    assert case.status is CaseStatus.FAILED
    assert "simulated matcher fault" in (case.status_detail or "")
    assert repository.list_review_items(ORG, "CASE-X") == []


# --------------------------------------------------------------------------- #
# Review-item assembly
# --------------------------------------------------------------------------- #


def a_ledger_entry(row_id: str = "LED-0001") -> LedgerEntry:
    return LedgerEntry(
        ledger_row_id=row_id,
        date=date(2026, 6, 2),
        amount=Decimal("284000"),
        party_name="Gulberg Traders (Pvt) Ltd",
        source=Provenance(document_id="DOC-LED-001", row_number=2),
    )


def test_assembly_attaches_flags_to_every_row_they_involve() -> None:
    """A structuring flag names two rows; both must show it."""
    ledger = [a_ledger_entry("LED-0014"), a_ledger_entry("LED-0015")]
    matches = [
        MatchResult(
            ledger_row_id=entry.ledger_row_id,
            status=MatchStatus.UNMATCHED,
            match_strength=MatchStrength.LOW,
            reason="No candidate.",
            rule_id="no-candidate-found",
        )
        for entry in ledger
    ]
    flags = [
        Flag(
            flag_id="FLG-0009",
            rule_id="structuring",
            severity=Severity.HIGH,
            explanation="Two payments under the limit on one day.",
            source_row_id="LED-0014",
            related_row_ids=["LED-0015"],
        )
    ]

    items = build_review_items("CASE-X", ledger, [], [], matches, flags, [])

    assert len(items) == 2
    assert all(item.flags for item in items)
    assert items[1].flags[0].rule_id == "structuring"


def test_assembly_never_invents_a_match_for_an_unknown_ledger_row() -> None:
    matches = [
        MatchResult(
            ledger_row_id="LED-DOES-NOT-EXIST",
            status=MatchStatus.UNMATCHED,
            match_strength=MatchStrength.LOW,
            reason="No candidate.",
            rule_id="no-candidate-found",
        )
    ]
    assert build_review_items("CASE-X", [a_ledger_entry()], [], [], matches, [], []) == []


def test_item_confidence_is_the_weakest_reading_behind_it() -> None:
    from app.shared.schemas import ExtractionResult, Invoice

    invoice = Invoice(
        invoice_id="DOC-INV-1",
        invoice_number="INV-1",
        date=date(2026, 6, 2),
        amount=Decimal("284000"),
        party_name="Gulberg Traders (Pvt) Ltd",
        source=Provenance(document_id="DOC-INV-1", page=1, text_snippet="284,000"),
    )
    extraction = ExtractionResult(
        document_id="DOC-INV-1",
        document_type=DocumentType.INVOICE,
        filename="inv.pdf",
        page_count=1,
        extracted_at=date(2026, 6, 2),
        model="qwen-vl-max",
        fields=[
            ExtractedField(
                field="party_name", value="Gulberg Traders (Pvt) Ltd",
                extraction_confidence=Confidence.HIGH,
                source=Provenance(document_id="DOC-INV-1", page=1, text_snippet="Gulberg"),
            ),
            ExtractedField(
                field="amount", value=284000.0,
                extraction_confidence=Confidence.LOW,
                source=Provenance(document_id="DOC-INV-1", page=1, text_snippet="284,000"),
            ),
        ],
    )
    matches = [
        MatchResult(
            ledger_row_id="LED-0001",
            invoice_id="DOC-INV-1",
            status=MatchStatus.MATCHED,
            match_strength=MatchStrength.HIGH,
            reason="Exact.",
            rule_id="exact-amount-exact-date",
        )
    ]

    item = build_review_items(
        "CASE-X", [a_ledger_entry()], [], [invoice], matches, [], [extraction]
    )[0]

    # One low reading drags the item down, while match_strength stays high.
    assert item.extraction_confidence is Confidence.LOW
    assert item.match.match_strength is MatchStrength.HIGH
