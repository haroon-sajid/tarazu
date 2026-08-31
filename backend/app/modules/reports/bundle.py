"""The evidence bundle: one archive that can be handed to a reviewer.

A report says what the firm concluded. A bundle proves it. When a partner is
challenged — by a regulator, a court, an incoming auditor, or the client
themselves — the question is never only "what did you find" but "on what, and
who said so, and is this the file you actually produced". This module answers
all three in a single zip: the source documents, the generated report, every
human decision, the complete append-only trail, and a SHA-256 manifest that
lets anyone confirm that not one byte of it has moved since it was exported.

Nothing here is computed, corrected, or summarised. Every file in the archive
is a record as it already stood; the bundle only carries it. That is why this
function is pure — it takes bytes and schema objects the caller has already
read, and returns bytes. It touches no repository, no storage, no network, and
no model. Reliability rules 3 and 5 say provenance and the trail must exist;
this makes them portable, so the evidence survives leaving the product.

**The bundle's shape never depends on the case.** `corrections.json` and
`sign-offs.json` are written even when the case has none, as empty arrays.
A reviewer who finds a file missing has to work out whether the case had no
corrections or the export was incomplete, and an artefact that raises that
question has failed at the only job it has. An empty list is an answer; an
absent file is a doubt.

**The manifest does not hash itself,** because it cannot: a file's digest
changes the moment the digest is written into it. Every *other* file in the
archive is listed, so the manifest is the one file that has to be trusted
from elsewhere — the report digests it reprints were recorded in the system
at generation time and can be checked against the `reports` history.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import datetime

from pydantic import TypeAdapter

from app.shared.schemas import (
    AuditRecord,
    CaseRecord,
    ReportRecord,
    ReviewDecision,
    ReviewItem,
    SignOff,
    ValueCorrection,
)

__all__ = [
    "AUDIT_NAME",
    "CORRECTIONS_NAME",
    "DOCUMENTS_DIR",
    "MANIFEST_NAME",
    "README_NAME",
    "REPORTS_DIR",
    "REVIEW_QUEUE_NAME",
    "SIGN_OFFS_NAME",
    "build_bundle",
]

DOCUMENTS_DIR = "documents"
REPORTS_DIR = "reports"
AUDIT_NAME = "audit-trail.json"
REVIEW_QUEUE_NAME = "review-queue.json"
CORRECTIONS_NAME = "corrections.json"
SIGN_OFFS_NAME = "sign-offs.json"
MANIFEST_NAME = "MANIFEST.txt"
README_NAME = "README.txt"

#: Serialisers for the four JSON files. Pydantic writes the fields in
#: declaration order and renders `Decimal` as its exact digits and `datetime`
#: as ISO-8601, which a hand-rolled encoder would have to be trusted to get
#: right. Nothing is excluded: a null stays in the file, so two bundles of the
#: same case always have the same keys in the same places.
_AUDIT_JSON = TypeAdapter(list[AuditRecord])
_ITEMS_JSON = TypeAdapter(list[ReviewItem])
_CORRECTIONS_JSON = TypeAdapter(list[ValueCorrection])
_SIGN_OFFS_JSON = TypeAdapter(list[SignOff])

#: Characters a zip entry may carry but Windows refuses to write to disk.
#: A bundle that cannot be extracted is not evidence of anything.
_UNSAFE_CHARS = '<>:"|?*'


# --------------------------------------------------------------------------- #
# Naming
# --------------------------------------------------------------------------- #


def _safe_name(name: str) -> str:
    """One flat, extractable filename, with any path in it thrown away.

    Uploaded filenames arrive from clients, so they are untrusted text. A name
    carrying `../` would place a file outside the folder a reviewer extracts
    into, which is both a security hole and a bundle that no longer matches
    its own manifest. Only the last segment survives.
    """
    leaf = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(
        character
        for character in leaf
        if character.isprintable() and character not in _UNSAFE_CHARS
    ).strip(" .")
    return cleaned or "document"


def _unique(name: str, taken: set[str]) -> str:
    """`invoice.pdf`, then `invoice-2.pdf`, then `invoice-3.pdf`.

    Two clients' scans are called `scan.pdf` more often than not, and a bundle
    may not silently drop one of them. Disambiguation follows the order the
    caller passed the documents in, so the same case always produces the same
    names — a manifest whose paths shuffled between exports would prove nothing.

    Collisions are judged case-insensitively: `Invoice.PDF` and `invoice.pdf`
    are two files on Linux and one on Windows, and the archive has to extract
    intact on both.
    """
    if name.casefold() not in taken:
        taken.add(name.casefold())
        return name
    stem, dot, extension = name.rpartition(".")
    if not dot or not stem:
        stem, extension = name, ""
    counter = 2
    while True:
        candidate = f"{stem}-{counter}.{extension}" if extension else f"{stem}-{counter}"
        if candidate.casefold() not in taken:
            taken.add(candidate.casefold())
            return candidate
        counter += 1


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #


def _when(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M UTC")


def _json(adapter: TypeAdapter, value: list) -> bytes:
    """Indented JSON with a trailing newline, so the file reads in any editor."""
    return adapter.dump_json(value, indent=2) + b"\n"


def _label(label: str, value: str) -> str:
    return f"{label:<20}{value}"


# --------------------------------------------------------------------------- #
# The two plain-text files
#
# Written in ASCII and with `\n` line endings whatever the host, so the digest
# of the manifest is a property of the bundle rather than of the machine that
# exported it. Client names and notes are of course whatever the client wrote,
# which is why the files are encoded as UTF-8.
# --------------------------------------------------------------------------- #


README_TEXT = """\
TARAZU EVIDENCE BUNDLE
======================

What this is
------------
Everything needed to defend one audit engagement, in one archive: the
documents the client provided, the report produced from them, every decision
a named person recorded, and the complete audit trail of the engagement.

Nothing in this bundle was calculated when it was exported. Each file is the
record exactly as it already stood in the system; the export only copied it.

What is in it
-------------
documents/          The source documents as they were uploaded, unmodified.
                    Where two uploads shared a filename, the later one was
                    given a numbered name (invoice-2.pdf) to keep both.
reports/            The generated report, as PDF and as an Excel workbook.
review-queue.json   Every ledger row that was reviewed, with its match
                    result, the rules that flagged it, and the human
                    decision recorded against it -- who decided, and when.
audit-trail.json    Every recorded action on the case, oldest first. This
                    trail is append-only in the system: entries are never
                    edited or removed, only added.
corrections.json    Values a person corrected after the model misread them.
                    Both readings are kept. An empty list means the case has
                    none -- the file is always present, so a missing file is
                    never mistaken for an empty one.
sign-offs.json      Second-person sign-offs on the finished engagement.
                    Empty list when the case has none, for the same reason.
MANIFEST.txt        A summary of the engagement, followed by the SHA-256
                    digest of every other file in this archive.

How to check that nothing has changed
-------------------------------------
Extract the archive, then run one of the following from the folder you
extracted it into.

  Linux or macOS:

      sha256sum -c MANIFEST.txt

    Every listed file should report "OK". The command also prints a warning
    that some lines are improperly formatted: those are the summary lines at
    the top of the manifest, and the warning is expected.

  Windows, Command Prompt:

      certutil -hashfile audit-trail.json SHA256

    Repeat for each file and compare the digest with its line in
    MANIFEST.txt.

  Windows, PowerShell -- all files at once:

      Get-ChildItem -Recurse -File | Get-FileHash -Algorithm SHA256

MANIFEST.txt is not listed inside itself. A file cannot state its own
digest: writing the digest in would change it. To confirm the manifest
itself, compare the report digests it reprints -- those were recorded in
the system at the moment each report was generated, and are held in the
firm's report history independently of this archive.

What this is not
----------------
Tarazu reconciles the books, flags what needs attention, and explains it in
plain language. The AI assists, the human decides. Nothing in this bundle
was approved automatically: every decision names the person who made it and
the moment they made it, and every figure can be traced to the document,
page, or spreadsheet row it was read from.
"""


def _manifest_text(
    case: CaseRecord,
    items: list[ReviewItem],
    audit: list[AuditRecord],
    reports: list[ReportRecord],
    corrections: list[ValueCorrection],
    sign_offs: list[SignOff],
    document_count: int,
    report_file_count: int,
    digests: list[tuple[str, str]],
    *,
    generated_by: str,
    generated_at: datetime,
) -> str:
    approved = sum(1 for item in items if item.decision is ReviewDecision.APPROVED)
    rejected = sum(1 for item in items if item.decision is ReviewDecision.REJECTED)
    pending = sum(1 for item in items if item.decision is ReviewDecision.PENDING)
    period = (
        f"{case.period_start.isoformat()} to {case.period_end.isoformat()}"
        if case.period_start and case.period_end
        else "not determined"
    )

    lines = [
        "TARAZU EVIDENCE BUNDLE -- MANIFEST",
        "==================================",
        "",
        _label("Client", case.client_name),
        _label("Case", case.case_id),
        _label("Period", period),
        _label("Case status", case.status.value),
        _label("Exported by", generated_by),
        _label("Exported at", _when(generated_at)),
        "",
        "Contents",
        f"  Source documents    {document_count}",
        f"  Report files        {report_file_count}",
        f"  Review items        {len(items)} "
        f"({approved} approved, {rejected} rejected, {pending} pending)",
        f"  Audit records       {len(audit)}",
        f"  Corrections         {len(corrections)}",
        f"  Sign-offs           {len(sign_offs)}",
        f"  Report records      {len(reports)}",
        "",
        "Reports on record",
        "  The digest recorded in the system when each report was generated.",
        "  It should equal the digest listed below for the same file.",
        "",
    ]
    if reports:
        for report in reports:
            lines.append(
                f"  {report.report_id}  generated {_when(report.generated_at)} "
                f"by {report.generated_by}"
            )
            lines.append(f"    pdf    sha256={report.pdf_sha256}  {report.pdf_path}")
            lines.append(f"    excel  sha256={report.excel_sha256}  {report.excel_path}")
    else:
        lines.append("  None. No report had been generated for this case at export time.")
    lines.extend(
        [
            "",
            "Files in this bundle",
            "  SHA-256 of every other file in this archive, sorted by path.",
            "  MANIFEST.txt is absent from this list on purpose: a file cannot",
            "  state its own digest. See README.txt for how to check these.",
            "",
        ]
    )
    lines.extend(f"{digest}  {path}" for path, digest in digests)
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# The archive
# --------------------------------------------------------------------------- #


def _archive_date_time(stamp: datetime) -> tuple[int, int, int, int, int, int]:
    """The one timestamp every entry in the archive carries.

    Zip records a modification time per entry, and `zipfile` fills it from the
    wall clock, which would make two exports of one unchanged case differ in
    bytes and so in digest. The export's own time is the only time that means
    anything here. DOS timestamps start in 1980 and have two-second
    resolution, hence the clamping and the rounding.
    """
    year = min(max(stamp.year, 1980), 2107)
    return (year, stamp.month, stamp.day, stamp.hour, stamp.minute, stamp.second - stamp.second % 2)


def _write(
    archive: zipfile.ZipFile, path: str, data: bytes, date_time: tuple[int, int, int, int, int, int]
) -> None:
    """Add one entry with every byte of its header pinned.

    `create_system` and the permission bits are set explicitly rather than
    left to `zipfile`, which derives them from the host operating system: an
    export from a Windows machine and an export from Linux must produce the
    same archive, or the digest describes the server instead of the evidence.
    """
    info = zipfile.ZipInfo(path, date_time=date_time)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3  # Unix, on every host.
    info.external_attr = 0o644 << 16
    archive.writestr(info, data)


def build_bundle(
    case: CaseRecord,
    items: list[ReviewItem],
    audit: list[AuditRecord],
    reports: list[ReportRecord],
    corrections: list[ValueCorrection],
    sign_offs: list[SignOff],
    documents: list[tuple[str, bytes]],
    report_files: list[tuple[str, bytes]],
    *,
    generated_by: str,
    generated_at: datetime,
) -> bytes:
    """Pack one engagement into a zip a reviewer can verify without Tarazu.

    Pure: the caller reads the records and the file bytes, this assembles
    them. Nothing is fetched, recomputed, or asked of a model.

    The result is byte-reproducible. Two exports of an unchanged case at the
    same `generated_at` are the same archive down to the last byte, so its
    digest identifies the evidence rather than the moment of export, and a
    firm can prove that the copy it kept and the copy it handed over are one
    file. Achieved by pinning every entry's timestamp, permissions, and host
    system, and by writing the entries in sorted order.

    Args:
        case: The engagement. Its client, period, and status head the manifest.
        items: The review queue, decided and pending alike, exactly as
            persisted. Pending items stay in, marked pending: what was *not*
            decided is part of the record a reviewer is owed.
        audit: The case's append-only trail, oldest first, as the caller read it.
        reports: The report history. Their recorded digests are reprinted in
            the manifest so the files under `reports/` can be checked against
            what the system recorded when it made them.
        corrections: Values a human corrected. Both readings are kept.
        sign_offs: Second-person sign-offs, if any.
        documents: `(filename, content)` of every source document. Filenames
            are untrusted client text: they are flattened, stripped of
            characters Windows will not extract, and de-duplicated in the
            order given.
        report_files: `(filename, content)` of the generated report files.
        generated_by: The person accountable for the export, as a user id.
        generated_at: When it was exported. Printed in the manifest and used
            as the timestamp of every entry in the archive.

    Returns:
        The zip archive as bytes. The caller stores it, serves it, and records
        `bundle_exported` in the audit trail.
    """
    date_time = _archive_date_time(generated_at)

    entries: list[tuple[str, bytes]] = [(README_NAME, README_TEXT.encode("utf-8"))]

    taken: set[str] = set()
    for filename, content in documents:
        entries.append((f"{DOCUMENTS_DIR}/{_unique(_safe_name(filename), taken)}", content))
    taken = set()
    for filename, content in report_files:
        entries.append((f"{REPORTS_DIR}/{_unique(_safe_name(filename), taken)}", content))

    entries.append((AUDIT_NAME, _json(_AUDIT_JSON, audit)))
    entries.append((REVIEW_QUEUE_NAME, _json(_ITEMS_JSON, items)))
    entries.append((CORRECTIONS_NAME, _json(_CORRECTIONS_JSON, corrections)))
    entries.append((SIGN_OFFS_NAME, _json(_SIGN_OFFS_JSON, sign_offs)))

    entries.sort(key=lambda entry: entry[0])
    digests = [(path, hashlib.sha256(data).hexdigest()) for path, data in entries]

    manifest = _manifest_text(
        case,
        items,
        audit,
        reports,
        corrections,
        sign_offs,
        document_count=len(documents),
        report_file_count=len(report_files),
        digests=digests,
        generated_by=generated_by,
        generated_at=generated_at,
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, data in entries:
            _write(archive, path, data, date_time)
        # Last, because it describes everything above it.
        _write(archive, MANIFEST_NAME, manifest.encode("utf-8"), date_time)
    return buffer.getvalue()
