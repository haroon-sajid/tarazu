"""Bank statement reader tests. Deterministic parsing only — nothing is mocked,
because there is nothing to mock: no network, no model, no repository.

The fixtures are built inline as bytes so each test says exactly what a bank
handed us. They are shaped after real Pakistani internet-banking exports: signed
amount columns, debit/credit pairs, `Rs.` prefixes, bracketed negatives, trailing
`Dr` markers, and a `TOTAL` row at the foot with no date.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from app.modules.extraction.bank_reader import BankStatementReadError, read_bank_statement
from app.shared.schemas import BankTransaction, Provenance


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def csv_bytes(rows: str) -> bytes:
    return rows.encode("utf-8")


def xlsx_bytes(frame: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.to_excel(buffer, index=False)
    return buffer.getvalue()


#: A signed single-amount export: HBL's "Amount" column carries the sign.
SIGNED_CSV = csv_bytes(
    "Date,Description,Amount,Balance\n"
    "02/06/2026,IBFT to Gulberg Traders,\"-284,000.00\",\"1,216,000.00\"\n"
    "10/06/2026,Cheque 004119 - Al-Habib Stationers,\"Rs. 45,900\",\"1,170,100.00\"\n"
    "14/06/2026,Inward remittance,1500000,\"2,670,100.00\"\n"
    ",,,\n"
    "18/06/2026,Consultancy fee,\"(187,500.00)\",\"2,482,600.00\"\n"
    ",TOTAL,\"1,074,400.00\",\n"
)

#: A debit/credit pair export with header variants: Meezan's "Txn Date" and
#: "Narration", a `Dr` marker inside a cell, and a blank balance.
PAIR_CSV = csv_bytes(
    "Txn Date,Narration,Withdrawal,Deposit,Running Balance\n"
    "02/06/2026,IBFT to Gulberg Traders,\"284,000.00\",,\"1,216,000.00\"\n"
    "10/06/2026,Cheque 004119,\"1,500 Dr\",,\"1,214,500.00\"\n"
    "14/06/2026,Inward remittance,,\"1,234.56\",\n"
    "18/06/2026,Bank charges,0.00,0.00,\"1,215,734.56\"\n"
    ",Closing balance,,,\"1,215,734.56\"\n"
)


def read_signed() -> list[BankTransaction]:
    return read_bank_statement("DOC-BNK-001", "statement.csv", SIGNED_CSV)


def read_pair() -> list[BankTransaction]:
    return read_bank_statement("DOC-BNK-002", "statement.csv", PAIR_CSV)


# --------------------------------------------------------------------------- #
# 1. A signed single-amount CSV
# --------------------------------------------------------------------------- #


def test_a_signed_amount_csv_is_read_into_bank_transactions() -> None:
    rows = read_signed()

    assert len(rows) == 4
    assert all(isinstance(row, BankTransaction) for row in rows)
    assert rows[0].description == "IBFT to Gulberg Traders"
    assert rows[0].amount == Decimal("-284000.00")
    assert rows[0].balance == Decimal("1216000.00")
    assert rows[0].currency == "PKR"


def test_money_out_is_negative_and_money_in_is_positive() -> None:
    by_description = {row.description: row.amount for row in read_signed()}
    assert by_description["IBFT to Gulberg Traders"] == Decimal("-284000.00")
    assert by_description["Inward remittance"] == Decimal("1500000")


def test_messy_money_cells_survive_currency_marks_and_brackets() -> None:
    by_description = {row.description: row.amount for row in read_signed()}
    assert by_description["Cheque 004119 - Al-Habib Stationers"] == Decimal("45900")
    assert by_description["Consultancy fee"] == Decimal("-187500.00")


def test_amounts_are_decimal_not_float() -> None:
    """Money is never a float here: 0.1 + 0.2 must not creep into a statement."""
    for row in read_signed():
        assert isinstance(row.amount, Decimal)
        assert row.balance is None or isinstance(row.balance, Decimal)


# --------------------------------------------------------------------------- #
# 2. A debit/credit pair, and header variants
# --------------------------------------------------------------------------- #


def test_a_debit_credit_pair_is_folded_into_one_signed_amount() -> None:
    rows = read_pair()

    assert [row.amount for row in rows] == [
        Decimal("-284000.00"),
        Decimal("-1500"),
        Decimal("1234.56"),
    ]


def test_header_variants_are_recognised() -> None:
    """`Txn Date` and `Narration` are the same columns as `Date` and `Description`."""
    rows = read_pair()
    assert rows[0].date == date(2026, 6, 2)
    assert rows[0].description == "IBFT to Gulberg Traders"


def test_a_dr_marker_inside_a_cell_keeps_the_money_going_out() -> None:
    """`1,500 Dr` is an outflow even though the figure itself is unsigned."""
    withdrawal = next(row for row in read_pair() if row.description == "Cheque 004119")
    assert withdrawal.amount == Decimal("-1500")


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("1,500 Dr", Decimal("-1500")),
        ("1,500 Cr", Decimal("1500")),
        ("Dr 1,500", Decimal("-1500")),
        ("DEBIT 1,500", Decimal("-1500")),
        ("Rs. 1,500", Decimal("1500")),
        ("-1,500 Dr", Decimal("-1500")),
    ],
)
def test_a_direction_marker_decides_the_sign_on_a_single_amount_column(
    written: str, expected: Decimal
) -> None:
    """`Dr` beside a figure is the bank saying "out"; it overrules the written sign."""
    rows = read_bank_statement(
        "DOC-BNK-018",
        "statement.csv",
        csv_bytes(f'Date,Narration,Amount\n05/06/2026,Cheque 004119,"{written}"\n'),
    )
    assert rows[0].amount == expected


def test_a_blank_balance_cell_is_none_not_zero() -> None:
    remittance = next(row for row in read_pair() if row.description == "Inward remittance")
    assert remittance.balance is None


def test_headers_match_regardless_of_case_and_punctuation() -> None:
    rows = read_bank_statement(
        "DOC-BNK-003",
        "statement.csv",
        csv_bytes(
            "TRANSACTION DATE,Transaction Details,Debit (PKR),Credit (PKR)\n"
            "05/06/2026,Karachi Packaging Co.,\"96,400\",\n"
        ),
    )
    assert len(rows) == 1
    assert rows[0].amount == Decimal("-96400")
    assert rows[0].description == "Karachi Packaging Co."


def test_a_debit_credit_pair_wins_over_an_unsigned_amount_column() -> None:
    """The pair states the direction; an `Amount` beside it is a magnitude."""
    rows = read_bank_statement(
        "DOC-BNK-004",
        "statement.csv",
        csv_bytes(
            "Date,Particulars,Amount,Debit,Credit\n"
            "05/06/2026,Yarn purchase,\"96,400\",\"96,400\",\n"
        ),
    )
    assert rows[0].amount == Decimal("-96400")


# --------------------------------------------------------------------------- #
# 3. Excel
# --------------------------------------------------------------------------- #


def test_an_xlsx_statement_is_read_too() -> None:
    content = xlsx_bytes(
        pd.DataFrame(
            {
                "Value Date": ["05/06/2026", "07/06/2026"],
                "Remarks": ["Karachi Packaging Co.", "Utility bill"],
                "Amount": [96400, -12750.25],
                "Closing Balance": [1216000, 1203249.75],
            }
        )
    )
    rows = read_bank_statement("DOC-BNK-005", "statement.xlsx", content)

    assert len(rows) == 2
    assert rows[0].date == date(2026, 6, 5)
    assert rows[0].amount == Decimal("96400")
    assert rows[1].amount == Decimal("-12750.25")
    assert rows[1].source.row_number == 3


def test_excel_date_cells_are_read_as_dates() -> None:
    """Excel hands pandas a Timestamp, not a string; both must land on the day."""
    content = xlsx_bytes(
        pd.DataFrame(
            {
                "Date": [pd.Timestamp("2026-04-03")],
                "Narration": ["Inward remittance"],
                "Amount": [5000],
            }
        )
    )
    rows = read_bank_statement("DOC-BNK-006", "statement.xlsx", content)
    assert rows[0].date == date(2026, 4, 3)


# --------------------------------------------------------------------------- #
# 4. Dates
# --------------------------------------------------------------------------- #


def test_dates_are_day_first() -> None:
    """`03/04/2026` is 3 April in Pakistan, not 4 March."""
    rows = read_bank_statement(
        "DOC-BNK-007",
        "statement.csv",
        csv_bytes("Date,Narration,Amount\n03/04/2026,Inward remittance,5000\n"),
    )
    assert rows[0].date == date(2026, 4, 3)


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("03/04/2026", date(2026, 4, 3)),
        ("03-04-2026", date(2026, 4, 3)),
        ("2026-04-03", date(2026, 4, 3)),
        ("03-Apr-2026", date(2026, 4, 3)),
        ("3 April 2026", date(2026, 4, 3)),
        ("03/04/2026 14:22", date(2026, 4, 3)),
    ],
)
def test_the_date_formats_these_exports_actually_use(written: str, expected: date) -> None:
    rows = read_bank_statement(
        "DOC-BNK-008",
        "statement.csv",
        csv_bytes(f"Date,Narration,Amount\n{written},Inward remittance,5000\n"),
    )
    assert rows[0].date == expected


def test_a_statement_may_mix_date_formats() -> None:
    """pandas would infer one format from row one; every row is parsed on its own."""
    rows = read_bank_statement(
        "DOC-BNK-009",
        "statement.csv",
        csv_bytes(
            "Date,Narration,Amount\n"
            "01/04/2026,First,100\n"
            "15-Apr-2026,Second,200\n"
            "2026-04-30,Third,300\n"
        ),
    )
    assert [row.date for row in rows] == [
        date(2026, 4, 1),
        date(2026, 4, 15),
        date(2026, 4, 30),
    ]


# --------------------------------------------------------------------------- #
# 5. Rows that are not transactions
# --------------------------------------------------------------------------- #


def test_blank_and_totals_rows_are_skipped() -> None:
    """The blank separator and the dateless `TOTAL` line are not transactions."""
    rows = read_signed()
    assert len(rows) == 4
    assert "TOTAL" not in {row.description for row in rows}
    assert all(row.description for row in rows)


def test_a_dateless_closing_balance_line_is_skipped() -> None:
    assert "Closing balance" not in {row.description for row in read_pair()}


def test_a_row_that_moves_no_money_is_skipped() -> None:
    """An export writing `0.00` on both sides of the pair is padding, not a payment."""
    assert "Bank charges" not in {row.description for row in read_pair()}


def test_a_statement_of_nothing_but_summary_rows_fails_loudly() -> None:
    with pytest.raises(BankStatementReadError, match="no usable rows"):
        read_bank_statement(
            "DOC-BNK-010",
            "statement.csv",
            csv_bytes("Date,Narration,Amount\n,Opening balance,\n,Closing balance,\n"),
        )


# --------------------------------------------------------------------------- #
# 6. Provenance and ids
# --------------------------------------------------------------------------- #


def test_every_transaction_carries_row_provenance_for_the_right_document() -> None:
    for row in read_signed():
        assert row.source.document_id == "DOC-BNK-001"
        assert row.source.row_number is not None
        assert row.source.page is None and row.source.bbox is None


def test_provenance_points_at_the_spreadsheet_row_a_human_would_click() -> None:
    """Header is row 1, so the first transaction is row 2 — and row 6 survives
    the blank row 5 above it."""
    rows = read_signed()
    assert rows[0].source == Provenance(document_id="DOC-BNK-001", row_number=2)
    assert rows[-1].source.row_number == 6


def test_ids_are_unique_and_follow_the_row() -> None:
    rows = read_signed()
    ids = [row.bank_row_id for row in rows]
    assert len(set(ids)) == len(ids)
    assert ids == ["BNK-0002", "BNK-0003", "BNK-0004", "BNK-0006"]


def test_a_row_with_no_narration_is_described_by_its_id() -> None:
    """`BankTransaction.description` is required; the id is the honest fallback."""
    rows = read_bank_statement(
        "DOC-BNK-011",
        "statement.csv",
        csv_bytes("Date,Amount\n05/06/2026,\"96,400\"\n"),
    )
    assert rows[0].description == rows[0].bank_row_id == "BNK-0002"


# --------------------------------------------------------------------------- #
# 7. Errors
# --------------------------------------------------------------------------- #


def test_a_missing_date_column_names_the_headers_found() -> None:
    with pytest.raises(BankStatementReadError) as error:
        read_bank_statement(
            "DOC-BNK-012",
            "statement.csv",
            csv_bytes("Serial,Narration,Amount\n1,Inward remittance,5000\n"),
        )
    message = str(error.value)
    assert "date column" in message
    assert "Found columns: Serial, Narration, Amount" in message


def test_a_missing_amount_column_names_the_headers_found() -> None:
    with pytest.raises(BankStatementReadError) as error:
        read_bank_statement(
            "DOC-BNK-013",
            "statement.csv",
            csv_bytes("Date,Narration,Cheque No\n05/06/2026,Inward remittance,004119\n"),
        )
    message = str(error.value)
    assert "amount column" in message
    assert "Found columns: Date, Narration, Cheque No" in message


def test_an_unsupported_format_says_what_is_accepted() -> None:
    with pytest.raises(BankStatementReadError, match="unsupported bank statement format"):
        read_bank_statement("DOC-BNK-014", "statement.pdf", b"%PDF-1.4")


def test_the_unsupported_format_message_lists_the_extensions() -> None:
    with pytest.raises(BankStatementReadError) as error:
        read_bank_statement("DOC-BNK-015", "statement.docx", b"stub")
    message = str(error.value)
    assert ".csv" in message and ".xlsx" in message


def test_a_file_that_will_not_open_as_a_spreadsheet_is_reported_not_raised_raw() -> None:
    with pytest.raises(BankStatementReadError, match="could not be opened"):
        read_bank_statement("DOC-BNK-016", "statement.xlsx", b"not really an excel file")


def test_an_empty_statement_is_rejected() -> None:
    with pytest.raises(BankStatementReadError):
        read_bank_statement("DOC-BNK-017", "statement.csv", csv_bytes("Date,Narration,Amount\n"))


# --------------------------------------------------------------------------- #
# 8. The boundary: reliability rule 2
# --------------------------------------------------------------------------- #


def test_the_bank_reader_imports_no_ai_client() -> None:
    """A spreadsheet cell must never meet a model. This is the whole point.

    Read off the import statements rather than grepping the text, so the module
    docstring stays free to explain *why* it does not call Qwen.
    """
    import ast
    from pathlib import Path

    import app.modules.extraction.bank_reader as module

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert imported == {
        "__future__", "io", "logging", "re", "datetime", "decimal",
        "pandas", "app.shared.schemas",
    }
