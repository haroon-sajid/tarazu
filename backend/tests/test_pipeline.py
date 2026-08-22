"""The pipeline: upload → extract → match → flag → persisted review queue.

`matching/` and `rules/` are owned by Dev-D and raise `NotImplementedError`
today. These tests cover both worlds:

- With the real stubs, the pipeline parks the case at `awaiting_matching` with
  everything it managed to do already saved, and says so.
- With the two functions monkeypatched to stand-ins, the whole flow runs end to
  end and produces a persisted review queue. **The monkeypatching happens here
  in the test, never in the application** — `matching/service.py` and
  `rules/service.py` are untouched.
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
from app.core.sqlite_store import LocalDocumentStore, SqliteCaseRepository
from app.modules.matching import service as matching
from app.modules.rules import service as rules
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
from app.core.repository import StoredDocument

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
            "Date": ["02/06/2026", "10/06/2026"],
            "Party Name": ["Gulberg Traders (Pvt) Ltd", "Al-Habib Stationers"],
            "Amount": [284000, 45900],
            "Particulars": ["Yarn purchase", "Office supplies"],
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


# The `demo_mode` and `implemented_modules` fixtures live in `conftest.py`, so
# the tenancy tests can drive the same full pipeline. They are still test-side
# stand-ins: `matching/service.py` and `rules/service.py` stay exactly as their
# owner left them.


# --------------------------------------------------------------------------- #
# The gap: matching and rules are not implemented yet
# --------------------------------------------------------------------------- #


def test_the_pipeline_parks_when_matching_is_not_implemented(
    repository: SqliteCaseRepository, storage: LocalDocumentStore, demo_mode
) -> None:
    outcome = run_pipeline(
        ORG, "CASE-A", "Sethi Textiles (Pvt) Ltd", documents("CASE-A"), AUDITOR,
        repository, storage,
    )

    assert outcome.status is CaseStatus.AWAITING_MATCHING
    assert outcome.review_items == []
    assert "not implemented" in (outcome.detail or "")
    assert repository.get_case(ORG, "CASE-A").status is CaseStatus.AWAITING_MATCHING


def test_everything_before_matching_is_still_saved(
    repository: SqliteCaseRepository, storage: LocalDocumentStore, demo_mode
) -> None:
    """A parked case keeps its documents, its extractions, and its trail."""
    run_pipeline(ORG, "CASE-B", "Client", documents("CASE-B"), AUDITOR, repository, storage)

    assert len(repository.list_documents(ORG, "CASE-B")) == 3
    assert repository.list_extractions(ORG, "CASE-B"), "extractions should be persisted"
    actions = [record.action for record in repository.list_audit(ORG, "CASE-B")]
    assert AuditAction.CASE_CREATED in actions
    assert actions.count(AuditAction.DOCUMENT_UPLOADED) == 3
    assert AuditAction.EXTRACTION_COMPLETED in actions
    assert AuditAction.MATCHING_COMPLETED not in actions


def test_the_upload_endpoint_reports_the_gap_honestly(
    client, repository: SqliteCaseRepository, demo_mode
) -> None:
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
    assert body["status"] == "awaiting_matching"
    assert body["review_item_count"] == 0
    assert "not implemented" in body["message"]


# --------------------------------------------------------------------------- #
# The full flow, with stand-ins for the two unimplemented functions
# --------------------------------------------------------------------------- #


def test_the_full_flow_produces_a_persisted_review_queue(
    repository: SqliteCaseRepository,
    storage: LocalDocumentStore,
    demo_mode,
    implemented_modules,
) -> None:
    outcome = run_pipeline(
        ORG, "CASE-C", "Sethi Textiles (Pvt) Ltd", documents("CASE-C"), AUDITOR,
        repository, storage,
    )

    assert outcome.status is CaseStatus.READY_FOR_REVIEW
    assert outcome.review_items, "the pipeline should have produced review items"

    persisted = repository.list_review_items(ORG, "CASE-C")
    assert len(persisted) == len(outcome.review_items)
    assert repository.get_case(ORG, "CASE-C").status is CaseStatus.READY_FOR_REVIEW


def test_the_full_flow_records_every_stage_in_the_trail(
    repository: SqliteCaseRepository,
    storage: LocalDocumentStore,
    demo_mode,
    implemented_modules,
) -> None:
    run_pipeline(ORG, "CASE-D", "Client", documents("CASE-D"), AUDITOR, repository, storage)

    actions = [record.action for record in repository.list_audit(ORG, "CASE-D")]
    assert AuditAction.CASE_CREATED in actions
    assert AuditAction.DOCUMENT_UPLOADED in actions
    assert AuditAction.EXTRACTION_COMPLETED in actions
    assert AuditAction.MATCHING_COMPLETED in actions


def test_the_ledger_is_read_by_pandas_and_recorded_as_such(
    repository: SqliteCaseRepository,
    storage: LocalDocumentStore,
    demo_mode,
    implemented_modules,
) -> None:
    """The trail should show plainly that no model touched the ledger."""
    outcome = run_pipeline(
        ORG, "CASE-E", "Client", documents("CASE-E"), AUDITOR, repository, storage
    )

    assert len(outcome.ledger_entries) == 2
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
    repository: SqliteCaseRepository,
    storage: LocalDocumentStore,
    demo_mode,
    implemented_modules,
) -> None:
    run_pipeline(ORG, "CASE-F", "Client", documents("CASE-F"), AUDITOR, repository, storage)
    stored = storage.get("CASE-F/DOC-LED-001/ledger.xlsx")
    assert stored[:2] == b"PK"  # an xlsx is a zip


def test_an_approve_after_a_real_pipeline_run_lands_in_the_trail(
    client, repository: SqliteCaseRepository, demo_mode, implemented_modules
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
