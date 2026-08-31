"""Value corrections: what a human says a misread value actually is.

The point of these tests is the invariant, not the plumbing: a correction
**adds** a reading, it never replaces one. The model's value stays on the
extraction, the human's value is recorded beside it with a name and a time, and
the review item's own numbers are left exactly as the deterministic modules
computed them — because re-matching one row against a corrected figure would
produce a queue that no single pipeline run ever computed (rule 2).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.repository import StoredDocument
from app.core.sqlite_store import SqliteCaseRepository
from app.shared.schemas import AuditAction, DocumentType

DEMO_ORG = "00000000-0000-4000-8000-0000000000d0"


@pytest.fixture()
def case_with_document(
    repository: SqliteCaseRepository, seeded_case: str
) -> tuple[str, str]:
    """The seeded case plus a bank statement to cite. Returns (case_id, doc_id)."""
    document = StoredDocument(
        document_id="DOC-BNK-test01",
        document_type=DocumentType.BANK_STATEMENT,
        filename="statement.pdf",
        size_bytes=1024,
        storage_path=f"{seeded_case}/DOC-BNK-test01/statement.pdf",
    )
    repository.add_documents(DEMO_ORG, seeded_case, [document], "tester")
    return seeded_case, document.document_id


def _first_item(client, case_id: str) -> str:
    return client.get(f"/v1/review-items?case_id={case_id}").json()["items"][0][
        "review_item_id"
    ]


def test_a_correction_keeps_both_readings(client, case_with_document) -> None:
    case_id, document_id = case_with_document
    item_id = _first_item(client, case_id)

    response = client.post(
        f"/v1/review-items/{item_id}/corrections",
        json={
            "document_id": document_id,
            "field": "amount",
            "ai_value": "49500.00",
            "corrected_value": "49900.00",
            "note": "The statement reads 49,900; the 5 is a smudged 9.",
        },
    )
    assert response.status_code == 201, response.text
    correction = response.json()["correction"]

    assert correction["ai_value"] == "49500.00"
    assert correction["corrected_value"] == "49900.00"
    assert correction["corrected_by"]
    assert correction["corrected_at"]

    record = response.json()["audit_record"]
    assert record["action"] == AuditAction.VALUE_CORRECTED.value
    assert "49500.00" in record["detail"] and "49900.00" in record["detail"]


def test_a_correction_does_not_change_the_item(client, case_with_document) -> None:
    """Rule 2: the arithmetic stays exactly as the deterministic run left it."""
    case_id, document_id = case_with_document
    item_id = _first_item(client, case_id)
    before = client.get(f"/v1/review-items?case_id={case_id}").json()["items"][0]

    client.post(
        f"/v1/review-items/{item_id}/corrections",
        json={
            "document_id": document_id,
            "field": "amount",
            "ai_value": "49500.00",
            "corrected_value": "49900.00",
        },
    )

    after = client.get(f"/v1/review-items?case_id={case_id}").json()["items"][0]
    assert after == before, "recording a correction must not re-match anything"


def test_corrections_accumulate_oldest_first(client, case_with_document) -> None:
    case_id, document_id = case_with_document
    item_id = _first_item(client, case_id)

    for field, value in (("amount", "1"), ("invoice_number", "INV-2")):
        client.post(
            f"/v1/review-items/{item_id}/corrections",
            json={"document_id": document_id, "field": field, "corrected_value": value},
        )

    listing = client.get(f"/v1/corrections?case_id={case_id}").json()
    assert listing["total"] == 2
    assert [c["field"] for c in listing["corrections"]] == ["amount", "invoice_number"]


def test_a_correction_that_changes_nothing_is_refused(
    client, case_with_document
) -> None:
    case_id, document_id = case_with_document
    item_id = _first_item(client, case_id)

    response = client.post(
        f"/v1/review-items/{item_id}/corrections",
        json={
            "document_id": document_id,
            "field": "amount",
            "ai_value": "49500.00",
            "corrected_value": "49500.00",
        },
    )
    assert response.status_code == 422
    assert "nothing to correct" in response.json()["detail"]


def test_a_document_from_another_case_is_refused(
    client, repository: SqliteCaseRepository, case_with_document
) -> None:
    """A correction cites evidence from its own case, or it cites nothing."""
    case_id, _ = case_with_document
    from app.shared.schemas import CaseRecord

    repository.create_case(
        DEMO_ORG,
        CaseRecord(
            case_id="CASE-other",
            client_name="Someone Else",
            created_by="tester",
            created_at=datetime.now(timezone.utc),
        ),
    )
    stray = StoredDocument(
        document_id="DOC-BNK-stray",
        document_type=DocumentType.BANK_STATEMENT,
        filename="other.pdf",
        size_bytes=10,
        storage_path="CASE-other/DOC-BNK-stray/other.pdf",
    )
    repository.add_documents(DEMO_ORG, "CASE-other", [stray], "tester")

    item_id = _first_item(client, case_id)
    response = client.post(
        f"/v1/review-items/{item_id}/corrections",
        json={
            "document_id": "DOC-BNK-stray",
            "field": "amount",
            "corrected_value": "1.00",
        },
    )
    assert response.status_code == 422
    assert "belongs to case" in response.json()["detail"]


def test_an_unknown_document_is_a_404(client, case_with_document) -> None:
    case_id, _ = case_with_document
    item_id = _first_item(client, case_id)
    response = client.post(
        f"/v1/review-items/{item_id}/corrections",
        json={"document_id": "DOC-nope", "field": "amount", "corrected_value": "1.00"},
    )
    assert response.status_code == 404


def test_another_firm_cannot_correct_or_read(
    client, other_client, case_with_document
) -> None:
    case_id, document_id = case_with_document
    item_id = _first_item(client, case_id)

    denied = other_client.post(
        f"/v1/review-items/{item_id}/corrections",
        json={"document_id": document_id, "field": "amount", "corrected_value": "1.00"},
    )
    assert denied.status_code == 404, "another firm's item does not exist to them"

    assert other_client.get(f"/v1/corrections?case_id={case_id}").status_code == 404
