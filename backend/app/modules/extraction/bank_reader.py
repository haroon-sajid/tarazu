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
value here is the spreadsheet row it came from (reliability rule 3), never a page
region, because no page was ever looked at.

This module imports pandas and the shared schemas. It must never import
`qwen_client`, and no code here may call a model.
"""

from __future__ import annotations

import io
import logging
import re
from datetime import date as Date
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pandas as pd

from app.shared.schemas import BankTransaction, Provenance

__all__ = ["BankStatementReadError", "read_bank_statement"]

logger = logging.getLogger(__name__)


class BankStatementReadError(ValueError):
    """The statement could not be read: unknown format, or a missing column."""


#: Header aliases seen in real Pakistani internet-banking exports. Compared
#: after normalising to lowercase with underscores, so `Txn. Date`, `TXN DATE`
#: and `txn_date` are all the same header. Order inside a tuple is priority:
#: the first alias present in the file wins.
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
        "amount_pkr",
    ),
    "debit": (
        "debit", "withdrawal", "withdrawals", "debit_amount", "withdrawal_amount",
        "dr", "money_out", "paid_out", "debit_pkr",
    ),
    "credit": (
        "credit", "deposit", "deposits", "credit_amount", "deposit_amount",
        "cr", "money_in", "paid_in", "credit_pkr",
    ),
    "balance": (
        "balance", "running_balance", "closing_balance", "available_balance",
        "ledger_balance", "book_balance", "balance_amount", "balance_pkr", "bal",
    ),
}

#: The numeric core of a money cell: `284,000.00`, `1 500 000`, `45,900`.
#: Anchoring on the digits rather than stripping noise is what lets this survive
#: `Rs. 45,900/-` — where a naive strip leaves the `.` of `Rs.` glued to the
#: front and the `-` of `/-` glued to the back.
_MONEY_NUMBER = re.compile(r"\d[\d,\s]*(?:\.\d+)?")

#: A direction marker written next to the figure. Banks state the direction in
#: words as often as they state it with a sign: `1,500 Dr`, `Cr 2,000`. Matched
#: as a whole word so `CREDIT` is a marker while the `cr` inside another word is
#: not, and so `PKR` and `Rs.` are left alone.
_DIRECTION = re.compile(
    r"(?<![a-z])(dr|cr|debit|credit|withdrawal|deposit)(?![a-z])", re.IGNORECASE
)
_OUTFLOW_WORDS = frozenset({"dr", "debit", "withdrawal"})

#: Date formats these exports actually use, tried in order. Day-first comes
#: first because Pakistani bank exports are day-first: `03/04/2026` is 3 April,
#: not 4 March. The shapes are mutually exclusive anyway — `%d-%m-%Y` cannot
#: read `2026-04-03`, because 2026 is not a day — so the order is a statement of
#: intent rather than a tie-break, except between the day-first and two-digit
#: year variants at the end.
_DATE_FORMATS: tuple[str, ...] = (
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%Y-%m-%d", "%Y/%m/%d",
    "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%d %B %Y",
    "%b %d, %Y", "%d/%m/%y", "%d-%m-%y", "%d-%b-%y", "%d %b %y",
)

#: Bank exports often stamp a time onto the date (`03/04/2026 14:22`). The date
#: is what a reconciliation works in, so the time is parsed and discarded.
_TIME_SUFFIXES: tuple[str, ...] = ("", " %H:%M:%S", " %H:%M", " %H:%M:%S.%f")

#: A year below this means a format matched by accident (`%d-%m-%Y` reading
#: `15-06-26` as the year 26). Treated as a failed parse, not as a date.
_EARLIEST_PLAUSIBLE_YEAR = 1900


def _is_blank(value: object) -> bool:
    """True for the empty cell in every dialect pandas hands back.

    CSV read with `keep_default_na=False` gives `""`; Excel gives `NaN`, and a
    date column can give `NaT`. `pd.isna` covers the last two and answers False
    for anything else, so it is safe on a string or an arbitrary object.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return bool(pd.isna(value))


def _normalise_header(name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def _resolve_columns(frame: pd.DataFrame) -> dict[str, str]:
    """Map our canonical names onto whatever the bank called their columns."""
    normalised = {_normalise_header(column): column for column in frame.columns}
    resolved: dict[str, str] = {}
    for canonical, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in normalised:
                resolved[canonical] = normalised[alias]
                break

    found = ", ".join(str(column) for column in frame.columns)
    if "date" not in resolved:
        raise BankStatementReadError(
            "the bank statement is missing a date column. Expected one of: "
            f"{', '.join(_ALIASES['date'])}. Found columns: {found}"
        )
    if not ({"amount", "debit", "credit"} & set(resolved)):
        raise BankStatementReadError(
            "the bank statement is missing an amount column: expected either a "
            "single signed amount, or a debit/credit pair. Expected one of: "
            f"{', '.join(_ALIASES['amount'] + _ALIASES['debit'] + _ALIASES['credit'])}. "
            f"Found columns: {found}"
        )
    if "description" not in resolved:
        # Not fatal: the figures still reconcile without a narration, and losing
        # a whole readable statement over a header we do not recognise would be
        # a worse trade than matching on amount and date alone.
        logger.warning(
            "Bank statement has no description column (found: %s). "
            "Transactions will be described by their row id.", found
        )
    return resolved


def _to_decimal(raw: object) -> Decimal | None:
    """Parse a money cell, signed as it is *written*. Direction words are ignored.

    Handles `Rs. 5,000`, `1,234.56`, `(2,000.00)`, `1,500.00-`, and the blank
    cell an export writes on the side of a debit/credit pair it is not using.
    """
    if _is_blank(raw):
        return None
    # Anything that is not text came out of an Excel cell already typed — `int`,
    # `float`, or one of numpy's look-alikes — and needs none of the string
    # handling below. Going through `str()` rather than `Decimal(float)` takes
    # the number the spreadsheet displayed instead of the binary expansion
    # behind it: `Decimal("12750.25")`, not `12750.2500000000009094947...`.
    if not isinstance(raw, str):
        try:
            return Decimal(str(raw).strip())
        except (InvalidOperation, ValueError, TypeError):
            return None

    text = raw.strip()
    match = _MONEY_NUMBER.search(text)
    if not match:
        return None

    digits = match.group(0).replace(",", "").replace(" ", "").rstrip(".")
    if not digits:
        return None

    # Accounting style writes negatives as `(1,234.00)`; a bare `-` counts when
    # it sits before the digits, and some exports trail it instead. A trailing
    # `/-` is the Pakistani "only" marker, not a minus sign, so the suffix
    # counts only when it is exactly a minus once the noise is stripped.
    prefix = text[: match.start()]
    suffix = text[match.end():].strip()
    negative = "(" in prefix or "-" in prefix or suffix == "-"

    try:
        value = Decimal(digits)
    except InvalidOperation:
        return None
    return -value if negative else value


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
    value = _to_decimal(raw)
    if value is None:
        return None
    direction = _direction_of(raw)
    if direction is None:
        return value
    return direction * abs(value)


def _to_date(raw: object, *, dayfirst: bool) -> Date | None:
    """Parse a date cell, or `None` when the cell holds no date.

    Tried format by format rather than column at a time, because pandas infers
    one format from the first row and coerces the rest to `NaT`, and a real
    export can and does mix `01/04/2026` with `15-Apr-2026` on the same sheet.
    `pd.to_datetime` is the last resort, so anything the explicit list misses
    still gets a chance.
    """
    if _is_blank(raw):
        return None
    # `datetime` first: both it and `pd.Timestamp` are subclasses of `date`,
    # and Excel hands back a `Timestamp` for every date-formatted cell.
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, Date):
        return raw

    text = str(raw).strip()

    for base in _DATE_FORMATS:
        for suffix in _TIME_SUFFIXES:
            try:
                parsed = datetime.strptime(text, base + suffix)
            except ValueError:
                continue
            if parsed.year >= _EARLIEST_PLAUSIBLE_YEAR:
                return parsed.date()

    fallback = pd.to_datetime(text, errors="coerce", dayfirst=dayfirst)
    if pd.isna(fallback):
        return None
    return fallback.date()


def _read_frame(content: bytes, filename: str) -> pd.DataFrame:
    lowered = filename.lower()
    if lowered.endswith(".csv"):
        reader, kwargs = pd.read_csv, {"dtype": object, "keep_default_na": False}
    elif lowered.endswith((".xlsx", ".xlsm", ".xls")):
        reader, kwargs = pd.read_excel, {"dtype": object}
    else:
        raise BankStatementReadError(
            f"unsupported bank statement format: {filename!r}. Expected .xlsx, "
            ".xlsm, .xls, or .csv. A statement PDF goes to `extract_document` "
            "instead — ask the client for the CSV or Excel export if you can, "
            "because a spreadsheet is read exactly and a PDF has to be read by a model."
        )

    try:
        return reader(io.BytesIO(content), **kwargs)
    except Exception as error:  # pandas raises a family of unrelated types here
        raise BankStatementReadError(
            f"the bank statement {filename!r} could not be opened as a spreadsheet: {error}"
        ) from error


def _combine_debit_credit(
    row: pd.Series, columns: dict[str, str]
) -> Decimal | None:
    """Fold a debit/credit pair into one signed amount: **money out is negative**.

    `abs()` on each side is deliberate. The column already states the direction,
    so an export that additionally writes its debits as `-1,500` (or as
    `1,500 Dr`) must not end up flipping the sign twice.
    """
    debit = _to_decimal(row[columns["debit"]]) if "debit" in columns else None
    credit = _to_decimal(row[columns["credit"]]) if "credit" in columns else None
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
        minted from the spreadsheet row (`BNK-0002` for the first data row), so
        it is unique within the document and stable across re-reads — a
        reference number out of the file is not used as the id, because two
        rows of one statement can legitimately carry the same reference.

    Raises:
        BankStatementReadError: The format is unsupported, the file will not
            open, a required column is absent, or no usable rows were found.
    """
    frame = _read_frame(content, filename)
    if frame.empty:
        raise BankStatementReadError("the bank statement has no rows")

    columns = _resolve_columns(frame)
    # The pair states the direction; a bare `amount` beside it usually does not.
    use_pair = bool({"debit", "credit"} & set(columns))

    transactions: list[BankTransaction] = []
    skipped = 0
    for position, (_index, row) in enumerate(frame.iterrows()):
        # Spreadsheet row as a human sees it: header is row 1, data starts at 2.
        row_number = position + 2
        when = _to_date(row[columns["date"]], dayfirst=dayfirst)
        amount = (
            _combine_debit_credit(row, columns)
            if use_pair
            else _signed_amount(row[columns["amount"]])
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
                description=_optional(row, columns, "description") or bank_row_id,
                balance=(
                    _signed_amount(row[columns["balance"]])
                    if "balance" in columns
                    else None
                ),
                currency=currency,
                source=Provenance(document_id=document_id, row_number=row_number),
            )
        )

    if not transactions:
        raise BankStatementReadError(
            "no usable rows in the bank statement: every row was missing a date "
            "or an amount"
        )
    if skipped:
        logger.info(
            "Bank statement %s: skipped %s non-transaction row(s).", document_id, skipped
        )
    return transactions


def _optional(row: pd.Series, columns: dict[str, str], name: str) -> str | None:
    if name not in columns:
        return None
    value = row[columns[name]]
    if _is_blank(value):
        return None
    return str(value).strip()
