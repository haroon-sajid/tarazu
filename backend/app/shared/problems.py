"""Why an upload could not be used, said so the person who uploaded it can fix it.

Every reader in Tarazu can refuse a file: the ledger reader when there is no
amount column, the bank reader when a spreadsheet will not open, the analytics
reader when no row names a date, the pipeline when the document reader is
down. Each of them used to say so in its own words, and those words were
written for a log — `LedgerReadError: the ledger is missing required
column(s): amount, party_name` tells a developer everything and an auditor
nothing.

This module is the one place those refusals are worded. Every builder returns
a `ReadProblem`: a stable code, a title, a message that is complete on its own,
and the structure a screen needs to lay the refusal out as a guide — which
file, which columns it had, which it lacked, and what to do next. The readers
raise a `ReadProblemError` carrying it; the API turns it into a response; the
upload screen turns it into a dialog.

Nothing here computes or reads anything. It is copy, kept next to the schema
it fills so that the ledger reader and the sales reader cannot drift apart.
"""

from __future__ import annotations

from app.shared.schemas import ProblemField, ReadProblem, UploadSlot

__all__ = [
    "ReadProblemError",
    "SLOT_NAMES",
    "document_reader_unavailable",
    "duplicate_file",
    "empty_file",
    "empty_upload",
    "generic",
    "http_status_for",
    "missing_columns",
    "no_usable_fields",
    "no_usable_rows",
    "processing_failed",
    "too_large",
    "unreadable_file",
    "unsupported_format",
]

#: How each upload is named in a sentence.
SLOT_NAMES: dict[str, str] = {
    "ledger": "ledger",
    "bank_statement": "bank statement",
    "invoice": "invoice",
    "sales_data": "sales data",
}

#: The advice every column problem ends with, because it is true of every reader.
_HEADER_GUIDANCE: tuple[str, ...] = (
    "Open the file and look at its header row. Tarazu searches the first 30 "
    "rows of every sheet for the header, so title rows above it are fine.",
    "Column names are matched loosely: 'Txn Date', 'TXN_DATE', and 'Date' all "
    "count, and a currency in the name, such as 'Amount (PKR)', is fine too.",
)


class ReadProblemError(ValueError):
    """A reader refused a file. `problem` says why; `str()` is its message.

    A plain string is accepted too, for the rare refusal that has no richer
    structure to offer; it becomes a generic problem for the given slot so
    that every refusal still reaches the screen in the same shape.
    """

    def __init__(
        self,
        problem: ReadProblem | str,
        *,
        slot: UploadSlot | None = None,
        filename: str | None = None,
    ) -> None:
        if isinstance(problem, str):
            problem = generic(slot, filename, problem)
        super().__init__(problem.message)
        self.problem = problem


def _name(slot: UploadSlot | None) -> str:
    return SLOT_NAMES.get(slot or "", "file")


def _quoted(filename: str | None) -> str:
    return f" '{filename}'" if filename else ""


def _join(items: list[str]) -> str:
    """`a`, `a and b`, `a, b, and c`."""
    if len(items) <= 1:
        return "".join(items)
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def http_status_for(problem: ReadProblem) -> int:
    """The HTTP status a problem is answered with.

    A file the person can fix is `422`; a document reader that is down is a
    `502` because the fault is upstream of Tarazu; anything that broke inside
    is a `500`. The frontend keys its dialog off the problem, not the status.
    """
    if problem.code == "document_reader_unavailable":
        return 502
    if problem.code == "processing_failed":
        return 500
    return 422


# --------------------------------------------------------------------------- #
# Files the readers refuse
# --------------------------------------------------------------------------- #


def unsupported_format(
    slot: UploadSlot | None,
    filename: str | None,
    accepted: list[str],
    *,
    note: str | None = None,
) -> ReadProblem:
    """The extension is not one this slot reads."""
    name = _name(slot)
    accepted_text = ", ".join(accepted)
    message = (
        f"The {name}{_quoted(filename)} could not be read: unsupported {name} "
        f"format. Expected one of {accepted_text}."
    )
    if note:
        message += f" {note}"
    return ReadProblem(
        code="unsupported_format",
        title=f"This file type is not accepted as a {name}",
        message=message,
        document=slot,
        filename=filename,
        guidance=[
            f"Export the {name} again in one of the accepted formats: {accepted_text}.",
            "Renaming a file's extension does not convert it. Use the export or "
            "'Save as' command of the software it came from.",
        ],
    )


def unreadable_file(
    slot: UploadSlot | None,
    filename: str | None,
    reason: str,
    *,
    kind: str = "spreadsheet",
) -> ReadProblem:
    """The bytes could not be opened as what the extension says they are."""
    name = _name(slot)
    # The reader's own reason often opens with the same words this sentence
    # does ("could not open the PDF: ..."); say it once.
    for prefix in (f"could not open the {kind}:", "could not open the pdf:", "could not open the file:"):
        if reason.lower().startswith(prefix):
            reason = reason[len(prefix):].strip()
            break
    reason = reason.rstrip(".") or "the reader gave no reason"
    return ReadProblem(
        code="unreadable_file",
        title=f"The {name} could not be opened",
        message=(
            f"The {name}{_quoted(filename)} could not be opened as a {kind}: "
            f"{reason}. It may be damaged, password-protected, or a different "
            "kind of file behind a familiar extension."
        ),
        document=slot,
        filename=filename,
        guidance=[
            "Open the file on your computer to check that it is what its "
            "extension says. A file that will not open there will not open here.",
            "Remove any password or protection, then save a fresh copy.",
            (
                "Save it again as .xlsx or .csv from the software it came from, "
                "and upload the new copy."
                if kind == "spreadsheet"
                else "Export or scan it again and upload the new copy."
            ),
        ],
    )


def empty_upload(slot: UploadSlot | None, filename: str | None) -> ReadProblem:
    """Zero bytes arrived."""
    name = _name(slot)
    return ReadProblem(
        code="empty_file",
        title=f"The {name} is empty",
        message=(
            f"The {name}{_quoted(filename)} is empty: it arrived with no "
            "content at all. The upload may have been interrupted, or the file "
            "may not have finished saving when it was chosen."
        ),
        document=slot,
        filename=filename,
        guidance=[
            "Open the file on your computer and check that it has content and a size.",
            "Choose it again and upload. If it is on a network drive or a phone, "
            "copy it to the computer first.",
        ],
    )


def too_large(slot: UploadSlot | None, filename: str | None, size_mb: float, limit_mb: int) -> ReadProblem:
    """More bytes than one upload takes."""
    name = _name(slot)
    return ReadProblem(
        code="file_too_large",
        title=f"The {name} is too large to upload",
        message=(
            f"The {name}{_quoted(filename)} is {size_mb:.1f} MB; the limit is "
            f"{limit_mb} MB per file."
        ),
        document=slot,
        filename=filename,
        guidance=[
            "For a bank statement, export a shorter period, or the CSV rather "
            "than the PDF: the same transactions take a fraction of the space.",
            "For a scanned document, save it at a lower resolution or as a PDF "
            "rather than a photo per page.",
            "Split the period into two cases if it cannot be made smaller.",
        ],
    )


def empty_file(slot: UploadSlot | None, filename: str | None) -> ReadProblem:
    """The file opened, and there was nothing in it."""
    name = _name(slot)
    return ReadProblem(
        code="empty_file",
        title=f"The {name} has no rows",
        message=(
            f"The {name}{_quoted(filename)} could not be read: it has no rows. "
            "An export with only a header, or a blank sheet, gives Tarazu "
            "nothing to reconcile."
        ),
        document=slot,
        filename=filename,
        guidance=[
            "Open the file and check that the sheet holds the rows you expect.",
            "If the workbook has several sheets, the data should be on one of "
            "them with a header row; Tarazu reads every sheet and uses the "
            "first one it can make sense of.",
            "Export the period again and upload the new file.",
        ],
    )


def missing_columns(
    slot: UploadSlot | None,
    filename: str | None,
    found: list[str],
    missing: list[ProblemField],
    *,
    needs: str,
) -> ReadProblem:
    """The header names some of what is needed, but not all of it.

    Args:
        found: The header cells as written, of the row that came closest.
        missing: What the header does not name, with what would satisfy it.
        needs: The whole requirement in one phrase, for the guide — "the date,
            the amount, and who was paid".
    """
    name = _name(slot)
    labels = [field.label for field in missing]
    found_text = ", ".join(found) if found else "(no header found)"
    if len(missing) == 1:
        title = f"The {name} needs {_article(labels[0])} {labels[0]} column"
        what = f"no {labels[0].lower()} column was found"
    else:
        title = f"The {name} is missing {len(missing)} required columns"
        what = f"no {_join([label.lower() for label in labels])} columns were found"
    why = " ".join(field.why for field in missing)
    accepted = "; ".join(
        f"{field.label}: {', '.join(field.accepted_headers)}"
        for field in missing
        if field.accepted_headers
    )
    message = (
        f"The {name}{_quoted(filename)} could not be read: {what}. "
        f"Found columns: {found_text}. {why} "
        f"Add {'it' if len(missing) == 1 else 'them'} to the header row and "
        "upload the file again."
    )
    if accepted:
        message += f" Accepted header names — {accepted}."
    return ReadProblem(
        code="missing_columns",
        title=title,
        message=message,
        document=slot,
        filename=filename,
        found_columns=list(found),
        missing=list(missing),
        guidance=[
            _HEADER_GUIDANCE[0],
            f"The header must name {needs}.",
            _HEADER_GUIDANCE[1],
            "Save the file and upload it again.",
        ],
    )


def no_usable_rows(
    slot: UploadSlot | None,
    filename: str | None,
    *,
    needs: str,
    rows_seen: int,
    example: str | None = None,
    found: list[str] | None = None,
) -> ReadProblem:
    """The header was fine; not one row under it could be used."""
    name = _name(slot)
    message = (
        f"The {name}{_quoted(filename)} could not be read: no usable rows. "
        f"The header was recognised, but none of its {rows_seen} row(s) had "
        f"everything a row needs ({needs})."
    )
    if found:
        message += f" Found columns: {', '.join(found)}."
    if example:
        message += f" The first row reads: {example}."
    return ReadProblem(
        code="no_usable_rows",
        title=f"No usable rows in the {name}",
        message=message,
        document=slot,
        filename=filename,
        found_columns=list(found or []),
        guidance=[
            f"Each row Tarazu keeps needs {needs}. Rows without them — opening "
            "and closing balances, totals, blank separators — are skipped on "
            "purpose, but here nothing was left.",
            "Check that the date column holds dates (for example 02/06/2026 or "
            "2-Jun-2026) and the amount column holds numbers, not text such as "
            "'see note'.",
            "If the dates and amounts sit under different headers than the ones "
            "Tarazu recognised, rename those headers and upload again.",
        ],
    )


def duplicate_file(first: UploadSlot, second: UploadSlot, filename: str | None) -> ReadProblem:
    """The same bytes were uploaded in two different slots."""
    first_name, second_name = _name(first), _name(second)
    return ReadProblem(
        code="duplicate_file",
        title=f"The {first_name} and the {second_name} are the same file",
        message=(
            f"The file{_quoted(filename)} was uploaded as both the {first_name} "
            f"and the {second_name}. They are two different records — the "
            "client's books and the bank's — and reconciling a file against "
            "itself would match every row and prove nothing."
        ),
        document=second,
        filename=filename,
        guidance=[
            f"Upload the client's {first_name} in the {first_name} slot and the "
            f"bank's {second_name} in the {second_name} slot.",
            "If the client keeps a bank book rather than a ledger, that bank "
            "book is the ledger; the bank statement is the bank's own export.",
        ],
    )


def generic(slot: UploadSlot | None, filename: str | None, reason: str) -> ReadProblem:
    """A refusal with no richer structure than its reason."""
    name = _name(slot)
    return ReadProblem(
        code="unreadable",
        title=f"The {name} could not be read",
        message=f"The {name}{_quoted(filename)} could not be read: {reason}",
        document=slot,
        filename=filename,
        guidance=[
            "Open the file and check that it holds what its name says, with a "
            "header row naming its columns.",
            "Fix what the message describes, save the file, and upload it again.",
        ],
    )


# --------------------------------------------------------------------------- #
# Failures after the files were accepted
# --------------------------------------------------------------------------- #


def document_reader_unavailable(
    slot: UploadSlot | None, filename: str | None, reason: str
) -> ReadProblem:
    """The vision model could not be reached, or did not answer usably."""
    name = _name(slot)
    return ReadProblem(
        code="document_reader_unavailable",
        title="The document reader is unavailable",
        message=(
            f"Tarazu could not get the {name}{_quoted(filename)} read: the "
            f"document reader did not answer ({reason}). Nothing was matched or "
            "flagged, and the case is marked failed rather than left half-done."
        ),
        document=slot,
        filename=filename,
        guidance=[
            "Try the upload again in a few minutes; a busy reader usually recovers.",
            "For a bank statement, upload the CSV or Excel export from internet "
            "banking instead of the PDF. A spreadsheet is read exactly, with no "
            "document reader involved.",
            "If it keeps failing, tell your administrator: the reader's API key "
            "or network settings (EXTRACTION_*) may need attention, and "
            "DEMO_MODE runs on cached readings meanwhile.",
        ],
    )


def no_usable_fields(slot: UploadSlot | None, filename: str | None) -> ReadProblem:
    """The reader answered, and found nothing on the page it could use."""
    name = _name(slot)
    return ReadProblem(
        code="no_usable_fields",
        title=f"Nothing readable in the {name}",
        message=(
            f"The document reader found no usable values in the {name}"
            f"{_quoted(filename)}. It may be a blank page, a scan too faint to "
            f"read, or not a {name} at all. Nothing was matched or flagged, and "
            "the case is marked failed rather than left half-done."
        ),
        document=slot,
        filename=filename,
        guidance=[
            f"Open the file and check that it shows the {name} clearly, with "
            "the dates and amounts legible.",
            "For a photo, retake it flat, in good light, with the whole page in "
            "the frame and nothing covering the figures.",
            "For a bank statement, prefer the CSV or Excel export from internet "
            "banking: it is read exactly, with no reading step at all.",
        ],
    )


def processing_failed(reason: str) -> ReadProblem:
    """A step after reading — matching, rules, saving — raised."""
    return ReadProblem(
        code="processing_failed",
        title="The case could not be processed",
        message=(
            f"The documents were read, but a later step failed: {reason}. The "
            "case is marked failed, and nothing half-finished was saved as a "
            "review queue."
        ),
        guidance=[
            "Try the upload again; a passing fault does not repeat.",
            "If it fails the same way, tell your administrator and quote the "
            "case id. The full reason is in the server log.",
        ],
    )


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"
