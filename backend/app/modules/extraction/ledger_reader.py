"""Read the client's ledger with pandas. No AI touches this path.

The ledger arrives as Excel or CSV — it is already structured, so sending it to
a vision model would add cost, latency, and a chance of misreading a number that
is sitting right there in a cell. Every value here is read exactly, and its
provenance is the spreadsheet row it came from.

What a ledger looks like varies more than what a bank statement looks like,
because it is whatever the client's bookkeeper keeps: a Tally day book with a
single signed `Amount`, a QuickBooks export with `Debit` and `Credit` side by
side, a hand-kept Excel bank book with `Debit (PKR)` and `Credit (PKR)` and a
running balance, with the counterparty in a `Party` column or only in the
narration. All of those are ledgers, and all of them are read here:

- **The amount** comes from a single amount column, or from a debit/credit
  pair folded into one figure. A pair has no sign convention of its own — a
  bookkeeper's debit is money out of a bank book and money in to an expense
  head — so the folded amount is the **magnitude** of whichever side is filled.
  A single amount column is taken as written, sign included, as before.
- **Who was paid** comes from a party column when the file has one, and from
  the description or narration when it does not; a row with neither cannot be
  matched to an invoice or a bank line and is skipped.
- **The header** is found, not assumed: an export that starts with the firm's
  name and the period is read from the row that actually names the columns.

This module imports pandas (through `spreadsheet.py`) and the shared schemas.
It must never import `qwen_client`, and no code here may call a model.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from app.modules.extraction.spreadsheet import (
    SPREADSHEET_SUFFIXES,
    HeaderMatch,
    cell,
    cell_text,
    load_tables,
    locate_header,
    to_date,
    to_decimal,
)
from app.shared.problems import (
    ReadProblemError,
    empty_file,
    missing_columns,
    no_usable_rows,
)
from app.shared.schemas import LedgerEntry, ProblemField, Provenance

__all__ = ["LEDGER_FIELDS", "LedgerReadError", "read_ledger"]

logger = logging.getLogger(__name__)


class LedgerReadError(ReadProblemError):
    """The ledger could not be read. `problem` says what to do about it."""


#: Header aliases seen in real Pakistani ledger exports (Tally, QuickBooks,
#: Excel by hand). Compared after normalising to lowercase with underscores
#: and dropping a currency word, so `Debit (PKR)` is `debit`. Order inside a
#: tuple is priority: the first alias present in the file wins.
_ALIASES: dict[str, tuple[str, ...]] = {
    "date": (
        "date", "txn_date", "transaction_date", "entry_date", "posting_date",
        "voucher_date", "tran_date", "trans_date", "value_date", "dated",
        "date_of_transaction",
    ),
    "amount": (
        "amount", "amt", "value", "transaction_amount", "txn_amount",
        "net_amount", "total_amount", "signed_amount",
    ),
    "debit": (
        "debit", "dr", "debit_amount", "withdrawal", "withdrawals", "payment",
        "payments", "paid", "paid_out", "money_out", "outflow", "expense",
    ),
    "credit": (
        "credit", "cr", "credit_amount", "deposit", "deposits", "receipt",
        "receipts", "received", "paid_in", "money_in", "inflow", "income",
    ),
    "party_name": (
        "party_name", "party", "vendor", "vendor_name", "supplier",
        "supplier_name", "payee", "payee_name", "customer", "customer_name",
        "account_name", "name", "paid_to", "beneficiary", "counterparty",
        "to_from",
    ),
    "description": (
        "description", "particulars", "narration", "details", "memo", "remarks",
        "transaction_details", "narrative", "notes", "note",
    ),
    "account_code": (
        "account_code", "account", "code", "gl_code", "ledger_code", "account_no",
        "account_number", "gl_account", "ledger_account", "account_head", "head",
    ),
    "ledger_row_id": (
        "ledger_row_id", "id", "voucher_no", "voucher_number", "voucher",
        "entry_no", "entry_number", "txn_id", "transaction_id", "ref",
        "reference", "serial", "serial_no", "sr_no", "s_no", "sno",
    ),
}

#: What a ledger has to carry, said for the person who has to add it. These
#: are what the refusal lists as missing, and what the upload screen explains.
LEDGER_FIELDS: dict[str, ProblemField] = {
    "date": ProblemField(
        name="date",
        label="Date",
        why=(
            "Every match is placed by date, so a row without one cannot be "
            "set against the bank statement."
        ),
        accepted_headers=[
            "Date", "Txn Date", "Transaction Date", "Entry Date",
            "Posting Date", "Voucher Date",
        ],
    ),
    "amount": ProblemField(
        name="amount",
        label="Amount",
        why=(
            "Every match and every audit rule works on the amount; without "
            "it nothing can be reconciled."
        ),
        accepted_headers=[
            "Amount", "Amt", "Value", "Amount (PKR)", "Debit and Credit",
            "Dr and Cr", "Payment and Receipt", "Withdrawal and Deposit",
        ],
    ),
    "party_name": ProblemField(
        name="party_name",
        label="Party or description",
        why=(
            "Matching an entry to an invoice and a bank line needs to know "
            "who was paid, from a party column or, failing that, the narration."
        ),
        accepted_headers=[
            "Party", "Party Name", "Vendor", "Supplier", "Payee", "Customer",
            "Account Name", "Paid To", "Description", "Particulars",
            "Narration", "Details", "Memo", "Remarks",
        ],
    ),
}

#: The whole requirement in one phrase, for the guide.
_NEEDS = (
    "the date, the amount (or a Debit and Credit pair), and who was paid "
    "(a Party, Vendor, Supplier, or Payee column, or at least a Description "
    "or Narration)"
)


def _has_amount(columns: dict[str, int]) -> bool:
    return bool({"amount", "debit", "credit"} & set(columns))


def _has_party(columns: dict[str, int]) -> bool:
    return bool({"party_name", "description"} & set(columns))


def _complete(columns: dict[str, int]) -> bool:
    return "date" in columns and _has_amount(columns) and _has_party(columns)


def _missing(columns: dict[str, int]) -> list[ProblemField]:
    missing: list[ProblemField] = []
    if "date" not in columns:
        missing.append(LEDGER_FIELDS["date"])
    if not _has_amount(columns):
        missing.append(LEDGER_FIELDS["amount"])
    if not _has_party(columns):
        missing.append(LEDGER_FIELDS["party_name"])
    return missing


def _refuse_header(match: HeaderMatch | None, filename: str, first_row: list[str]) -> LedgerReadError:
    found = match.cells if match is not None else first_row
    columns = match.columns if match is not None else {}
    return LedgerReadError(
        missing_columns("ledger", filename, found, _missing(columns), needs=_NEEDS)
    )


def _amount_of(row: list[object], columns: dict[str, int]) -> Decimal | None:
    """The row's amount: a single column as written, or a pair as a magnitude.

    The pair wins when the file has both, because the pair states which side a
    figure is on and a bare `amount` beside it is usually an unsigned copy.
    Exactly one side of a pair is expected to be filled; when both are, the
    net (debit less credit) is kept and logged rather than a side dropped.
    """
    if {"debit", "credit"} & set(columns):
        debit = to_decimal(cell(row, columns.get("debit")))
        credit = to_decimal(cell(row, columns.get("credit")))
        debit = debit if debit else None
        credit = credit if credit else None
        if debit is None and credit is None:
            return None
        if debit is not None and credit is not None:
            return abs(debit) - abs(credit)
        return abs(debit if debit is not None else credit)  # type: ignore[arg-type]
    return to_decimal(cell(row, columns.get("amount")))


def _party_of(row: list[object], columns: dict[str, int]) -> str | None:
    party = cell_text(cell(row, columns.get("party_name")))
    if party:
        return party
    return cell_text(cell(row, columns.get("description")))


def read_ledger(
    document_id: str,
    filename: str,
    content: bytes,
    *,
    dayfirst: bool = True,
    currency: str = "PKR",
) -> list[LedgerEntry]:
    """Read a ledger file into `LedgerEntry` objects.

    Args:
        document_id: The stored document this ledger came from.
        filename: Used to pick the reader. `.xlsx`, `.xls`, `.xlsm`, or `.csv`.
        content: The raw file bytes.
        dayfirst: Parse ambiguous dates as DD/MM/YYYY. True by default, which is
            the Pakistani convention — `03/06/2026` is 3 June, not 6 March.
        currency: ISO code recorded on every row.

    Returns:
        One `LedgerEntry` per usable row, in file order. A row is usable when
        it has a date, a non-zero amount, and a party or a description. Rows
        without them — blank separators, opening balances, totals — are skipped
        and counted in a log line rather than silently dropped. `ledger_row_id`
        is the file's own reference or voucher number when the file has one
        and it is unique; otherwise it is minted from the spreadsheet row
        (`LED-0002` for the first data row under a row-1 header), because a
        reference that repeats cannot name a row.

    Raises:
        LedgerReadError: The format is unsupported, the file will not open,
            the header does not name a date, an amount, and a party or
            description, or no usable rows were found. `problem` on the error
            says which, with what was found and what to do about it.
    """
    tables = load_tables(
        content, filename, slot="ledger", error=LedgerReadError,
        accepted=SPREADSHEET_SUFFIXES,
    )
    match = locate_header(tables, _ALIASES, complete=_complete)
    if match is None or not match.complete:
        raise _refuse_header(match, filename, _first_row(tables))
    if not match.data_rows:
        raise LedgerReadError(empty_file("ledger", filename))

    columns = match.columns
    read: list[tuple[int, object, Decimal, str, list[object]]] = []
    skipped = 0
    for offset, row in enumerate(match.data_rows):
        row_number = match.row_number(offset)
        when = to_date(cell(row, columns["date"]), dayfirst=dayfirst)
        amount = _amount_of(row, columns)
        party = _party_of(row, columns)
        if when is None or amount is None or amount == 0 or not party:
            skipped += 1
            continue
        read.append((row_number, when, amount, party, row))

    if not read:
        example = ", ".join(
            cell_text(value) or "" for value in (match.data_rows[0] if match.data_rows else [])
        ).strip(", ")
        raise LedgerReadError(
            no_usable_rows(
                "ledger", filename,
                needs="a date, a non-zero amount, and a party or a description",
                rows_seen=len(match.data_rows),
                example=example or None,
                found=match.cells,
            )
        )

    ids = _row_ids(read, columns)
    entries = [
        LedgerEntry(
            ledger_row_id=ledger_row_id,
            date=when,
            amount=amount,
            party_name=party,
            description=cell_text(cell(row, columns.get("description"))),
            account_code=cell_text(cell(row, columns.get("account_code"))),
            currency=currency,
            source=Provenance(document_id=document_id, row_number=row_number),
        )
        for (row_number, when, amount, party, row), ledger_row_id in zip(read, ids)
    ]
    if skipped:
        logger.info("Ledger %s: skipped %s incomplete row(s).", document_id, skipped)
    return entries


def _row_ids(
    read: list[tuple[int, object, Decimal, str, list[object]]],
    columns: dict[str, int],
) -> list[str]:
    """The file's own ids where they are unique, the row number where not.

    Every downstream lookup — the match, the flag, the approve route — is by
    `ledger_row_id`, so two rows sharing one would be one row to the review
    queue. A repeated reference therefore falls back to the row, for every
    row that carries it.
    """
    position = columns.get("ledger_row_id")
    raw = [
        cell_text(cell(row, position)) if position is not None else None
        for _number, _when, _amount, _party, row in read
    ]
    counts: dict[str, int] = {}
    for value in raw:
        if value:
            counts[value] = counts.get(value, 0) + 1
    repeated = {value for value, count in counts.items() if count > 1}
    if repeated:
        logger.info(
            "Ledger ids %s repeat; those rows are numbered by spreadsheet row instead.",
            ", ".join(sorted(repeated)[:5]),
        )
    return [
        value if value and value not in repeated else f"LED-{row_number:04d}"
        for value, (row_number, *_rest) in zip(raw, read)
    ]


def _first_row(tables) -> list[str]:
    for table in tables:
        for row in table.rows:
            texts = [cell_text(value) for value in row]
            if any(texts):
                return [text for text in texts if text]
    return []
