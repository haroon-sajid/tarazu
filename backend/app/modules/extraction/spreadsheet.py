"""Deterministic spreadsheet plumbing shared by the ledger and bank readers.

Both readers take a file a client exported — from Tally, QuickBooks, an
internet-banking portal, or Excel by hand — and turn its rows into typed
entries. What varies between the two is which columns they need and what a row
means; what does not vary is everything below: opening the file, finding the
header, and reading a cell. That shared part lives here so the ledger reader
and the bank reader cannot drift apart in how forgiving they are.

What this module handles, because real exports do all of it:

- **Encodings and delimiters.** A CSV saved by Excel on Windows is cp1252, not
  UTF-8; one saved in a Pakistani locale may be semicolon-separated. The text
  is decoded by trying the likely encodings in order, and the delimiter is the
  one that splits the sample into the most consistent number of fields.
- **Title rows and cover sheets.** An export rarely starts with its header:
  the firm's name, the account number, the period, and a blank line come
  first. The header is the row among the first thirty of any sheet that names
  the most columns the reader knows, and every sheet is tried in order.
- **Currency in the header.** `Debit (PKR)`, `Amount in Rs`, and `Debit` are the
  same column. Unit words are stripped before a header is compared.
- **Messy cells.** `Rs. 45,900/-`, `(1,200.00)`, `1,500.00-`, an Excel date
  serial that lost its format, and a date written five different ways on one
  sheet are all read for what they are.

This module imports pandas and the shared schemas. It must never import
`qwen_client`, and no code here may call a model: a spreadsheet is already
structured, and the whole point of this path is that nothing *reads* it.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Callable

import pandas as pd

from app.shared.problems import (
    ReadProblemError,
    empty_file,
    unreadable_file,
    unsupported_format,
)
from app.shared.schemas import UploadSlot

__all__ = [
    "HEADER_SCAN_ROWS",
    "SPREADSHEET_SUFFIXES",
    "HeaderMatch",
    "Table",
    "cell",
    "cell_text",
    "is_blank",
    "load_tables",
    "locate_header",
    "normalise_header",
    "resolve_headers",
    "strip_units",
    "to_date",
    "to_decimal",
]

logger = logging.getLogger(__name__)

#: What the readers open. Anything else is refused with the list.
SPREADSHEET_SUFFIXES: tuple[str, ...] = (".csv", ".xlsx", ".xlsm", ".xls")

#: How far down a sheet the header is looked for. Thirty rows is more than any
#: export's preamble and small enough that a data row never gets mistaken.
HEADER_SCAN_ROWS = 30

#: Tried in order. `utf-8-sig` eats a BOM; `cp1252` is what Excel on Windows
#: writes; `latin-1` decodes any byte, so the chain always ends somewhere.
_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "utf-8", "cp1252", "latin-1")

#: Candidate delimiters, in tie-break order.
_DELIMITERS: tuple[str, ...] = (",", ";", "\t", "|")

#: Words a header carries that say the currency, not the column. Compared as
#: whole tokens after normalising, so `transfers` keeps its `rs`.
_UNIT_TOKENS = frozenset(
    {"pkr", "rs", "rupee", "rupees", "inr", "usd", "aed", "gbp", "eur", "sar", "currency"}
)

#: The numeric core of a money cell: `284,000.00`, `1 500 000`, `45,900`.
#: Anchoring on the digits rather than stripping noise is what lets this survive
#: `Rs. 45,900/-` — where a naive strip leaves the `.` of `Rs.` glued to the
#: front and the `-` of `/-` glued to the back.
_MONEY_NUMBER = re.compile(r"\d[\d,\s]*(?:\.\d+)?")

#: Date formats these exports actually use, tried in order. Day-first comes
#: first because Pakistani exports are day-first: `03/04/2026` is 3 April, not
#: 4 March. The shapes are mutually exclusive anyway — `%d-%m-%Y` cannot read
#: `2026-04-03`, because 2026 is not a day — so the order is a statement of
#: intent rather than a tie-break, except between the day-first and two-digit
#: year variants at the end.
_DATE_FORMATS: tuple[str, ...] = (
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%Y-%m-%d", "%Y/%m/%d",
    "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%d %B %Y", "%d-%b-%y", "%d %b %y",
    "%b %d, %Y", "%B %d, %Y", "%d/%m/%y", "%d-%m-%y",
)

#: Exports often stamp a time onto the date (`03/04/2026 14:22`). The date is
#: what a reconciliation works in, so the time is parsed and discarded.
_TIME_SUFFIXES: tuple[str, ...] = ("", " %H:%M:%S", " %H:%M", " %H:%M:%S.%f")

#: A year below this means a format matched by accident (`%d-%m-%Y` reading
#: `15-06-26` as the year 26). Treated as a failed parse, not as a date.
_EARLIEST_PLAUSIBLE_YEAR = 1900

#: An Excel date serial that lost its number format arrives as a float. Only
#: a plausible range is taken as one: 20000 is 1954, 80000 is 2119.
_EXCEL_EPOCH = datetime(1899, 12, 30)
_EXCEL_SERIAL_RANGE = (20000, 80000)


@dataclass(frozen=True)
class Table:
    """One sheet of an upload, as rows of raw cells. Rows may be ragged."""

    name: str
    rows: list[list[object]]


@dataclass(frozen=True)
class HeaderMatch:
    """Where the header is, what it resolved, and whether that is enough.

    `index` is the row's position in the table (0-based); the spreadsheet row
    a person sees is `index + 1`. `columns` maps a reader's canonical names to
    column positions. `cells` is the header as written, for a message.
    """

    table: Table
    index: int
    columns: dict[str, int]
    cells: list[str]
    complete: bool

    @property
    def data_rows(self) -> list[list[object]]:
        return self.table.rows[self.index + 1 :]

    def row_number(self, offset: int) -> int:
        """The spreadsheet row of the `offset`-th data row, as a human counts."""
        return self.index + offset + 2


# --------------------------------------------------------------------------- #
# Opening the file
# --------------------------------------------------------------------------- #


def load_tables(
    content: bytes,
    filename: str,
    *,
    slot: UploadSlot,
    error: type[ReadProblemError],
    accepted: tuple[str, ...] = SPREADSHEET_SUFFIXES,
    unsupported_note: str | None = None,
) -> list[Table]:
    """Every sheet of the file as raw rows, in workbook order.

    Args:
        content: The raw bytes.
        filename: Picks the reader by extension.
        slot: Which upload this is, for the problem a refusal carries.
        error: The reader's own exception class, so callers keep catching what
            they always caught.
        accepted: The extensions this slot reads.
        unsupported_note: An extra sentence for the unsupported-format problem.

    Raises:
        `error`, carrying a `ReadProblem`: the extension is not accepted, the
        bytes will not open as what the extension says, or the file has no
        rows at all.
    """
    lowered = filename.lower()
    suffix = "." + lowered.rsplit(".", 1)[1] if "." in lowered else ""
    if suffix not in accepted:
        raise error(
            unsupported_format(slot, filename, list(accepted), note=unsupported_note)
        )

    if suffix == ".csv":
        try:
            tables = [_read_csv(content, filename)]
        except csv.Error as cause:
            # A bare carriage return inside an unquoted cell, a field longer
            # than the csv module's limit: the file is not a CSV as written.
            raise error(unreadable_file(slot, filename, _reason(cause), kind="CSV file")) from cause
    else:
        try:
            sheets = pd.read_excel(
                io.BytesIO(content), sheet_name=None, header=None, dtype=object
            )
        except Exception as cause:  # pandas raises a family of unrelated types here
            raise error(unreadable_file(slot, filename, _reason(cause))) from cause
        tables = [
            Table(name=str(name), rows=frame.values.tolist())
            for name, frame in sheets.items()
        ]

    if not any(any(not is_blank(value) for value in row) for table in tables for row in table.rows):
        raise error(empty_file(slot, filename))
    return tables


def _read_csv(content: bytes, filename: str) -> Table:
    text = _decode(content).replace("\x00", "")
    delimiter = _sniff_delimiter(text)
    # `newline=""` hands the csv module the line endings untouched, which is
    # what its quoting rules expect; without it a `\r` inside a quoted cell
    # is a parse error rather than a character.
    rows = [list(row) for row in csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)]
    return Table(name=filename, rows=rows)


def _decode(content: bytes) -> str:
    for encoding in _ENCODINGS:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1", errors="replace")  # pragma: no cover - latin-1 never fails


def _sniff_delimiter(text: str) -> str:
    """The delimiter that splits the sample into the steadiest field count.

    Each candidate is tried through the csv module — so a comma inside a quoted
    `"284,000.00"` is not counted as a separator — and scored by how many
    sample lines agree on one field count above 1. Ties go to the comma.
    """
    sample = [line for line in text.splitlines()[:40] if line.strip()]
    if not sample:
        return ","
    best: tuple[int, int, str] | None = None
    for delimiter in _DELIMITERS:
        try:
            widths = [
                len(fields)
                for fields in csv.reader(sample, delimiter=delimiter)
                if any(field.strip() for field in fields)
            ]
        except csv.Error:
            continue  # not readable with this delimiter; another may do
        if not widths:
            continue
        mode = max(set(widths), key=widths.count)
        if mode < 2:
            continue
        score = (widths.count(mode), mode, delimiter)
        if best is None or score[:2] > best[:2]:
            best = score
    return best[2] if best else ","


def _reason(cause: BaseException) -> str:
    text = str(cause).strip() or type(cause).__name__
    return text if len(text) <= 200 else text[:197] + "..."


# --------------------------------------------------------------------------- #
# Finding the header
# --------------------------------------------------------------------------- #


def normalise_header(name: object) -> str:
    """`Txn. Date`, `TXN DATE`, and `txn_date` become one key."""
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def strip_units(normalised: str) -> str:
    """Drop the currency from a header: `debit_pkr` and `amount_in_rs` → `debit`, `amount`.

    Works on whole tokens, so a header that merely contains the letters is left
    alone: `transfers` stays `transfers`. An `in` directly before a unit goes
    with it; a bare `in`, as in `money_in`, stays.
    """
    tokens = normalised.split("_")
    kept: list[str] = []
    for position, token in enumerate(tokens):
        if token in _UNIT_TOKENS:
            continue
        following = tokens[position + 1] if position + 1 < len(tokens) else ""
        if token == "in" and following in _UNIT_TOKENS:
            continue
        kept.append(token)
    return "_".join(token for token in kept if token)


def resolve_headers(
    cells: list[object], aliases: dict[str, tuple[str, ...]]
) -> dict[str, int]:
    """Map a reader's canonical names onto the positions of a header row.

    Order inside an alias tuple is priority: the first alias present wins. A
    column serves one canonical name only, so a `Reference` column claimed as
    the row id is not also the description. Where two columns share a header,
    the first is the one used.
    """
    by_key: dict[str, int] = {}
    for position, value in enumerate(cells):
        text = cell_text(value)
        if not text:
            continue
        normalised = normalise_header(text)
        for key in (normalised, strip_units(normalised)):
            if key and key not in by_key:
                by_key[key] = position

    resolved: dict[str, int] = {}
    taken: set[int] = set()
    for canonical, names in aliases.items():
        for alias in names:
            position = by_key.get(alias)
            if position is not None and position not in taken:
                resolved[canonical] = position
                taken.add(position)
                break
    return resolved


def locate_header(
    tables: list[Table],
    aliases: dict[str, tuple[str, ...]],
    *,
    complete: Callable[[dict[str, int]], bool],
    scan: int = HEADER_SCAN_ROWS,
) -> HeaderMatch | None:
    """The best header among the first `scan` rows of every sheet.

    The first sheet with a row that satisfies `complete` wins, and within a
    sheet the row that names the most known columns does, earliest on a tie.
    When no sheet has a usable header, the row that came closest anywhere is
    returned with `complete=False`, so the refusal can say what was found;
    `None` means nothing on any sheet looked like a header at all.
    """
    nearest: HeaderMatch | None = None
    for table in tables:
        best: HeaderMatch | None = None
        for index, row in enumerate(table.rows[:scan]):
            texts = [cell_text(value) or "" for value in row]
            if sum(1 for text in texts if text) < 2:
                continue
            columns = resolve_headers(row, aliases)
            if not columns:
                continue
            match = HeaderMatch(
                table=table,
                index=index,
                columns=columns,
                cells=[text for text in texts if text],
                complete=complete(columns),
            )
            if best is None or len(columns) > len(best.columns):
                best = match
        if best is not None and best.complete:
            return best
        if best is not None and (nearest is None or len(best.columns) > len(nearest.columns)):
            nearest = best
    return nearest


# --------------------------------------------------------------------------- #
# Reading a cell
# --------------------------------------------------------------------------- #


def cell(row: list[object], position: int | None) -> object:
    """The cell at `position`, or None when the row is too short or unmapped."""
    if position is None or position >= len(row):
        return None
    return row[position]


def is_blank(value: object) -> bool:
    """True for the empty cell in every dialect the readers meet.

    The csv module gives `""`; Excel gives `NaN`, and a date column can give
    `NaT`. `pd.isna` covers the last two and answers False for anything else,
    so it is safe on a string or an arbitrary object.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):  # pragma: no cover - an exotic object
        return False


def cell_text(value: object) -> str | None:
    """The cell as trimmed text, or None when it is blank."""
    if is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def to_decimal(raw: object) -> Decimal | None:
    """Parse a money cell, signed as it is *written*. Direction words are ignored.

    Handles `Rs. 5,000`, `1,234.56`, `(2,000.00)`, `1,500.00-`, and the blank
    cell an export writes on the side of a debit/credit pair it is not using.
    """
    if is_blank(raw) or isinstance(raw, bool):
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

    digits = match.group(0).replace(",", "").replace(" ", "").replace("\xa0", "").rstrip(".")
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


def to_date(raw: object, *, dayfirst: bool = True) -> Date | None:
    """Parse a date cell, or `None` when the cell holds no date.

    Tried format by format rather than column at a time, because pandas infers
    one format from the first row and coerces the rest to `NaT`, and a real
    export can and does mix `01/04/2026` with `15-Apr-2026` on the same sheet.
    `pd.to_datetime` is the last resort, so anything the explicit list misses
    still gets a chance.
    """
    if is_blank(raw) or isinstance(raw, bool):
        return None
    # `datetime` first: both it and `pd.Timestamp` are subclasses of `date`,
    # and Excel hands back a `Timestamp` for every date-formatted cell.
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, Date):
        return raw
    if isinstance(raw, (int, float)):
        low, high = _EXCEL_SERIAL_RANGE
        if low <= raw <= high:
            return (_EXCEL_EPOCH + timedelta(days=int(raw))).date()
        return None

    text = str(raw).strip()

    for base in _DATE_FORMATS:
        for suffix in _TIME_SUFFIXES:
            try:
                parsed = datetime.strptime(text, base + suffix)
            except ValueError:
                continue
            if parsed.year >= _EARLIEST_PLAUSIBLE_YEAR:
                return parsed.date()

    try:
        fallback = pd.to_datetime(text, errors="coerce", dayfirst=dayfirst)
    except (ValueError, TypeError, OverflowError):  # pragma: no cover - pandas edge cases
        return None
    if pd.isna(fallback):
        return None
    return fallback.date()
