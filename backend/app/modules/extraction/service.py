"""Public interface of the extraction module.

This is the only file other modules may import from `modules/extraction/`. It
accepts and returns `app/shared/` schema objects exclusively — never raw dicts.

What this module does:

- Renders PDFs to page images with PyMuPDF (no poppler on the deploy box).
- Reads those images with Qwen VL via Alibaba Cloud Model Studio, returning a
  value, a confidence, and **source provenance** for every field.
- Reads the ledger with pandas. **No AI on that path** — a spreadsheet is
  already structured, and a model could only misread what is sitting in a cell.
- Re-reads low-confidence fields with a verification pass that reports agreement
  and never resolves it.

What it must never do (see the module README): perform matching or any
cross-document math, emit a value without confidence and provenance, or fabricate
a value for an unreadable field.

Typical use::

    result = extract_document("DOC-INV-0431", DocumentType.INVOICE,
                              "smw-0431.jpg", image_bytes)
    if result.needs_human_review:
        ...  # the two passes disagreed on money; a human decides
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from app.modules.extraction import demo_mode
from app.modules.extraction.bank_reader import (
    BankStatementReadError,
    read_bank_statement,
)
from app.modules.extraction.ledger_reader import LedgerReadError, read_ledger
from app.modules.extraction.page_images import (
    PageImage,
    image_bytes_to_page_image,
    pdf_page_count,
    pdf_to_page_images,
    render_pdf_page,
)
from app.modules.extraction.prompts import (
    EXTRACTION_FIELDS,
    STATEMENT_FIELDS,
    extraction_messages,
    statement_messages,
    verification_messages,
)
from app.modules.extraction.qwen_client import (
    QwenError,
    QwenResponseError,
    QwenTransportError,
    QwenVisionClient,
)
from app.modules.extraction.settings import ExtractionSettings, get_settings
from app.shared.schemas import (
    MONETARY_FIELD_NAMES,
    BankTransaction,
    Confidence,
    DocumentType,
    ExtractedField,
    ExtractedRow,
    ExtractionResult,
    FieldDisagreement,
    Invoice,
    LedgerEntry,
    Provenance,
    SecondOpinion,
    VerificationOutcome,
)

__all__ = [
    "BankStatementReadError",
    "ExtractionError",
    "LedgerReadError",
    "PageImage",
    "QwenError",
    "QwenResponseError",
    "QwenTransportError",
    "bank_transactions_from",
    "extract_document",
    "extract_page",
    "extract_statement_page",
    "document_page_count",
    "invoices_from",
    "pdf_to_page_images",
    "read_bank_statement",
    "read_ledger",
    "render_document_page",
    "verify_page",
]

#: Bank-statement extensions that are read deterministically with pandas
#: instead of by the vision model. Every Pakistani bank's internet banking can
#: export one of these, and a statement read this way carries no extraction
#: uncertainty at all: there is no model to be unsure, no API to be down, and
#: no cost per page. Reserve the vision model for the paper that has no
#: machine-readable form.
SPREADSHEET_STATEMENT_SUFFIXES = (".csv", ".xlsx", ".xlsm", ".xls")


def statement_is_a_spreadsheet(filename: str) -> bool:
    """Whether this bank statement should be read by pandas rather than Qwen."""
    return filename.lower().endswith(SPREADSHEET_STATEMENT_SUFFIXES)

logger = logging.getLogger(__name__)


class ExtractionError(RuntimeError):
    """Extraction could not produce a usable result for a document."""


#: Which confidences trigger the verification pass, by threshold setting.
_VERIFY_SETS: dict[str, frozenset[Confidence]] = {
    "low": frozenset({Confidence.LOW}),
    "medium": frozenset({Confidence.LOW, Confidence.MEDIUM}),
    "high": frozenset({Confidence.LOW, Confidence.MEDIUM, Confidence.HIGH}),
}


# --------------------------------------------------------------------------- #
# 1. Documents to page images
# --------------------------------------------------------------------------- #
#
# `pdf_to_page_images(content, dpi)` is re-exported from `page_images` above.


def _is_pdf(content: bytes, filename: str) -> bool:
    return filename.lower().endswith(".pdf") or content[:5] == b"%PDF-"


def _pages_for(content: bytes, filename: str, dpi: int) -> list[PageImage]:
    """Render whatever arrived — PDF or photo — into page images."""
    if _is_pdf(content, filename):
        return pdf_to_page_images(content, dpi=dpi)
    return [image_bytes_to_page_image(content)]


def document_page_count(content: bytes, filename: str) -> int:
    """How many pages a stored document has: a PDF's count, or 1 for a photo.

    Raises:
        ValueError: The bytes are neither a readable PDF nor a supported image.
    """
    if _is_pdf(content, filename):
        return pdf_page_count(content)
    image_bytes_to_page_image(content)  # validates the format
    return 1


def render_document_page(
    content: bytes, filename: str, page: int, *, dpi: int = 110
) -> PageImage:
    """One page of a stored document as an image, for the evidence viewer.

    The same renderer the model's pages come from, so the page a human sees
    is the page the provenance coordinates were measured on. A photographed
    invoice has exactly one page and is returned as-is.

    Raises:
        ValueError: Unreadable bytes, or `page` out of range.
    """
    if _is_pdf(content, filename):
        return render_pdf_page(content, page, dpi=dpi)
    if page != 1:
        raise ValueError("an image document has exactly one page")
    return image_bytes_to_page_image(content)


# --------------------------------------------------------------------------- #
# 2. One page through Qwen VL
# --------------------------------------------------------------------------- #


def extract_page(
    image: PageImage,
    document_id: str,
    *,
    page_count: int = 1,
    client: QwenVisionClient | None = None,
    settings: ExtractionSettings | None = None,
) -> list[ExtractedField]:
    """Read one page image with Qwen VL.

    Args:
        image: The rendered page.
        document_id: Recorded in every field's provenance.
        page_count: Total pages, so the model knows where it is in the document.
        client: Injected in tests. Built from settings when omitted.
        settings: Injected in tests. Read from the environment when omitted.

    Returns:
        One `ExtractedField` per field the model reported, each carrying its
        confidence and the page region or text snippet it was read from. Fields
        the model could not read come back with `unreadable=True` and no value —
        never a fabricated one.

    Raises:
        QwenTransportError: Qwen never answered.
        QwenResponseError: Qwen answered with unparseable JSON, twice.
    """
    settings = settings or get_settings()
    owned = client is None
    client = client or QwenVisionClient(settings=settings)
    try:
        payload = client.complete_json(
            extraction_messages(image.as_data_url(), image.page, page_count),
            model=settings.vl_model,
        )
    finally:
        if owned:
            client.close()

    entries = payload.get("fields")
    if not isinstance(entries, list):
        raise QwenResponseError("Qwen's reply had no 'fields' array")

    fields: list[ExtractedField] = []
    for entry in entries:
        field = _to_extracted_field(entry, document_id, image.page)
        if field is not None:
            fields.append(field)
    return fields


def _to_extracted_field(
    entry: object, document_id: str, page: int
) -> ExtractedField | None:
    """Map one raw model entry onto the shared schema, or drop it if unusable."""
    if not isinstance(entry, dict):
        logger.warning("Dropping a non-object entry from Qwen: %r", entry)
        return None

    name = str(entry.get("field") or "").strip()
    if name not in EXTRACTION_FIELDS:
        logger.warning("Dropping unexpected field %r from Qwen", name)
        return None

    unreadable = bool(entry.get("unreadable"))
    value = entry.get("value")
    if value is None or (isinstance(value, str) and not value.strip()):
        # A missing value is an unreadable field, whatever the model claimed.
        unreadable, value = True, None
    elif unreadable:
        value = None

    if not unreadable and name in MONETARY_FIELD_NAMES:
        value = _as_number(value, fallback=value)

    snippet = entry.get("text_snippet")
    snippet = snippet.strip() if isinstance(snippet, str) and snippet.strip() else None
    bbox = _clean_bbox(entry.get("bbox"))
    if bbox is None and snippet is None:
        # Reliability rule 3: no provenance, no output. The verbatim reading is
        # the weakest acceptable locator, so fall back to it rather than emit a
        # value a human cannot trace.
        snippet = str(value) if value is not None else None
        if snippet is None:
            logger.warning("Dropping %r from %s p%s: no usable provenance", name, document_id, page)
            return None

    try:
        return ExtractedField(
            field=name,
            value=value,
            extraction_confidence=_as_confidence(entry.get("extraction_confidence")),
            source=Provenance(
                document_id=document_id, page=page, bbox=bbox, text_snippet=snippet
            ),
            unreadable=unreadable,
        )
    except ValueError as error:
        logger.warning("Dropping %r from %s p%s: %s", name, document_id, page, error)
        return None


def _as_confidence(raw: object) -> Confidence:
    """Map the model's confidence word, defaulting to `low` when it is unclear.

    Defaulting down is deliberate: an unrecognised confidence means we do not
    know how sure the model was, and "we do not know" must never read as "high".
    """
    try:
        return Confidence(str(raw).strip().lower())
    except ValueError:
        logger.warning("Unrecognised confidence %r from Qwen, treating as low", raw)
        return Confidence.LOW


def _clean_bbox(raw: object) -> list[float] | None:
    """Accept a bbox only if it is four sane normalised coordinates."""
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        box = [float(coordinate) for coordinate in raw]
    except (TypeError, ValueError):
        return None
    if any(coordinate < 0.0 or coordinate > 1.0 for coordinate in box):
        return None
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        return None
    return box


def _as_number(raw: object, fallback: object = None) -> object:
    """Parse a money reading like `'Rs. 312,880/-'` into a float, or give up.

    The verbatim characters stay in `text_snippet`; this is only so downstream
    code has a number to work with. If it does not parse cleanly the raw reading
    is kept — better an unparsed string than a wrong number.
    """
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    if not isinstance(raw, str):
        return fallback
    cleaned = "".join(c for c in raw if c.isdigit() or c in ".-").strip("-.")
    negative = raw.strip().startswith("(") or raw.strip().startswith("-")
    if not cleaned or cleaned.count(".") > 1:
        return fallback
    try:
        number = float(cleaned)
    except ValueError:
        return fallback
    return -number if negative else number


def extract_statement_page(
    image: PageImage,
    document_id: str,
    *,
    page_count: int = 1,
    start_index: int = 0,
    client: QwenVisionClient | None = None,
    settings: ExtractionSettings | None = None,
) -> list[ExtractedRow]:
    """Read one bank-statement page as a table of transaction rows.

    A statement is a table, not a form: one page holds dozens of transactions,
    so it is read row by row rather than as a set of document-level values.

    Args:
        image: The rendered statement page.
        document_id: Recorded in every field's provenance.
        page_count: Total pages in the document.
        start_index: Row numbering offset, so rows stay unique across pages.
        client: Injected in tests.
        settings: Injected in tests.

    Returns:
        One `ExtractedRow` per transaction, each carrying its own fields with
        confidence and provenance. Rows with no date or no amount are dropped —
        they are headers, subtotals, or carried-forward lines, not transactions.
    """
    settings = settings or get_settings()
    owned = client is None
    client = client or QwenVisionClient(settings=settings)
    try:
        payload = client.complete_json(
            statement_messages(image.as_data_url(), image.page, page_count),
            model=settings.vl_model,
        )
    finally:
        if owned:
            client.close()

    raw_rows = payload.get("transactions")
    if not isinstance(raw_rows, list):
        raise QwenResponseError("Qwen's reply had no 'transactions' array")

    rows: list[ExtractedRow] = []
    for offset, raw in enumerate(raw_rows):
        if not isinstance(raw, dict):
            continue
        confidence = _as_confidence(raw.get("extraction_confidence"))
        bbox = _clean_bbox(raw.get("bbox"))
        snippet = raw.get("text_snippet")
        snippet = snippet.strip() if isinstance(snippet, str) and snippet.strip() else None

        fields: list[ExtractedField] = []
        for name in STATEMENT_FIELDS:
            value = raw.get(name)
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            if name in MONETARY_FIELD_NAMES:
                value = _as_number(value, fallback=value)
            locator = snippet or (str(value) if bbox is None else None)
            try:
                fields.append(
                    ExtractedField(
                        field=name,
                        value=value,
                        extraction_confidence=confidence,
                        source=Provenance(
                            document_id=document_id,
                            page=image.page,
                            bbox=bbox,
                            text_snippet=locator,
                        ),
                    )
                )
            except ValueError as error:
                logger.warning("Dropping %r on %s p%s: %s", name, document_id, image.page, error)

        names = {field.field for field in fields}
        if not {"date", "amount"} <= names:
            # A header, a subtotal, or a carried-forward line, not a transaction.
            continue
        rows.append(
            ExtractedRow(
                row_id=f"BNK-{start_index + len(rows) + 1:04d}",
                page=image.page,
                fields=fields,
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# 3. The ledger: pandas only
# --------------------------------------------------------------------------- #
#
# `read_ledger(document_id, filename, content)` is re-exported from
# `ledger_reader` above. It imports pandas and the shared schemas, and nothing
# else. There is no code path from a ledger cell to a model.


# --------------------------------------------------------------------------- #
# 4. The verification pass
# --------------------------------------------------------------------------- #


def verify_page(
    image: PageImage,
    fields: list[ExtractedField],
    *,
    client: QwenVisionClient | None = None,
    settings: ExtractionSettings | None = None,
) -> VerificationOutcome:
    """Re-read low-confidence fields and report whether the two passes agree.

    This is a checker, not a second guesser: it is shown the image *and* the
    first reading, and asked whether they match. It reports agreement per field
    and stops. When the readings differ on a monetary field the outcome is
    always `needs_human_review=True` — there is no branch in this function, and
    no field in `VerificationOutcome`, where the AI could pick a winner.

    Only fields at or below `EXTRACTION_CONFIDENCE_THRESHOLD` (default: `low`)
    are sent, because verification doubles the token cost of a page.

    Args:
        image: The same page the fields were read from.
        fields: The first pass's output for that page.
        client: Injected in tests.
        settings: Injected in tests.

    Returns:
        A `VerificationOutcome`. If nothing was worth checking, the outcome
        carries `second_opinion.ran=False` and no disagreements.
    """
    settings = settings or get_settings()
    to_check = [field for field in fields if _should_verify(field, settings)]

    if not to_check:
        return VerificationOutcome(
            second_opinion=SecondOpinion(
                ran=False, model=settings.second_opinion_model, agrees=True
            ),
            needs_human_review=False,
        )

    owned = client is None
    client = client or QwenVisionClient(settings=settings)
    try:
        payload = client.complete_json(
            verification_messages(
                image.as_data_url(),
                [
                    {
                        "field": field.field,
                        "value": field.value,
                        "text_snippet": field.source.text_snippet,
                    }
                    for field in to_check
                ],
            ),
            model=settings.second_opinion_model,
        )
    finally:
        if owned:
            client.close()

    checks = payload.get("checks")
    if not isinstance(checks, list):
        raise QwenResponseError("the verification reply had no 'checks' array")

    first_by_name = {field.field: field for field in to_check}
    disagreements: list[FieldDisagreement] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        name = str(check.get("field") or "").strip()
        original = first_by_name.get(name)
        if original is None or check.get("agrees") is True:
            continue
        second = check.get("reading")
        if name in MONETARY_FIELD_NAMES:
            second = _as_number(second, fallback=second)
        disagreements.append(
            FieldDisagreement(
                field=name,
                first_reading=original.value,
                second_reading=second if isinstance(second, (str, int, float)) else None,
            )
        )

    return VerificationOutcome(
        second_opinion=SecondOpinion(
            ran=True,
            model=settings.second_opinion_model,
            agrees=not disagreements,
            disagreements=disagreements,
        ),
        # Any disagreement escalates. The schema requires it for monetary
        # fields; we do not soften it for the others either.
        needs_human_review=bool(disagreements),
    )


def _should_verify(field: ExtractedField, settings: ExtractionSettings) -> bool:
    if field.unreadable:
        return False  # Nothing to check: there is no value to compare against.
    triggers = _VERIFY_SETS.get(settings.verify_at_or_below, _VERIFY_SETS["low"])
    return field.extraction_confidence in triggers


# --------------------------------------------------------------------------- #
# 5. Assembling typed rows for the deterministic modules
# --------------------------------------------------------------------------- #
#
# `matching/` takes `Invoice` and `BankTransaction` objects, not loose fields.
# Turning one into the other is extraction's job: it is the only place that
# knows how a reading maps onto a column. No arithmetic happens here — values
# are typed and carried across, never combined.


def invoices_from(result: ExtractionResult) -> list[Invoice]:
    """Build the `Invoice` an invoice document describes, if it is complete.

    Returns an empty list when a required value was unreadable — an invoice
    missing its amount cannot be matched, and inventing one would be worse than
    reporting nothing.
    """
    if result.document_type is not DocumentType.INVOICE:
        return []

    values = {field.field: field for field in result.fields if not field.unreadable}
    amount = _as_decimal(values.get("amount"))
    when = _as_date(values.get("date"))
    party = _as_text(values.get("party_name"))
    number = _as_text(values.get("invoice_number")) or result.document_id

    if amount is None or when is None or not party:
        logger.warning(
            "Cannot assemble an invoice from %s: missing %s",
            result.document_id,
            ", ".join(
                name
                for name, present in (
                    ("amount", amount is not None),
                    ("date", when is not None),
                    ("party_name", bool(party)),
                )
                if not present
            ),
        )
        return []

    source = values["amount"].source
    return [
        Invoice(
            invoice_id=result.document_id,
            invoice_number=number,
            date=when,
            amount=amount,
            party_name=party,
            source=source,
        )
    ]


def bank_transactions_from(result: ExtractionResult) -> list[BankTransaction]:
    """Build one `BankTransaction` per statement row that has a date and amount."""
    if result.document_type is not DocumentType.BANK_STATEMENT:
        return []

    transactions: list[BankTransaction] = []
    for row in result.rows:
        values = {field.field: field for field in row.fields if not field.unreadable}
        amount = _as_decimal(values.get("amount"))
        when = _as_date(values.get("date"))
        if amount is None or when is None:
            continue
        transactions.append(
            BankTransaction(
                bank_row_id=row.row_id,
                date=when,
                amount=amount,
                description=_as_text(values.get("description")) or row.row_id,
                balance=_as_decimal(values.get("balance")),
                source=values["amount"].source,
            )
        )
    return transactions


def _as_text(field: ExtractedField | None) -> str | None:
    if field is None or field.value is None:
        return None
    text = str(field.value).strip()
    return text or None


def _as_decimal(field: ExtractedField | None) -> Decimal | None:
    if field is None or field.value is None:
        return None
    try:
        return Decimal(str(_as_number(field.value, fallback=field.value)))
    except (InvalidOperation, ValueError):
        return None


#: Formats seen from the model, in preference order. ISO first because the
#: prompt asks for it; the rest are what Pakistani documents actually print.
_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y")


def _as_date(field: ExtractedField | None) -> date | None:
    if field is None or field.value is None:
        return None
    text = str(field.value).strip()
    for pattern in _DATE_FORMATS:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    logger.warning("Could not parse a date from %r", text)
    return None


# --------------------------------------------------------------------------- #
# 6. The whole document
# --------------------------------------------------------------------------- #


def extract_document(
    document_id: str,
    document_type: DocumentType,
    filename: str,
    content: bytes,
    *,
    client: QwenVisionClient | None = None,
    settings: ExtractionSettings | None = None,
) -> ExtractionResult:
    """Read one uploaded document end to end.

    In `DEMO_MODE` this returns a cached result instead of calling Qwen — same
    schema, same downstream code path, no network.

    A ledger never reaches this function's model path: call `read_ledger`
    instead, and this raises if asked to send one to a vision model.

    Raises:
        ExtractionError: A ledger was passed, or no page yielded a single field.
        QwenTransportError: Qwen never answered.
        QwenResponseError: Qwen answered with unparseable JSON, twice.
    """
    settings = settings or get_settings()

    if document_type is DocumentType.LEDGER:
        raise ExtractionError(
            "the ledger is read by pandas, not by a model. Call read_ledger() instead."
        )

    if settings.demo_mode:
        return demo_mode.cached_extraction(document_id, document_type, filename)

    pages = _pages_for(content, filename, settings.page_image_dpi)
    owned = client is None
    client = client or QwenVisionClient(settings=settings)

    fields: list[ExtractedField] = []
    rows: list[ExtractedRow] = []
    verifications: list[VerificationOutcome] = []
    try:
        for image in pages:
            if document_type is DocumentType.BANK_STATEMENT:
                page_rows = extract_statement_page(
                    image,
                    document_id,
                    page_count=len(pages),
                    start_index=len(rows),
                    client=client,
                    settings=settings,
                )
                rows.extend(page_rows)
                verifications.extend(
                    _verify_rows(image, page_rows, client=client, settings=settings)
                )
            else:
                page_fields = extract_page(
                    image,
                    document_id,
                    page_count=len(pages),
                    client=client,
                    settings=settings,
                )
                fields.extend(page_fields)
                verifications.append(
                    verify_page(image, page_fields, client=client, settings=settings)
                )
    finally:
        if owned:
            client.close()

    if not fields and not rows:
        raise ExtractionError(
            f"Qwen returned no usable fields for {document_id} ({filename})"
        )

    return ExtractionResult(
        document_id=document_id,
        document_type=document_type,
        filename=filename,
        page_count=len(pages),
        extracted_at=datetime.now(timezone.utc),
        model=settings.vl_model,
        fields=fields,
        rows=rows,
        second_opinion=_merge(verifications, settings),
        needs_human_review=any(check.needs_human_review for check in verifications),
    )


#: Verifying a page costs a full image round-trip, so a statement page with
#: dozens of shaky rows is capped rather than allowed to run up the bill.
MAX_VERIFIED_ROWS_PER_PAGE = 5


def _verify_rows(
    image: PageImage,
    rows: list[ExtractedRow],
    *,
    client: QwenVisionClient,
    settings: ExtractionSettings,
) -> list[VerificationOutcome]:
    """Verify statement rows that contain a low-confidence reading.

    Row by row rather than page at a time, because a page holds many `amount`
    fields and the verifier matches its answers back by field name.
    """
    shaky = [
        row
        for row in rows
        if any(_should_verify(field, settings) for field in row.fields)
    ]
    if len(shaky) > MAX_VERIFIED_ROWS_PER_PAGE:
        logger.warning(
            "Page %s has %s low-confidence rows; verifying the first %s. "
            "The rest keep their low confidence and reach the reviewer unverified.",
            image.page,
            len(shaky),
            MAX_VERIFIED_ROWS_PER_PAGE,
        )
        shaky = shaky[:MAX_VERIFIED_ROWS_PER_PAGE]
    return [
        verify_page(image, row.fields, client=client, settings=settings) for row in shaky
    ]


def _merge(
    verifications: list[VerificationOutcome], settings: ExtractionSettings
) -> SecondOpinion | None:
    """Fold per-page verifications into the document's single second opinion."""
    ran = [check.second_opinion for check in verifications if check.second_opinion.ran]
    if not ran:
        return None
    disagreements = [
        disagreement for opinion in ran for disagreement in opinion.disagreements
    ]
    return SecondOpinion(
        ran=True,
        model=settings.second_opinion_model,
        agrees=not disagreements,
        disagreements=disagreements,
    )
