"""A bank statement that arrives as a spreadsheet never reaches the model.

Every Pakistani bank's internet banking exports the statement as CSV or Excel,
and reading that with pandas removes the extraction risk from the single
riskiest document in a case: no confidence to weigh, no API to be down, no page
to be misread, and nothing billed per page.

These tests are the wiring, not the parser — `test_bank_reader.py` proves the
reading itself. What is pinned here is that the pipeline takes the deterministic
branch, records it honestly in the trail, and produces a queue that matches.
"""

from __future__ import annotations

import io

from app.core.sqlite_store import SqliteCaseRepository
from app.shared.schemas import ActorType, AuditAction

DEMO_ORG = "00000000-0000-4000-8000-0000000000d0"

#: The bank's side of the three ledger rows in `tests/test_pipeline.py`
#: (Gulberg Traders 284,000 on 2 June; Al-Habib Stationers 45,900 on 10 June;
#: Indus Power Solutions 1,500,000 on 14 June), in the debit/credit shape a
#: real internet-banking export uses — day-first dates, thousands separators,
#: and a dateless total row at the foot.
STATEMENT_CSV = b"""Txn Date,Narration,Debit,Credit,Balance
02/06/2026,PAYMENT TO GULBERG TRADERS PVT LTD,"284,000.00",,"2,500,000.00"
10/06/2026,PAYMENT TO AL-HABIB STATIONERS,"45,900.00",,"2,454,100.00"
14/06/2026,PAYMENT TO INDUS POWER SOLUTIONS,"1,500,000.00",,"954,100.00"
,TOTAL,"1,829,900.00",,
"""


def _upload(client, statement: tuple[str, bytes]):
    from tests.test_pipeline import a_ledger, a_pdf

    return client.post(
        "/v1/upload",
        files=[
            ("bank_statement", statement),
            ("ledger", ("ledger.xlsx", io.BytesIO(a_ledger()))),
            ("invoices", ("invoice.pdf", io.BytesIO(a_pdf("INVOICE")))),
        ],
    )


def test_a_csv_statement_is_read_by_pandas_not_the_model(
    client, repository: SqliteCaseRepository, demo_mode
) -> None:
    response = _upload(client, ("statement.csv", io.BytesIO(STATEMENT_CSV)))
    assert response.status_code == 201, response.text
    case_id = response.json()["case_id"]

    reads = [
        record
        for record in repository.list_audit(DEMO_ORG, case_id)
        if record.action is AuditAction.EXTRACTION_COMPLETED
    ]
    statement_read = [
        record for record in reads if "bank transactions read with pandas" in (record.detail or "")
    ]
    assert statement_read, "the statement must take the deterministic branch"
    assert statement_read[0].actor_type is ActorType.SYSTEM
    assert statement_read[0].actor_id == "pandas"
    assert "3 bank transactions" in statement_read[0].detail
    assert "no model involved" in statement_read[0].detail

    # And nothing recorded an AI reading of the statement.
    assert not [record for record in reads if record.actor_type is ActorType.AI and
                "statement" in (record.detail or "").lower()]


def test_a_csv_statement_still_produces_matches(client, demo_mode) -> None:
    """The rest of the pipeline cannot tell where the transactions came from."""
    response = _upload(client, ("statement.csv", io.BytesIO(STATEMENT_CSV)))
    case_id = response.json()["case_id"]

    items = client.get(f"/v1/review-items?case_id={case_id}").json()["items"]
    assert len(items) == 3
    matched = [item for item in items if item.get("bank_transaction")]
    assert matched, "the ledger rows should reconcile against the CSV statement"
    # Provenance points at a spreadsheet row, not a page.
    source = matched[0]["bank_transaction"]["source"]
    assert source["row_number"] is not None
    assert source["page"] is None


def test_an_xlsx_statement_is_accepted(client, demo_mode) -> None:
    import pandas

    buffer = io.BytesIO()
    pandas.DataFrame(
        {
            "Date": ["02/06/2026", "14/06/2026"],
            "Description": [
                "PAYMENT TO GULBERG TRADERS PVT LTD",
                "PAYMENT TO INDUS POWER SOLUTIONS",
            ],
            # A signed single-amount column: money out is negative.
            "Amount": [-284_000.00, -1_500_000.00],
        }
    ).to_excel(buffer, index=False)

    response = _upload(client, ("statement.xlsx", io.BytesIO(buffer.getvalue())))
    assert response.status_code == 201, response.text


def test_a_pdf_statement_still_goes_to_the_model(
    client, repository: SqliteCaseRepository, demo_mode
) -> None:
    """The vision model is for paper that has no machine-readable form."""
    from tests.test_pipeline import a_pdf

    response = _upload(client, ("statement.pdf", io.BytesIO(a_pdf())))
    assert response.status_code == 201, response.text
    case_id = response.json()["case_id"]

    ai_reads = [
        record
        for record in repository.list_audit(DEMO_ORG, case_id)
        if record.action is AuditAction.EXTRACTION_COMPLETED
        and record.actor_type is ActorType.AI
    ]
    assert ai_reads, "a PDF statement is still read by the model"


def test_an_unreadable_statement_is_a_422_naming_the_problem(client, demo_mode) -> None:
    broken = b"this,is,not,a,bank,statement\n1,2,3,4,5,6\n"
    response = _upload(client, ("statement.csv", io.BytesIO(broken)))
    assert response.status_code == 422
    assert "bank statement could not be read" in response.json()["detail"]


def test_an_unsupported_statement_extension_is_refused(client, demo_mode) -> None:
    response = _upload(client, ("statement.docx", io.BytesIO(b"not a statement")))
    assert response.status_code == 415
    assert ".csv" in response.json()["detail"]
