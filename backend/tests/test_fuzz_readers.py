"""Property-based tests: whatever a file contains, a reader says one of two things.

Every reader takes bytes from outside and must either return typed rows or
raise its own `ReadProblemError` with a guide. Nothing else — no `KeyError`
from a short row, no `UnicodeDecodeError` from a Windows export, no
`InvalidOperation` from a cell that says "see note". Hypothesis writes the
files no tester would think to: random bytes, random cell soup, headers with
no rows, rows wider than their header, every encoding a text can have.

The upload route is held to the same rule with a status code: whatever the
bytes, the answer is a `4xx` with a sentence and never a `500`.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.api.files import MAX_FILENAME_LENGTH, safe_filename
from app.modules.extraction.bank_reader import BankStatementReadError, read_bank_statement
from app.modules.extraction.ledger_reader import LedgerReadError, read_ledger
from app.modules.extraction.spreadsheet import (
    normalise_header,
    strip_units,
    to_date,
    to_decimal,
)
from app.modules.matching.service import party_similarity
from app.shared.problems import ReadProblemError
from app.shared.text import normalise_party_name, normalise_reference

FUZZ = settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)

#: Cells the way exports actually write them, plus the ones they should not.
cells = st.one_of(
    st.text(max_size=30),
    st.integers(min_value=-10**9, max_value=10**9).map(str),
    st.sampled_from(
        [
            "", " ", "Rs. 45,900/-", "(1,200.00)", "1,500 Dr", "Cr 2,000", "-284,000.00",
            "02/06/2026", "2026-06-02", "15-Jun-2026", "see note", "TOTAL", "n/a", "—",
            "1.5e3", "١٢٣", "=1+1", "'quoted'", '"double"', "12/13/2026", "31/02/2026",
        ]
    ),
)

#: A header made of real aliases and noise, so some tables are readable.
headers = st.lists(
    st.sampled_from(
        [
            "Date", "Txn Date", "Description", "Narration", "Party", "Vendor", "Amount",
            "Debit (PKR)", "Credit (PKR)", "Balance", "Reference", "Notes", "Serial",
            "", "Unnamed: 3", "Amount", "date",
        ]
    ),
    min_size=1,
    max_size=8,
)

tables = st.tuples(headers, st.lists(st.lists(cells, min_size=0, max_size=9), max_size=12))


def _csv_bytes(header: list[str], rows: list[list[object]], delimiter: str = ",") -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _only_the_readers_error(callable_, error_type) -> None:
    try:
        result = callable_()
    except error_type as error:
        assert isinstance(error, ReadProblemError)
        assert error.problem.message
        assert error.problem.code
        return
    assert isinstance(result, list)


# --------------------------------------------------------------------------- #
# 1. Random bytes
# --------------------------------------------------------------------------- #


@FUZZ
@given(st.binary(max_size=4000))
def test_random_bytes_as_a_csv_ledger_are_refused_or_read(data: bytes) -> None:
    _only_the_readers_error(lambda: read_ledger("DOC", "ledger.csv", data), LedgerReadError)


@FUZZ
@given(st.binary(max_size=4000))
def test_random_bytes_as_an_xlsx_ledger_are_refused_or_read(data: bytes) -> None:
    _only_the_readers_error(lambda: read_ledger("DOC", "ledger.xlsx", data), LedgerReadError)


@FUZZ
@given(st.binary(max_size=4000))
def test_random_bytes_as_a_csv_statement_are_refused_or_read(data: bytes) -> None:
    _only_the_readers_error(
        lambda: read_bank_statement("DOC", "statement.csv", data), BankStatementReadError
    )


@FUZZ
@given(st.binary(max_size=4000))
def test_random_bytes_as_an_xls_statement_are_refused_or_read(data: bytes) -> None:
    _only_the_readers_error(
        lambda: read_bank_statement("DOC", "statement.xls", data), BankStatementReadError
    )


# --------------------------------------------------------------------------- #
# 2. Random tables
# --------------------------------------------------------------------------- #


@FUZZ
@given(tables, st.sampled_from([",", ";", "\t", "|"]))
def test_any_table_is_read_or_refused_by_the_ledger_reader(table, delimiter) -> None:
    header, rows = table
    data = _csv_bytes(header, rows, delimiter)
    _only_the_readers_error(lambda: read_ledger("DOC", "ledger.csv", data), LedgerReadError)


@FUZZ
@given(tables, st.sampled_from([",", ";", "\t", "|"]))
def test_any_table_is_read_or_refused_by_the_bank_reader(table, delimiter) -> None:
    header, rows = table
    data = _csv_bytes(header, rows, delimiter)
    _only_the_readers_error(
        lambda: read_bank_statement("DOC", "statement.csv", data), BankStatementReadError
    )


@FUZZ
@given(tables, st.sampled_from(["utf-8", "utf-8-sig", "cp1252", "utf-16"]))
def test_any_encoding_is_read_or_refused(table, encoding) -> None:
    header, rows = table
    text = _csv_bytes(header, rows).decode("utf-8")
    try:
        data = text.encode(encoding)
    except UnicodeEncodeError:
        return  # this text has no such encoding; nothing to test
    _only_the_readers_error(lambda: read_ledger("DOC", "ledger.csv", data), LedgerReadError)


@FUZZ
@given(st.lists(st.lists(cells, max_size=6), max_size=8))
def test_a_readable_ledger_yields_typed_rows(rows) -> None:
    """When the reader accepts, every row is complete and typed."""
    data = _csv_bytes(["Date", "Party", "Amount"], rows)
    try:
        entries = read_ledger("DOC", "ledger.csv", data)
    except LedgerReadError:
        return
    for entry in entries:
        assert isinstance(entry.amount, Decimal) and entry.amount != 0
        assert isinstance(entry.date, date)
        assert entry.party_name.strip()
        assert entry.source.row_number is not None and entry.source.row_number >= 2
    assert len({entry.ledger_row_id for entry in entries}) == len(entries)


# --------------------------------------------------------------------------- #
# 3. Cell parsers and text helpers never raise
# --------------------------------------------------------------------------- #


@FUZZ
@given(st.one_of(st.text(max_size=60), st.floats(allow_nan=True, allow_infinity=True), st.integers(), st.booleans(), st.none()))
def test_to_decimal_never_raises(raw) -> None:
    value = to_decimal(raw)
    assert value is None or isinstance(value, Decimal)


@FUZZ
@given(st.one_of(st.text(max_size=60), st.floats(allow_nan=True, allow_infinity=True), st.integers(), st.booleans(), st.none(), st.dates()))
def test_to_date_never_raises(raw) -> None:
    value = to_date(raw)
    assert value is None or isinstance(value, date)


@FUZZ
@given(st.text(max_size=80))
def test_header_helpers_never_raise_and_stay_lowercase(raw: str) -> None:
    normalised = normalise_header(raw)
    assert normalised == normalised.lower()
    assert not normalised.startswith("_") and not normalised.endswith("_")
    stripped = strip_units(normalised)
    assert stripped == stripped.lower()
    assert "transfers" not in raw.lower() or "transfe" not in stripped or "transfers" in stripped


@FUZZ
@given(st.text(max_size=80), st.text(max_size=80))
def test_party_similarity_is_bounded_and_symmetric(a: str, b: str) -> None:
    score = party_similarity(a, b)
    assert 0 <= score <= 100
    assert score == party_similarity(b, a)
    assert normalise_party_name(a) == normalise_party_name(a)
    assert normalise_reference(a) == normalise_reference(a)


@FUZZ
@given(st.one_of(st.none(), st.text(max_size=300)))
def test_safe_filename_is_always_a_safe_name(raw) -> None:
    name = safe_filename(raw)
    assert name
    assert len(name) <= MAX_FILENAME_LENGTH
    assert "/" not in name and "\\" not in name
    assert not any(ord(char) < 32 for char in name)
    assert name == name.strip(" .")


# --------------------------------------------------------------------------- #
# 4. The route never answers 500
# --------------------------------------------------------------------------- #


@settings(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))
@given(st.binary(max_size=3000), st.sampled_from(["ledger.csv", "ledger.xlsx", "ledger.xls"]))
def test_the_upload_route_never_answers_500_to_a_bad_ledger(client, demo_mode, data, name) -> None:
    from tests.test_pipeline import a_pdf

    response = client.post(
        "/v1/upload",
        files=[
            ("bank_statement", ("statement.pdf", io.BytesIO(a_pdf()))),
            ("ledger", (name, io.BytesIO(data))),
            ("invoices", ("invoice.pdf", io.BytesIO(a_pdf("INVOICE")))),
        ],
    )
    assert response.status_code in (201, 422), response.text
    body = response.json()
    if response.status_code == 422:
        assert body["detail"]
        assert body["problem"]["guidance"]
