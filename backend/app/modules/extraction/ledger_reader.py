"""Read the client's ledger with pandas. No AI touches this path.

The ledger arrives as Excel or CSV — it is already structured, so sending it to
a vision model would add cost, latency, and a chance of misreading a number that
is sitting right there in a cell. Every value here is read exactly, and its
provenance is the spreadsheet row it came from.

This module imports pandas and the shared schemas. It must never import
`qwen_client`, and no code here may call a model.
"""

from __future__ import annotations

import io
import logging
import re
from decimal import Decimal, InvalidOperation

import pandas as pd

from app.shared.schemas import LedgerEntry, Provenance

__all__ = ["LedgerReadError", "read_ledger"]

logger = logging.getLogger(__name__)


class LedgerReadError(ValueError):
    """The ledger could not be read: unknown format, or a missing column."""


#: Header aliases seen in real Pakistani ledger exports (Tally, QuickBooks,
#: Excel by hand). Compared after normalising to lowercase with underscores.
_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("date", "txn_date", "transaction_date", "entry_date", "posting_date", "dated"),
    "amount": ("amount", "amt", "value", "debit", "credit", "debit_amount", "amount_pkr"),
    "party_name": (
        "party_name", "party", "vendor", "supplier", "payee", "account_name",
        "customer", "name",
    ),
    "description": (
        "description", "particulars", "narration", "details", "memo", "remarks",
    ),
    "account_code": (
        "account_code", "account", "code", "gl_code", "ledger_code", "account_no",
    ),
    "ledger_row_id": ("ledger_row_id", "id", "ref", "reference", "voucher_no", "entry_no"),
}

_REQUIRED = ("date", "amount", "party_name")

#: The numeric core of a money cell: `284,000.00`, `1 500 000`, `45,900`.
#: Anchoring on the digits rather than stripping noise is what lets this survive
#: `Rs. 45,900/-` — where a naive strip leaves the `.` of `Rs.` glued to the
#: front and the `-` of `/-` glued to the back.
_MONEY_NUMBER = re.compile(r"\d[\d,\s]*(?:\.\d+)?")


def _normalise_header(name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def _resolve_columns(frame: pd.DataFrame) -> dict[str, str]:
    """Map our canonical names onto whatever the client called their columns."""
    normalised = {_normalise_header(column): column for column in frame.columns}
    resolved: dict[str, str] = {}
    for canonical, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in normalised:
                resolved[canonical] = normalised[alias]
                break
    missing = [name for name in _REQUIRED if name not in resolved]
    if missing:
        raise LedgerReadError(
            f"the ledger is missing required column(s): {', '.join(missing)}. "
            f"Found columns: {', '.join(str(c) for c in frame.columns)}"
        )
    return resolved


def _to_decimal(raw: object) -> Decimal | None:
    """Parse a money cell. Handles 'Rs. 49,500/-', '(1,200)', and plain numbers."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if isinstance(raw, (int, float, Decimal)):
        try:
            return Decimal(str(raw))
        except InvalidOperation:
            return None

    text = str(raw).strip()
    if not text:
        return None

    match = _MONEY_NUMBER.search(text)
    if not match:
        return None

    digits = match.group(0).replace(",", "").replace(" ", "").rstrip(".")
    if not digits:
        return None

    # Accounting style writes negatives as `(1,200)`; a bare `-` also counts,
    # but only when it sits before the digits. A trailing `/-` is the Pakistani
    # "only" marker, not a minus sign.
    prefix = text[: match.start()]
    negative = "(" in prefix or "-" in prefix

    try:
        value = Decimal(digits)
    except InvalidOperation:
        return None
    return -value if negative else value


def _read_frame(content: bytes, filename: str) -> pd.DataFrame:
    lowered = filename.lower()
    if lowered.endswith(".csv"):
        return pd.read_csv(io.BytesIO(content), dtype=object, keep_default_na=False)
    if lowered.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(io.BytesIO(content), dtype=object)
    raise LedgerReadError(
        f"unsupported ledger format: {filename!r}. Expected .xlsx, .xls, or .csv."
    )


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
        One `LedgerEntry` per usable row, in file order. Rows with no date or no
        amount are skipped as blank or as separator rows, and counted in a log
        line rather than silently dropped.

    Raises:
        LedgerReadError: The format is unsupported, a required column is absent,
            or no usable rows were found.
    """
    frame = _read_frame(content, filename)
    if frame.empty:
        raise LedgerReadError("the ledger has no rows")

    columns = _resolve_columns(frame)
    dates = pd.to_datetime(
        frame[columns["date"]], errors="coerce", dayfirst=dayfirst
    )

    entries: list[LedgerEntry] = []
    skipped = 0
    for position, (index, row) in enumerate(frame.iterrows()):
        # Spreadsheet row as a human sees it: header is row 1, data starts at 2.
        row_number = position + 2
        date = dates.iloc[position]
        amount = _to_decimal(row[columns["amount"]])
        party = str(row[columns["party_name"]] or "").strip()

        if pd.isna(date) or amount is None or not party:
            skipped += 1
            continue

        raw_id = row[columns["ledger_row_id"]] if "ledger_row_id" in columns else None
        ledger_row_id = str(raw_id).strip() if raw_id not in (None, "") else ""

        entries.append(
            LedgerEntry(
                ledger_row_id=ledger_row_id or f"LED-{row_number:04d}",
                date=date.date(),
                amount=amount,
                party_name=party,
                description=_optional(row, columns, "description"),
                account_code=_optional(row, columns, "account_code"),
                currency=currency,
                source=Provenance(document_id=document_id, row_number=row_number),
            )
        )

    if not entries:
        raise LedgerReadError(
            "no usable rows in the ledger: every row was missing a date, an amount, "
            "or a party name"
        )
    if skipped:
        logger.info("Ledger %s: skipped %s incomplete row(s).", document_id, skipped)
    return entries


def _optional(row: pd.Series, columns: dict[str, str], name: str) -> str | None:
    if name not in columns:
        return None
    value = row[columns[name]]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None
