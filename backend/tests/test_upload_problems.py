"""A file that cannot be used is refused with a guide, before anything exists.

Two failures a tester met drove this file. A ledger exported as a bank book —
`Date, Description, Reference, Debit (PKR), Credit (PKR), Balance (PKR), Notes`
— was refused for lacking `amount` and `party_name`, in a sentence written for
a log. And a session that had quietly expired answered an upload with "Sign in
at POST /v1/auth/login and send the access token as a Bearer header."

What is pinned here: the readers take what real exports look like; when they
cannot, the refusal is a `ReadProblem` — which file, what it held, what it
lacked, what to do — carried on the response *and* on a failed job; nothing is
created for a refused upload; and every error body is a sentence a person can
read, including the ones FastAPI and the server would otherwise write for
developers.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.sqlite_store import SqliteCaseRepository
from app.main import app
from app.modules.extraction.bank_reader import BankStatementReadError, read_bank_statement
from app.modules.extraction.ledger_reader import LedgerReadError, read_ledger
from app.shared.schemas import CaseStatus, JobStatus

DEMO_ORG = "00000000-0000-4000-8000-0000000000d0"


def csv_bytes(rows: str, encoding: str = "utf-8") -> bytes:
    return rows.encode(encoding)


def xlsx_bytes(frames: dict[str, pd.DataFrame], header: bool = True) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer) as writer:
        for name, frame in frames.items():
            frame.to_excel(writer, sheet_name=name, index=False, header=header)
    return buffer.getvalue()


#: The tester's ledger, shape for shape: a bank book with a debit/credit pair
#: carrying the currency in the header, a reference, and no party column.
BANK_BOOK_CSV = csv_bytes(
    "Date,Description,Reference,Debit (PKR),Credit (PKR),Balance (PKR),Notes\n"
    "02/06/2026,Payment to Gulberg Traders (Pvt) Ltd,CHQ-1001,\"284,000.00\",,\"1,216,000.00\",Yarn\n"
    "05/06/2026,Receipt from Karachi Packaging Co.,IBFT-77,,\"96,400.00\",\"1,312,400.00\",\n"
    "10/06/2026,Al-Habib Stationers,CHQ-1002,\"45,900.00\",,\"1,266,500.00\",Office supplies\n"
    ",Closing balance,,,,\"1,266,500.00\",\n"
)


# --------------------------------------------------------------------------- #
# 1. The ledger reader takes what real exports look like
# --------------------------------------------------------------------------- #


def test_a_bank_book_ledger_with_a_debit_credit_pair_and_no_party_column_is_read() -> None:
    entries = read_ledger("DOC-LED-100", "ledger.csv", BANK_BOOK_CSV)

    assert [entry.ledger_row_id for entry in entries] == ["CHQ-1001", "IBFT-77", "CHQ-1002"]
    # A pair has no sign of its own: the magnitude of the filled side is kept.
    assert [entry.amount for entry in entries] == [
        Decimal("284000.00"), Decimal("96400.00"), Decimal("45900.00"),
    ]
    # No party column, so the narration says who was paid.
    assert entries[0].party_name == "Payment to Gulberg Traders (Pvt) Ltd"
    assert entries[0].description == "Payment to Gulberg Traders (Pvt) Ltd"
    assert entries[0].date == date(2026, 6, 2)
    # The dateless closing-balance line is not an entry.
    assert all(entry.party_name != "Closing balance" for entry in entries)
    # Provenance still counts spreadsheet rows as a person does.
    assert entries[0].source.row_number == 2


def test_a_party_column_wins_over_the_narration_row_by_row() -> None:
    entries = read_ledger(
        "DOC-LED-101", "ledger.csv",
        csv_bytes(
            "Date,Party,Particulars,Amount\n"
            "02/06/2026,Gulberg Traders,Yarn purchase,284000\n"
            "03/06/2026,,Cash withdrawal for wages,50000\n"
        ),
    )
    assert entries[0].party_name == "Gulberg Traders"
    # A blank party cell falls back to the row's narration, not to nothing.
    assert entries[1].party_name == "Cash withdrawal for wages"


def test_the_header_is_found_under_title_rows() -> None:
    entries = read_ledger(
        "DOC-LED-102", "ledger.csv",
        csv_bytes(
            "Haroon Textiles (Pvt) Ltd\n"
            "General ledger — June 2026\n"
            "\n"
            "Date,Party Name,Amount (PKR)\n"
            "02/06/2026,Gulberg Traders,284000\n"
        ),
    )
    assert len(entries) == 1
    assert entries[0].party_name == "Gulberg Traders"
    # Row 5 of the sheet: three title rows, the header on row 4.
    assert entries[0].source.row_number == 5


def test_a_cover_sheet_is_skipped_for_the_sheet_with_the_ledger() -> None:
    content = xlsx_bytes(
        {
            "Cover": pd.DataFrame({"Haroon Textiles": ["Ledger for June 2026"]}),
            "Ledger": pd.DataFrame(
                {"Date": ["02/06/2026"], "Vendor": ["Gulberg Traders"], "Amount": [284000]}
            ),
        }
    )
    entries = read_ledger("DOC-LED-103", "ledger.xlsx", content)
    assert len(entries) == 1
    assert entries[0].amount == Decimal("284000")


def test_a_windows_csv_with_semicolons_and_a_rupee_sign_is_read() -> None:
    content = csv_bytes(
        "Date;Party;Amount\n"
        "02/06/2026;Gulberg Traders – Lahore;\"Rs. 284,000/-\"\n",
        encoding="cp1252",
    )
    entries = read_ledger("DOC-LED-104", "ledger.csv", content)
    assert entries[0].party_name == "Gulberg Traders – Lahore"
    assert entries[0].amount == Decimal("284000")


def test_a_repeated_reference_cannot_name_a_row_so_the_row_number_does() -> None:
    entries = read_ledger(
        "DOC-LED-105", "ledger.csv",
        csv_bytes(
            "Date,Party,Amount,Reference\n"
            "02/06/2026,Gulberg Traders,1000,IBFT\n"
            "03/06/2026,Al-Habib Stationers,2000,IBFT\n"
            "04/06/2026,Ravi Logistics,3000,CHQ-9\n"
        ),
    )
    assert [entry.ledger_row_id for entry in entries] == ["LED-0002", "LED-0003", "CHQ-9"]


def test_a_row_that_moves_no_money_is_not_an_entry() -> None:
    entries = read_ledger(
        "DOC-LED-106", "ledger.csv",
        csv_bytes("Date,Party,Amount\n02/06/2026,Memo only,0\n03/06/2026,Gulberg,500\n"),
    )
    assert [entry.party_name for entry in entries] == ["Gulberg"]


def test_a_missing_amount_column_is_refused_with_a_guide() -> None:
    with pytest.raises(LedgerReadError) as error:
        read_ledger(
            "DOC-LED-107", "ledger.csv",
            csv_bytes("Date,Description,Reference\n02/06/2026,Yarn,CHQ-1\n"),
        )
    problem = error.value.problem
    assert problem.code == "missing_columns"
    assert problem.title == "The ledger needs an Amount column"
    assert "no amount column was found" in problem.message
    assert problem.found_columns == ["Date", "Description", "Reference"]
    assert [field.name for field in problem.missing] == ["amount"]
    assert "Debit and Credit" in problem.missing[0].accepted_headers
    assert any("header" in step for step in problem.guidance)


def test_a_file_that_is_not_a_spreadsheet_is_refused_not_raised_raw() -> None:
    with pytest.raises(LedgerReadError, match="could not be opened") as error:
        read_ledger("DOC-LED-108", "ledger.xlsx", b"<html>not a workbook</html>")
    assert error.value.problem.code == "unreadable_file"


def test_a_ledger_of_nothing_but_a_header_is_refused() -> None:
    with pytest.raises(LedgerReadError) as error:
        read_ledger("DOC-LED-109", "ledger.csv", csv_bytes("Date,Party,Amount\n"))
    assert error.value.problem.code == "empty_file"


def test_a_ledger_whose_rows_carry_no_dates_is_refused_with_the_first_row() -> None:
    with pytest.raises(LedgerReadError, match="no usable rows") as error:
        read_ledger(
            "DOC-LED-110", "ledger.csv",
            csv_bytes("Date,Party,Amount\nsee note,Gulberg,1000\n"),
        )
    assert error.value.problem.code == "no_usable_rows"
    assert "see note" in error.value.problem.message


# --------------------------------------------------------------------------- #
# 2. The bank reader shares the plumbing
# --------------------------------------------------------------------------- #


def test_a_bank_export_with_the_account_holder_above_the_header_is_read() -> None:
    rows = read_bank_statement(
        "DOC-BNK-100", "statement.csv",
        csv_bytes(
            "Account statement\n"
            "Account no,0123-456789\n"
            "Period,01/06/2026 to 30/06/2026\n"
            "\n"
            "Txn Date,Narration,Debit (PKR),Credit (PKR),Balance (PKR)\n"
            "02/06/2026,IBFT to Gulberg Traders,\"284,000.00\",,\"1,216,000.00\"\n"
        ),
    )
    assert len(rows) == 1
    assert rows[0].amount == Decimal("-284000.00")
    assert rows[0].source.row_number == 6


def test_a_bank_refusal_is_a_guide_too() -> None:
    with pytest.raises(BankStatementReadError) as error:
        read_bank_statement(
            "DOC-BNK-101", "statement.csv",
            csv_bytes("Serial,Narration,Cheque No\n1,Inward remittance,004119\n"),
        )
    problem = error.value.problem
    assert problem.document == "bank_statement"
    assert {field.name for field in problem.missing} == {"date", "amount"}


# --------------------------------------------------------------------------- #
# 3. The upload route refuses before anything exists
# --------------------------------------------------------------------------- #


def _upload(client, *, ledger=None, statement=None, invoice=None, background=False):
    from tests.test_pipeline import a_ledger, a_pdf

    files = [
        ("bank_statement", statement or ("statement.pdf", io.BytesIO(a_pdf()))),
        ("ledger", ledger or ("ledger.xlsx", io.BytesIO(a_ledger()))),
        ("invoices", invoice or ("invoice.pdf", io.BytesIO(a_pdf("INVOICE")))),
    ]
    return client.post(f"/v1/upload{'?background=true' if background else ''}", files=files)


def test_the_testers_bank_book_ledger_now_opens_a_case(client, demo_mode) -> None:
    response = _upload(client, ledger=("AI_Audit_Test_Ledger.csv", io.BytesIO(BANK_BOOK_CSV)))
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "ready_for_review"


@pytest.mark.parametrize("background", [False, True])
def test_an_unusable_ledger_is_refused_with_a_guide_and_creates_nothing(
    client, repository: SqliteCaseRepository, demo_mode, background: bool
) -> None:
    broken = csv_bytes("Date,Description\n02/06/2026,Yarn\n")
    response = _upload(client, ledger=("ledger.csv", io.BytesIO(broken)), background=background)

    assert response.status_code == 422, response.text
    body = response.json()
    assert "ledger 'ledger.csv' could not be read" in body["detail"]
    problem = body["problem"]
    assert problem["code"] == "missing_columns"
    assert problem["document"] == "ledger"
    assert problem["filename"] == "ledger.csv"
    assert problem["found_columns"] == ["Date", "Description"]
    assert [field["name"] for field in problem["missing"]] == ["amount"]
    assert problem["guidance"]
    # Nothing was created: no case for the list to show as stuck, no job.
    assert repository.list_cases(DEMO_ORG) == []
    assert client.get("/v1/jobs").json()["total"] == 0


def test_a_corrupt_pdf_is_refused_before_the_reader_is_called(client, demo_mode) -> None:
    response = _upload(client, invoice=("invoice.pdf", io.BytesIO(b"%PDF-1.4 not really")))
    assert response.status_code == 422
    problem = response.json()["problem"]
    assert problem["code"] == "unreadable_file"
    assert problem["document"] == "invoice"
    assert problem["filename"] == "invoice.pdf"
    assert "could not be opened as a PDF" in problem["message"]


def test_the_same_file_in_both_spreadsheet_slots_is_refused(client, demo_mode) -> None:
    response = _upload(
        client,
        ledger=("book.csv", io.BytesIO(BANK_BOOK_CSV)),
        statement=("book.csv", io.BytesIO(BANK_BOOK_CSV)),
    )
    assert response.status_code == 422
    problem = response.json()["problem"]
    assert problem["code"] == "duplicate_file"
    assert "same file" in problem["title"]


def test_an_empty_upload_says_so_as_a_guide(client, demo_mode) -> None:
    response = _upload(client, ledger=("ledger.csv", io.BytesIO(b"")))
    assert response.status_code == 422
    problem = response.json()["problem"]
    assert problem["code"] == "empty_file"
    assert problem["document"] == "ledger"


def test_a_wrong_extension_carries_the_guide_beside_the_415(client, demo_mode) -> None:
    response = _upload(client, ledger=("ledger.docx", io.BytesIO(b"stub")))
    assert response.status_code == 415
    body = response.json()
    assert ".xlsx" in body["detail"] and ".csv" in body["detail"]
    assert body["problem"]["code"] == "unsupported_format"


# --------------------------------------------------------------------------- #
# 4. A failure after acceptance marks the case failed and carries the guide
# --------------------------------------------------------------------------- #


def test_a_reader_outage_marks_the_case_failed_not_stuck_extracting(
    client, repository: SqliteCaseRepository, demo_mode, monkeypatch
) -> None:
    """Before this, an extraction error left the case saying `extracting` forever."""
    from app import pipeline
    from app.modules.extraction.qwen_client import QwenTransportError

    def down(*_args, **_kwargs):
        raise QwenTransportError("connection refused")

    monkeypatch.setattr(pipeline.extraction, "extract_document", down)

    response = _upload(client, background=True)
    assert response.status_code == 201, response.text
    body = response.json()

    job = client.get(f"/v1/jobs/{body['job_id']}").json()
    assert job["status"] == JobStatus.FAILED.value
    assert job["problem"]["code"] == "document_reader_unavailable"
    assert job["problem"]["document"] == "bank_statement"
    assert job["problem"]["filename"] == "statement.pdf"
    assert job["problem"]["guidance"]
    assert job["error"] == job["problem"]["message"]
    assert "connection refused" in job["error"]

    case = repository.get_case(DEMO_ORG, body["case_id"])
    assert case.status is CaseStatus.FAILED
    assert case.status_detail == job["error"]


def test_a_synchronous_reader_outage_is_a_502_with_the_guide(client, demo_mode, monkeypatch) -> None:
    from app import pipeline
    from app.modules.extraction.qwen_client import QwenTransportError

    def down(*_args, **_kwargs):
        raise QwenTransportError("timed out")

    monkeypatch.setattr(pipeline.extraction, "extract_document", down)
    response = _upload(client)
    assert response.status_code == 502
    assert response.json()["problem"]["code"] == "document_reader_unavailable"


def test_a_deterministic_fault_is_a_processing_failure_with_its_reason(
    client, demo_mode, monkeypatch
) -> None:
    from app.modules import matching

    def explode(*_args, **_kwargs):
        raise RuntimeError("matching blew up")

    monkeypatch.setattr(matching.service, "run_matching", explode)
    response = _upload(client)
    assert response.status_code == 500
    problem = response.json()["problem"]
    assert problem["code"] == "processing_failed"
    assert "matching blew up" in problem["message"]
    assert "marked failed" in problem["message"]


# --------------------------------------------------------------------------- #
# 5. Every error body is a sentence
# --------------------------------------------------------------------------- #


def test_no_credential_is_told_to_sign_in_not_to_post_a_header(anonymous_client) -> None:
    response = anonymous_client.get("/v1/cases")
    assert response.status_code == 401
    assert response.json()["detail"].startswith("You are not signed in, or your session has ended.")


def test_a_request_missing_its_files_is_told_which_in_words(client) -> None:
    response = client.post("/v1/upload", data={"client_name": "X"})
    assert response.status_code == 422
    body = response.json()
    assert body["detail"].startswith("The request could not be accepted:")
    assert "bank_statement is missing" in body["detail"]
    assert "ledger is missing" in body["detail"]
    assert "invoices is missing" in body["detail"]
    # FastAPI's own list stays beside it, for developers.
    assert isinstance(body["errors"], list) and body["errors"]


def test_an_unhandled_error_is_a_readable_500_not_a_bare_text(
    repository: SqliteCaseRepository, storage, demo_org
) -> None:
    from app.api.deps import get_repository, get_storage
    from app.core.auth import issue_local_token
    from app.core.config import get_settings
    from tests.conftest import DEMO_USER

    def broken_repository():
        raise RuntimeError("the database vanished")

    app.dependency_overrides[get_repository] = broken_repository
    app.dependency_overrides[get_storage] = lambda: storage
    try:
        token, _ = issue_local_token(DEMO_USER.user_id, DEMO_USER.email, get_settings())
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/v1/cases", headers={"Authorization": f"Bearer {token}"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    body = response.json()
    assert body["detail"].startswith("Something went wrong on the server")
    # The reason stays in the log; the body never repeats a traceback.
    assert "vanished" not in body["detail"]


def test_a_sales_export_without_a_header_is_refused_with_a_guide(client, seeded_case) -> None:
    response = client.post(
        f"/v1/cases/{seeded_case}/sales-data",
        files=[("file", ("sales.csv", io.BytesIO(b"this,that\n1,2\n")))],
    )
    assert response.status_code == 422
    body = response.json()
    assert "could not be read" in body["detail"]
    problem = body["problem"]
    assert problem["code"] == "missing_columns"
    assert problem["document"] == "sales_data"
    assert problem["filename"] == "sales.csv"
    assert {field["name"] for field in problem["missing"]} == {"date", "amount"}
