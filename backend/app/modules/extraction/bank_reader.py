"""Read a bank statement exported as CSV or Excel with pandas. No AI touches this path.

The bank statement is the riskiest document Tarazu reads. It is dense, it is the
one document every number in the reconciliation is checked against, and as a PDF
it can only be read by a vision model — which costs money, adds latency, and
introduces a confidence level a human then has to review. Every Pakistani bank a
firm is likely to meet (HBL, Meezan, UBL, Bank Alfalah, MCB) lets the customer
export the same statement from internet banking as CSV or Excel. When the client
does that, there is nothing to *read*: the figures are already in cells, and
pandas takes them exactly, at no cost, with no reading uncertainty at all.

So this module is the same trade `ledger_reader.py` makes, applied to the
document where it is worth the most. Ask for the export, and the extraction risk
on the statement disappears rather than being managed. The provenance of every
value here is the spreadsheet row it came from (reliability rule 3), never a
page region, because no page was ever looked at.

Opening the file, finding the header under the bank's preamble, and reading a
cell are shared with the ledger reader in `spreadsheet.py`. What is particular
to a statement is here: which headers mean what, and which way the money went.

This module imports pandas (through `spreadsheet.py`) and the shared schemas.
It must never import `qwen_client`, and no code here may call a model.
"""

from __future__ import annotations

import logging
import re
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
from app.shared.schemas import BankTransaction, ProblemField, Provenance

__all__ = ["BANK_STATEMENT_FIELDS", "BankStatementReadError", "read_bank_statement"]

logger = logging.getLogger(__name__)


class BankStatementReadError(ReadProblemError):
    """The statement could not be read. `problem` says what to do about it."""


#: Header aliases seen in real Pakistani internet-banking exports. Compared
#: after normalising to lowercase with underscores and dropping a currency
#: word, so `Txn. Date`, `TXN DATE`, and `txn_date` are all the same header
#: and `Debit (PKR)` is `debit`. Order inside a tuple is priority: the first
#: alias present in the file wins.
_ALIASES: dict[str, tuple[str, ...]] = {
    "date": (
        "date", "txn_date", "transaction_date", "value_date", "posting_date",
        "tran_date", "trn_date", "trans_date", "booking_date", "date_of_transaction",
    ),
    "description": (
        "description", "narration", "particulars", "details", "remarks",
        "transaction_details", "transaction_description", "transaction_remarks",
        "narrative", "memo", "reference",
    ),
    "amount": (
        "amount", "transaction_amount", "txn_amount", "signed_amount", "amt",
    ),
    "debit": (
        "debit", "withdrawal", "withdrawals", "debit_amount", "withdrawal_amount",
        "dr", "money_out", "paid_out",
    ),
    "credit": (
        "credit", "deposit", "deposits", "credit_amount", "deposit_amount",
        "cr", "money_in", "paid_in",
    ),
    "balance": (
        "balance", "running_balance", "closing_balance", "available_balance",
        "ledger_balance", "book_balance", "balance_amount", "bal",
    ),
}

#: What a statement has to carry, said for the person who has to add it.
BANK_STATEMENT_FIELDS: dict[str, ProblemField] = {
    "date": ProblemField(
        name="date",
        label="Date",
        why=(
            "Every transaction is placed by date; a row without one cannot be "
            "set against the ledger."
        ),
        accepted_headers=[
            "Date", "Txn Date", "Transaction Date", "Value Date",
            "Posting Date", "Booking Date",
        ],
    ),
    "amount": ProblemField(
        name="amount",
        label="Amount",
        why=(
            "Every match works on the amount: either one signed Amount "
            "column, or a Debit and Credit pair."
        ),
        accepted_headers=[
            "Amount", "Transaction Amount", "Debit and Credit",
            "Withdrawal and Deposit", "Dr and Cr", "Money Out and Money In",
        ],
    ),
}

#: The whole requirement in one phrase, for the guide.
_NEEDS = (
    "the date and the amount (one signed Amount column, or a Debit and Credit "
    "pair). A Description or Narration column is used when the export has one"
)

#: A direction marker written next to the figure. Banks state the direction in
#: words as often as they state it with a sign: `1,500 Dr`, `Cr 2,000`. Matched
#: as a whole word so `CREDIT` is a marker while the `cr` inside another word is
#: not, and so `PKR` and `Rs.` are left alone.
_DIRECTION = re.compile(
    r"(?<![a-z])(dr|cr|debit|credit|withdrawal|deposit)(?![a-z])", re.IGNORECASE
)
_OUTFLOW_WORDS = frozenset({"dr", "debit", "withdrawal"})

#: What the unsupported-format refusal adds, because a statement has a second
#: route into the case that a ledger does not.
_UNSUPPORTED_NOTE = (
    "A statement PDF is accepted too, and goes to the document reader instead; "
    "prefer the CSV or Excel export from internet banking where you have one, "
    "because a spreadsheet is read exactly and a PDF has to be read by a model."
)


def _has_amount(columns: dict[str, int]) -> bool:
    return bool({"amount", "debit", "credit"} & set(columns))


def _complete(columns: dict[str, int]) -> bool:
    return "date" in columns and _has_amount(columns)


def _missing(columns: dict[str, int]) -> list[ProblemField]:
    missing: list[ProblemField] = []
    if "date" not in columns:
        missing.append(BANK_STATEMENT_FIELDS["date"])
    if not _has_amount(columns):
        missing.append(BANK_STATEMENT_FIELDS["amount"])
    return missing


def _refuse_header(
    match: HeaderMatch | None, filename: str, first_row: list[str]
) -> BankStatementReadError:
    found = match.cells if match is not None else first_row
    columns = match.columns if match is not None else {}
    return BankStatementReadError(
        missing_columns("bank_statement", filename, found, _missing(columns), needs=_NEEDS)
    )


def _direction_of(raw: object) -> int | None:
    """`-1` for money out, `+1` for money in, `None` when the cell does not say.

    Only a written marker counts: `1,500 Dr`, `Cr 2,000`, `DEBIT 900`. A cell
    that only carries a figure leaves the direction to whatever the caller knows
    from the column it came out of.
    """
    if not isinstance(raw, str):
        return None
    match = _DIRECTION.search(raw)
    if match is None:
        return None
    return -1 if match.group(1).lower() in _OUTFLOW_WORDS else 1


def _signed_amount(raw: object) -> Decimal | None:
    """A money cell as a signed `Decimal`, letting a `Dr`/`Cr` marker overrule.

    The marker wins over the written sign because it is the more explicit of the
    two: an export that says `1,500 Dr` means money out even where it also
    prints the figure unsigned.
    """
    value = to_decimal(raw)
    if value is None:
        return None
    direction = _direction_of(raw)
    if direction is None:
        return value
    return direction * abs(value)


def _combine_debit_credit(row: list[object], columns: dict[str, int]) -> Decimal | None:
    """Fold a debit/credit pair into one signed amount: **money out is negative**.

    `abs()` on each side is deliberate. The column already states the direction,
    so an export that additionally writes its debits as `-1,500` (or as
    `1,500 Dr`) must not end up flipping the sign twice.
    """
    debit = to_decimal(cell(row, columns.get("debit")))
    credit = to_decimal(cell(row, columns.get("credit")))
    if debit is None and credit is None:
        return None
    return abs(credit or Decimal(0)) - abs(debit or Decimal(0))


def read_bank_statement(
    document_id: str,
    filename: str,
    content: bytes,
    *,
    dayfirst: bool = True,
    currency: str = "PKR",
) -> list[BankTransaction]:
    """Read a CSV or Excel bank statement into `BankTransaction` objects.

    **Sign convention: money out of the account is negative, money in is
    positive.** One rule, applied everywhere — a signed `Amount` column is taken
    as written, a `Debit` column is negated, a `Credit` column is not, and a
    `Dr`/`Cr` marker written beside a figure overrules both. `matching/` compares
    absolute amounts, so the sign is not what reconciles anything; it is there so
    an auditor reading a row can see which way the money went without having to
    know which column it came out of.

    **Which column decides the amount.** A debit/credit pair wins over a single
    `amount` column when the file has both, because the pair states the direction
    and an `amount` column beside it is usually an unsigned magnitude.

    **Which rows are kept.** A row is a transaction when it has a date *and* a
    non-zero amount. That one rule drops the blank separator rows, the
    `Opening Balance` and `Closing Balance` lines, and the `TOTAL` row at the
    foot — none of which carry a transaction date — as well as the filler rows an
    export writes with `0.00` on both sides of the pair. The count of what was
    dropped is logged rather than lost.

    **Where the header is.** Found, not assumed: an export that opens with the
    account holder, the account number, and the period is read from the row
    that names the columns, on whichever sheet carries it.

    Args:
        document_id: The stored document this statement came from.
        filename: Used to pick the reader. `.xlsx`, `.xlsm`, `.xls`, or `.csv`.
        content: The raw file bytes.
        dayfirst: Resolve an ambiguous date as DD/MM/YYYY. True by default,
            which is what Pakistani bank exports use — `03/04/2026` is 3 April,
            not 4 March.
        currency: ISO code recorded on every row.

    Returns:
        One `BankTransaction` per usable row, in file order. `bank_row_id` is
        minted from the spreadsheet row (`BNK-0002` for the first data row under
        a row-1 header), so it is unique within the document and stable across
        re-reads — a reference number out of the file is not used as the id,
        because two rows of one statement can legitimately carry the same
        reference.

    Raises:
        BankStatementReadError: The format is unsupported, the file will not
            open, the header names no date or no amount, or no usable rows were
            found. `problem` on the error says which, with what was found and
            what to do about it.
    """
    tables = load_tables(
        content, filename, slot="bank_statement", error=BankStatementReadError,
        accepted=SPREADSHEET_SUFFIXES, unsupported_note=_UNSUPPORTED_NOTE,
    )
    match = locate_header(tables, _ALIASES, complete=_complete)
    if match is None or not match.complete:
        raise _refuse_header(match, filename, _first_row(tables))
    if not match.data_rows:
        raise BankStatementReadError(empty_file("bank_statement", filename))

    columns = match.columns
    # The pair states the direction; a bare `amount` beside it usually does not.
    use_pair = bool({"debit", "credit"} & set(columns))

    transactions: list[BankTransaction] = []
    skipped = 0
    for offset, row in enumerate(match.data_rows):
        row_number = match.row_number(offset)
        when = to_date(cell(row, columns["date"]), dayfirst=dayfirst)
        amount = (
            _combine_debit_credit(row, columns)
            if use_pair
            else _signed_amount(cell(row, columns["amount"]))
        )

        if when is None or amount is None or amount == 0:
            skipped += 1
            continue

        bank_row_id = f"BNK-{row_number:04d}"
        transactions.append(
            BankTransaction(
                bank_row_id=bank_row_id,
                date=when,
                amount=amount,
                # The schema requires a description; the row id is the honest
                # fallback when the export has no narration to give.
                description=cell_text(cell(row, columns.get("description"))) or bank_row_id,
                balance=_signed_amount(cell(row, columns.get("balance"))),
                currency=currency,
                source=Provenance(document_id=document_id, row_number=row_number),
            )
        )

    if not transactions:
        example = ", ".join(
            cell_text(value) or "" for value in (match.data_rows[0] if match.data_rows else [])
        ).strip(", ")
        raise BankStatementReadError(
            no_usable_rows(
                "bank_statement", filename,
                needs="a date and a non-zero amount",
                rows_seen=len(match.data_rows),
                example=example or None,
                found=match.cells,
            )
        )
    if skipped:
        logger.info(
            "Bank statement %s: skipped %s non-transaction row(s).", document_id, skipped
        )
    return transactions


def _first_row(tables) -> list[str]:
    for table in tables:
        for row in table.rows:
            texts = [cell_text(value) for value in row]
            if any(texts):
                return [text for text in texts if text]
    return []
