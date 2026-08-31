"""Public interface of the analytics module.

This is the only file other modules may import from `modules/analytics/`. It
accepts and returns `app/shared/` schema objects exclusively — never raw dicts.

What this module does:

- Reads a SALES_DATA export (Excel or CSV) with pandas into `SalesRecord`
  objects. **No AI on this path** — a spreadsheet is already structured, and a
  model could only misread a number that is sitting right there in a cell. This
  is the same no-AI path the ledger takes.
- Aggregates those records into a `SalesAnalyticsResult`: revenue by month, by
  product, by region, the top customers, and anomalies worth a human's
  attention. Every figure is a sum or a count over the rows that were read;
  money stays `Decimal` end to end, so the breakdowns add back to the total
  exactly.

What it must never do (see the module README and CLAUDE.md): import an AI
client, call anything over the network, or turn an anomaly into a verdict. The
anomalies are rule findings — `negative-amount`, `duplicate-transaction`,
`revenue-spike`, `large-transaction` — and each names the row or month it is
about, the same way `rules/` flags name theirs.

Typical use::

    records = read_sales_data("DOC-SLS-0001", "sales.xlsx", content)
    result = analyze_sales(records)
    if result.anomalies:
        ...  # a human weighs them; nothing is auto-suppressed
"""

from __future__ import annotations

import csv
import io
import logging
import re
import statistics
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import pandas as pd

from app.shared.schemas import (
    Anomaly,
    CustomerSummary,
    MonthlyRevenue,
    ProductRevenue,
    Provenance,
    RegionSummary,
    SalesAnalyticsResult,
    SalesRecord,
)

__all__ = [
    "ANOMALY_KINDS",
    "LARGE_TRANSACTION_FACTOR",
    "LARGE_TRANSACTION_MIN_SAMPLE",
    "SPIKE_FACTOR",
    "SPIKE_MIN_MONTHS",
    "TOP_CUSTOMERS",
    "SalesReadError",
    "analyze_sales",
    "read_sales_data",
]

logger = logging.getLogger(__name__)


class SalesReadError(ValueError):
    """The sales data could not be read: an unsupported format, a missing
    column, or a malformed file."""


#: How many customers the readout ranks. The schema caps the list at the same
#: number, so the contract and the computation cannot drift apart.
TOP_CUSTOMERS = 5

#: A month is only called a spike against at least this many months of
#: context. Two months cannot make a trend, and one of two is always "above
#: the median".
SPIKE_MIN_MONTHS = 3

#: A month whose revenue is more than this multiple of the median month — or
#: less than the median divided by it — is flagged as a spike.
SPIKE_FACTOR = Decimal("2")

#: A whale transaction is only looked for once there is this much of a sample,
#: for the same reason Benford refuses significance below fifty rows.
LARGE_TRANSACTION_MIN_SAMPLE = 10

#: A sale more than this multiple of the median sale is flagged. A multiple of
#: the median rather than of the mean, so one enormous sale cannot raise the
#: bar against its own detection.
LARGE_TRANSACTION_FACTOR = Decimal("10")

#: The anomaly kinds this module emits, in the order they are evaluated. A
#: plain string rather than an enum, matching `rule_id` in `rules/`.
ANOMALY_KINDS = (
    "negative-amount",
    "duplicate-transaction",
    "revenue-spike",
    "large-transaction",
)


# --------------------------------------------------------------------------- #
# 1. Reading the export
# --------------------------------------------------------------------------- #
#
# The mirror of `extraction/ledger_reader.py`, which this module deliberately
# does not import: a module's internals are its own, so the small parsing
# helpers live here too.


#: Header aliases seen in real sales exports (ERPs, POS dumps, Excel by hand).
#: Compared after normalising to lowercase with underscores.
_ALIASES: dict[str, tuple[str, ...]] = {
    "date": (
        "date", "sale_date", "sales_date", "txn_date", "transaction_date",
        "order_date", "invoice_date", "dated",
    ),
    "amount": (
        "amount", "amt", "value", "revenue", "total", "sale_amount",
        "amount_pkr", "line_total",
    ),
    "customer_name": (
        "customer_name", "customer", "client", "buyer", "party_name", "party",
        "account_name", "name",
    ),
    "product": (
        "product", "product_name", "item", "item_name", "sku", "description",
        "particulars",
    ),
    "region": (
        "region", "city", "area", "territory", "zone", "province", "location",
        "branch",
    ),
    "sales_row_id": (
        "sales_row_id", "id", "ref", "reference", "invoice_no", "invoice_number",
        "order_no", "entry_no",
    ),
}

#: Without all four of these there is nothing to aggregate: no month without a
#: date, no revenue without an amount, no breakdowns without the dimensions.
_REQUIRED = ("date", "amount", "customer_name", "product")

#: The numeric core of a money cell, anchoring on the digits so `Rs. 45,900/-`
#: survives the same way it does in the ledger reader.
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
        raise SalesReadError(
            f"the sales data is missing required column(s): {', '.join(missing)}. "
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


def _reject_ragged_csv(content: bytes) -> None:
    """Refuse a CSV whose rows are wider than its header.

    pandas has no error for that case: by default it takes the first data
    column for an index and shifts every column left, and with `index_col=False`
    it drops the end of the row instead. Either way an unquoted `Rs. 45,900` is
    read as a different number without a word — and a silent misread is the one
    failure an audit layer must never have. So the field counts are checked
    here, with a real CSV reader, before pandas ever sees the file.
    """
    try:
        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"), newline="")))
    except UnicodeDecodeError as exc:
        raise SalesReadError(f"the sales data is not UTF-8 text: {exc}") from exc
    if not rows:
        return
    width = len(rows[0])
    for number, row in enumerate(rows[1:], start=2):
        if len(row) > width:
            raise SalesReadError(
                f"row {number} of the sales CSV has {len(row)} fields but the "
                f"header has {width}. If a value contains the delimiter — an "
                'amount like Rs. 45,900 — the field must be quoted: "Rs. 45,900"'
            )


def _read_frame(content: bytes, filename: str) -> pd.DataFrame:
    lowered = filename.lower()
    if lowered.endswith(".csv"):
        _reject_ragged_csv(content)
        # utf-8-sig: Excel writes a BOM ahead of the header, and an unstripped
        # one would garble the first column name for the alias lookup.
        return pd.read_csv(
            io.BytesIO(content),
            dtype=object,
            keep_default_na=False,
            encoding="utf-8-sig",
        )
    if lowered.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(io.BytesIO(content), dtype=object)
    raise SalesReadError(
        f"unsupported sales data format: {filename!r}. Expected .xlsx, .xls, or .csv."
    )


def _optional_text(row: pd.Series, columns: dict[str, str], name: str) -> str | None:
    if name not in columns:
        return None
    value = row[columns[name]]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def read_sales_data(
    document_id: str,
    filename: str,
    content: bytes,
    *,
    dayfirst: bool = True,
    currency: str = "PKR",
) -> list[SalesRecord]:
    """Read a sales export into `SalesRecord` objects.

    Args:
        document_id: The stored document this export came from.
        filename: Used to pick the reader. `.xlsx`, `.xls`, `.xlsm`, or `.csv`.
        content: The raw file bytes.
        dayfirst: Parse ambiguous dates as DD/MM/YYYY. True by default, which is
            the Pakistani convention — `03/06/2026` is 3 June, not 6 March.
        currency: ISO code recorded on every row.

    Returns:
        One `SalesRecord` per usable row, in file order. Rows missing the date,
        the amount, the customer, or the product are skipped as blank or
        separator rows, and counted in a log line rather than silently dropped.

    Raises:
        SalesReadError: The format is unsupported, a required column is absent,
            the file is malformed, or no usable rows were found.
    """
    frame = _read_frame(content, filename)
    if frame.empty:
        raise SalesReadError("the sales data has no rows")

    columns = _resolve_columns(frame)
    dates = pd.to_datetime(
        frame[columns["date"]], errors="coerce", dayfirst=dayfirst
    )

    records: list[SalesRecord] = []
    skipped = 0
    for position, (index, row) in enumerate(frame.iterrows()):
        # Spreadsheet row as a human sees it: header is row 1, data starts at 2.
        row_number = position + 2
        when = dates.iloc[position]
        amount = _to_decimal(row[columns["amount"]])
        customer = _optional_text(row, columns, "customer_name")
        product = _optional_text(row, columns, "product")

        if pd.isna(when) or amount is None or not customer or not product:
            skipped += 1
            continue

        raw_id = (
            row[columns["sales_row_id"]] if "sales_row_id" in columns else None
        )
        sales_row_id = ""
        if raw_id is not None and not (
            isinstance(raw_id, float) and pd.isna(raw_id)
        ):
            sales_row_id = str(raw_id).strip()

        records.append(
            SalesRecord(
                sales_row_id=sales_row_id or f"SAL-{row_number:04d}",
                date=when.date(),
                amount=amount,
                customer_name=customer,
                product=product,
                region=_optional_text(row, columns, "region"),
                currency=currency,
                source=Provenance(document_id=document_id, row_number=row_number),
            )
        )

    if not records:
        raise SalesReadError(
            "no usable rows in the sales data: every row was missing a date, an "
            "amount, a customer, or a product"
        )
    if skipped:
        logger.info(
            "Sales data %s: skipped %s incomplete row(s).", document_id, skipped
        )
    return records


# --------------------------------------------------------------------------- #
# 2. The analysis
# --------------------------------------------------------------------------- #


def _share(revenue: Decimal, total: Decimal) -> float:
    """Percent of the total, or 0.0 when the total makes the ratio meaningless."""
    if total <= 0:
        return 0.0
    return round(float(Decimal(100) * revenue / total), 2)


def _ranked(frame: pd.DataFrame, key: str) -> list[tuple[str, Decimal, int]]:
    """Group revenue by `key`, highest revenue first, then by name.

    The sort is what makes two runs over the same records produce the same
    list; the schema rejects a breakdown that arrives in any other order.
    """
    rows = [
        (str(name), sum(group["amount"], Decimal(0)), len(group))
        for name, group in frame.groupby(key, sort=False)
    ]
    rows.sort(key=lambda row: (-row[1], row[0]))
    return rows


def _negative_amounts(records: list[SalesRecord]) -> list[dict]:
    """A sale with a negative amount: a refund, a correction, or a typo."""
    return [
        {
            "kind": "negative-amount",
            "row_id": record.sales_row_id,
            "month": None,
            "related": [],
            "explanation": (
                f"sale of {_money(record.amount)} to {record.customer_name} on "
                f"{record.date.isoformat()} is negative — a refund, a correction, "
                "or a sign error in the export"
            ),
        }
        for record in records
        if record.amount < 0
    ]


def _duplicate_transactions(frame: pd.DataFrame) -> list[dict]:
    """The same date, customer, product, and amount, more than once.

    Genuine repeat purchases do land on the same key, which is why this is a
    finding for a human and not a verdict: the explanation says how many rows
    share the key and names them all.
    """
    findings: list[dict] = []
    if frame.empty:
        return findings
    keyed = frame.groupby(
        ["date", "customer_name", "product", "amount"], sort=False, dropna=False
    )
    for _key, group in keyed:
        if len(group) < 2:
            continue
        ids = list(group["sales_row_id"])
        first = group.iloc[0]
        findings.append(
            {
                "kind": "duplicate-transaction",
                "row_id": ids[0],
                "month": None,
                "related": ids,
                "explanation": (
                    f"{len(ids)} identical rows — {first['customer_name']}, "
                    f"{first['product']}, {_money(first['amount'])} on "
                    f"{first['date'].isoformat()} — share one key"
                ),
            }
        )
    return findings


def _revenue_spikes(monthly: list[MonthlyRevenue]) -> list[dict]:
    """A month far from the median month: more than double it, or under half.

    Against the median rather than the mean so one enormous month cannot lift
    the bar high enough to hide behind. Months are compared only when there
    are at least `SPIKE_MIN_MONTHS` of them.
    """
    if len(monthly) < SPIKE_MIN_MONTHS:
        return []
    median = statistics.median([entry.revenue for entry in monthly])
    if median <= 0:
        return []

    findings: list[dict] = []
    for entry in monthly:
        if entry.revenue > median * SPIKE_FACTOR:
            findings.append(
                {
                    "kind": "revenue-spike",
                    "row_id": None,
                    "month": entry.month,
                    "related": [],
                    "explanation": (
                        f"{entry.month} revenue of {_money(entry.revenue)} is more "
                        f"than double the median month ({_money(median)})"
                    ),
                }
            )
        elif entry.revenue < median / SPIKE_FACTOR:
            findings.append(
                {
                    "kind": "revenue-spike",
                    "row_id": None,
                    "month": entry.month,
                    "related": [],
                    "explanation": (
                        f"{entry.month} revenue of {_money(entry.revenue)} is less "
                        f"than half the median month ({_money(median)})"
                    ),
                }
            )
    return findings


def _large_transactions(records: list[SalesRecord]) -> list[dict]:
    """A sale far above the median sale: worth a look, not a conclusion."""
    if len(records) < LARGE_TRANSACTION_MIN_SAMPLE:
        return []
    median = statistics.median([record.amount for record in records])
    if median <= 0:
        return []
    return [
        {
            "kind": "large-transaction",
            "row_id": record.sales_row_id,
            "month": None,
            "related": [],
            "explanation": (
                f"{record.sales_row_id}: {_money(record.amount)} from "
                f"{record.customer_name} is more than {LARGE_TRANSACTION_FACTOR}× "
                f"the median sale ({_money(median)})"
            ),
        }
        for record in records
        if record.amount > median * LARGE_TRANSACTION_FACTOR
    ]


def _money(value: Decimal) -> str:
    return f"{value:,.2f}"


def analyze_sales(records: list[SalesRecord]) -> SalesAnalyticsResult:
    """Aggregate sales records into the full analytics readout.

    Pure arithmetic: pandas groups the rows, Decimal keeps the money exact, and
    the breakdowns partition the records — by month and by product they each
    sum back to `total_revenue` and `record_count`, which the schema enforces.

    Args:
        records: The sales rows, typically from every SALES_DATA document in a
            case concatenated in document order.

    Returns:
        A `SalesAnalyticsResult`. Empty input yields an empty readout rather
        than an error — the caller decides whether no sales data is exceptional,
        and the pipeline only calls this when there is some.
    """
    generated_at = datetime.now(timezone.utc)
    if not records:
        return SalesAnalyticsResult(
            record_count=0,
            total_revenue=Decimal(0),
            document_ids=[],
            generated_at=generated_at,
        )

    frame = pd.DataFrame(
        {
            "sales_row_id": [record.sales_row_id for record in records],
            "date": [record.date for record in records],
            "customer_name": [record.customer_name for record in records],
            "product": [record.product for record in records],
            "region": [record.region for record in records],
            "amount": [record.amount for record in records],
        }
    )
    # Lexicographic order on YYYY-MM is chronological order, which is the order
    # the schema requires of monthly_revenue.
    frame["month"] = frame["date"].map(lambda day: f"{day.year:04d}-{day.month:02d}")

    total = sum((record.amount for record in records), Decimal(0))

    monthly = [
        MonthlyRevenue(
            month=month,
            revenue=sum(group["amount"], Decimal(0)),
            transaction_count=len(group),
        )
        for month, group in frame.groupby("month", sort=True)
    ]
    products = [
        ProductRevenue(
            product=name,
            revenue=revenue,
            transaction_count=count,
            share=_share(revenue, total),
        )
        for name, revenue, count in _ranked(frame, "product")
    ]
    # dropna is the default: rows without a region are simply not in this
    # breakdown, rather than being filed under a label they never carried.
    regions = [
        RegionSummary(
            region=name,
            revenue=revenue,
            transaction_count=count,
            share=_share(revenue, total),
        )
        for name, revenue, count in _ranked(frame, "region")
    ]
    customers = [
        CustomerSummary(
            customer_name=name,
            revenue=revenue,
            transaction_count=count,
            share=_share(revenue, total),
        )
        for name, revenue, count in _ranked(frame, "customer_name")
    ][:TOP_CUSTOMERS]

    records_by_id = {record.sales_row_id: record for record in records}
    findings = (
        _negative_amounts(records)
        + _duplicate_transactions(frame)
        + _revenue_spikes(monthly)
        + _large_transactions(records)
    )
    anomalies = [
        Anomaly(
            anomaly_id=f"ANM-{position:04d}",
            kind=finding["kind"],
            explanation=finding["explanation"],
            source_row_id=finding["row_id"],
            related_row_ids=list(finding["related"]),
            month=finding["month"],
            source=(
                records_by_id[finding["row_id"]].source
                if finding["row_id"] in records_by_id
                else None
            ),
        )
        for position, finding in enumerate(findings, start=1)
    ]

    return SalesAnalyticsResult(
        record_count=len(records),
        period_start=min(record.date for record in records),
        period_end=max(record.date for record in records),
        total_revenue=total,
        monthly_revenue=monthly,
        revenue_by_product=products,
        top_customers=customers,
        sales_by_region=regions,
        anomalies=anomalies,
        document_ids=sorted({record.source.document_id for record in records}),
        generated_at=generated_at,
    )
