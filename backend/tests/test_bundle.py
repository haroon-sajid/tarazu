"""The evidence bundle: what is in the archive, and that it can be trusted.

A bundle is only worth handing to a regulator if two things hold: every file
it claims to contain is there, and the manifest's digests are the digests of
those exact bytes. Both are asserted here by recomputing the hashes rather
than by trusting the manifest's own arithmetic.

The third property is reproducibility. `test_reports.py` proves the workbook
is byte-identical across renderings; the same has to be true of the bundle,
or the digest of an export would describe the second it happened in rather
than the evidence inside it. Two builds from identical inputs are compared
byte for byte here for that reason.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from datetime import date, datetime, timezone

from pydantic import TypeAdapter

from app.modules.reports.bundle import build_bundle
from app.shared.schemas import (
    ActorType,
    AuditAction,
    AuditRecord,
    CaseRecord,
    CaseStatus,
    ReportRecord,
    ReviewDecision,
    ReviewItem,
    SignOff,
    ValueCorrection,
)
from tests.conftest import DEMO_USER, load_sample_queue

EXPORTED_AT = datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)

#: Lines of the manifest that state a digest: "<64 hex>  <path>", sha256sum's
#: own format, so `sha256sum -c MANIFEST.txt` works on the extracted folder.
DIGEST_LINE = re.compile(r"^([0-9a-f]{64})  (.+)$")


def a_case() -> CaseRecord:
    return CaseRecord(
        case_id="CASE-2026-06-STX",
        client_name="Haroon Textiles",
        period_start=date(2026, 6, 2),
        period_end=date(2026, 6, 18),
        status=CaseStatus.READY_FOR_REVIEW,
        created_by=DEMO_USER.user_id,
        created_at=datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc),
    )


def an_audit_trail(case_id: str) -> list[AuditRecord]:
    return [
        AuditRecord(
            audit_id="AUD-0001",
            case_id=case_id,
            actor_type=ActorType.SYSTEM,
            actor_id="pipeline",
            action=AuditAction.CASE_CREATED,
            occurred_at=datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc),
        ),
        AuditRecord(
            audit_id="AUD-0002",
            case_id=case_id,
            actor_type=ActorType.HUMAN,
            actor_id=DEMO_USER.user_id,
            action=AuditAction.ITEM_APPROVED,
            item_id="RI-0001",
            detail="matched to bank line BNK-0001",
            occurred_at=datetime(2026, 6, 21, 14, 30, tzinfo=timezone.utc),
        ),
    ]


def a_report_record(case_id: str) -> ReportRecord:
    return ReportRecord(
        report_id="RPT-test000001",
        case_id=case_id,
        generated_by=DEMO_USER.user_id,
        generated_at=EXPORTED_AT,
        pdf_path=f"{case_id}/reports/RPT-test000001/tarazu-report.pdf",
        excel_path=f"{case_id}/reports/RPT-test000001/tarazu-report.xlsx",
        pdf_sha256="a" * 64,
        excel_sha256="b" * 64,
        item_count=10,
        approved_count=1,
        rejected_count=1,
        pending_count=8,
        flag_count=4,
        audit_record_count=2,
    )


def a_correction(case_id: str) -> ValueCorrection:
    return ValueCorrection(
        correction_id="COR-0001",
        case_id=case_id,
        review_item_id="RI-0004",
        document_id="DOC-BNK-001",
        field="amount",
        ai_value="49500.00",
        corrected_value="49900.00",
        note="The statement reads 49,900; the model transposed a digit.",
        corrected_by=DEMO_USER.user_id,
        corrected_at=datetime(2026, 6, 22, 11, 0, tzinfo=timezone.utc),
    )


def a_sign_off(case_id: str) -> SignOff:
    return SignOff(
        sign_off_id="SGN-0001",
        case_id=case_id,
        signed_by="00000000-0000-4000-8000-000000000002",
        signed_at=datetime(2026, 6, 23, 8, 0, tzinfo=timezone.utc),
        note="Reviewed the two rejections against the statement.",
        item_count=10,
        approved_count=9,
        rejected_count=1,
    )


DOCUMENTS = [
    ("bank-statement.pdf", b"%PDF-1.4 bank statement bytes"),
    ("invoices.pdf", b"%PDF-1.4 invoice bytes"),
    ("ledger.xlsx", b"PK\x03\x04 ledger bytes"),
]
REPORT_FILES = [
    ("tarazu-report.pdf", b"%PDF-1.4 report bytes"),
    ("tarazu-report.xlsx", b"PK\x03\x04 workbook bytes"),
]


def a_bundle(
    *,
    items: list[ReviewItem] | None = None,
    corrections: list[ValueCorrection] | None = None,
    sign_offs: list[SignOff] | None = None,
    documents: list[tuple[str, bytes]] | None = None,
    exported_at: datetime = EXPORTED_AT,
) -> bytes:
    case = a_case()
    return build_bundle(
        case,
        load_sample_queue().items if items is None else items,
        an_audit_trail(case.case_id),
        [a_report_record(case.case_id)],
        [] if corrections is None else corrections,
        [] if sign_offs is None else sign_offs,
        DOCUMENTS if documents is None else documents,
        REPORT_FILES,
        generated_by=DEMO_USER.user_id,
        generated_at=exported_at,
    )


def opened(bundle: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(bundle))


# --------------------------------------------------------------------------- #
# What is in the archive
# --------------------------------------------------------------------------- #


def test_the_archive_holds_exactly_the_expected_entries() -> None:
    with opened(a_bundle()) as archive:
        assert set(archive.namelist()) == {
            "README.txt",
            "MANIFEST.txt",
            "audit-trail.json",
            "review-queue.json",
            "corrections.json",
            "sign-offs.json",
            "documents/bank-statement.pdf",
            "documents/invoices.pdf",
            "documents/ledger.xlsx",
            "reports/tarazu-report.pdf",
            "reports/tarazu-report.xlsx",
        }


def test_the_source_documents_and_reports_are_carried_unmodified() -> None:
    with opened(a_bundle()) as archive:
        for filename, content in DOCUMENTS:
            assert archive.read(f"documents/{filename}") == content
        for filename, content in REPORT_FILES:
            assert archive.read(f"reports/{filename}") == content


def test_the_manifest_states_the_engagement_and_the_counts() -> None:
    with opened(a_bundle(corrections=[a_correction("CASE-2026-06-STX")])) as archive:
        manifest = archive.read("MANIFEST.txt").decode("utf-8")
    assert "Haroon Textiles" in manifest
    assert "CASE-2026-06-STX" in manifest
    assert "2026-06-02 to 2026-06-18" in manifest
    assert "Exported at" in manifest and "2026-08-29 10:00 UTC" in manifest
    assert DEMO_USER.user_id in manifest
    assert "Review items        10 (1 approved, 1 rejected, 8 pending)" in manifest
    assert "Audit records       2" in manifest
    assert "Corrections         1" in manifest


def test_the_manifest_reprints_the_digests_recorded_when_the_report_was_made() -> None:
    """So the file in `reports/` can be checked against the system's own record."""
    with opened(a_bundle()) as archive:
        manifest = archive.read("MANIFEST.txt").decode("utf-8")
    assert f"pdf    sha256={'a' * 64}" in manifest
    assert f"excel  sha256={'b' * 64}" in manifest
    assert "RPT-test000001" in manifest


def test_the_readme_explains_how_to_verify_the_bundle() -> None:
    with opened(a_bundle()) as archive:
        readme = archive.read("README.txt").decode("utf-8")
    assert "sha256sum -c MANIFEST.txt" in readme
    assert "certutil -hashfile" in readme
    assert "Get-FileHash" in readme
    assert "The AI assists, the human decides." in readme


# --------------------------------------------------------------------------- #
# The manifest is true
# --------------------------------------------------------------------------- #


def listed_digests(archive: zipfile.ZipFile) -> dict[str, str]:
    manifest = archive.read("MANIFEST.txt").decode("utf-8")
    return {
        match.group(2): match.group(1)
        for match in (DIGEST_LINE.match(line) for line in manifest.splitlines())
        if match
    }


def test_the_manifest_carries_a_correct_digest_for_every_other_file() -> None:
    with opened(a_bundle()) as archive:
        listed = listed_digests(archive)
        recomputed = {
            name: hashlib.sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
            if name != "MANIFEST.txt"
        }
    assert listed == recomputed


def test_the_manifest_does_not_hash_itself_and_says_why() -> None:
    """A file cannot state its own digest; the bundle admits it rather than lying."""
    with opened(a_bundle()) as archive:
        manifest = archive.read("MANIFEST.txt").decode("utf-8")
        assert "MANIFEST.txt" not in listed_digests(archive)
    assert "cannot" in manifest and "state its own digest" in manifest


def test_the_digest_lines_are_sorted_by_path() -> None:
    """`sha256sum -c` reads them in order, and so does a person."""
    with opened(a_bundle()) as archive:
        paths = list(listed_digests(archive))
    assert paths == sorted(paths)


def test_tampering_with_a_file_breaks_its_manifest_line() -> None:
    """The property the whole artefact rests on, stated as a test."""
    with opened(a_bundle()) as archive:
        listed = listed_digests(archive)
        original = archive.read("documents/ledger.xlsx")
    assert listed["documents/ledger.xlsx"] == hashlib.sha256(original).hexdigest()
    assert listed["documents/ledger.xlsx"] != hashlib.sha256(original + b" ").hexdigest()


# --------------------------------------------------------------------------- #
# Byte-reproducibility
# --------------------------------------------------------------------------- #


def test_two_bundles_from_the_same_inputs_are_the_same_bytes() -> None:
    assert a_bundle() == a_bundle()


def test_the_entry_timestamps_come_from_the_export_not_the_wall_clock() -> None:
    """Zip stamps each entry as it writes; left alone that alone would break it."""
    with opened(a_bundle()) as archive:
        stamps = {entry.date_time for entry in archive.infolist()}
    assert stamps == {(2026, 8, 29, 10, 0, 0)}


def test_a_later_export_of_the_same_case_differs_only_in_its_stamp() -> None:
    """The digest identifies an export, so a different export time is a different file."""
    assert a_bundle() != a_bundle(exported_at=EXPORTED_AT.replace(hour=11))


# --------------------------------------------------------------------------- #
# The shape does not depend on the case
# --------------------------------------------------------------------------- #


def test_an_empty_corrections_and_sign_offs_still_produce_their_files() -> None:
    """A missing file would leave a reviewer unable to tell "none" from "not exported"."""
    with opened(a_bundle()) as archive:
        assert json.loads(archive.read("corrections.json")) == []
        assert json.loads(archive.read("sign-offs.json")) == []


def test_corrections_and_sign_offs_round_trip_when_the_case_has_them() -> None:
    case_id = "CASE-2026-06-STX"
    bundle = a_bundle(corrections=[a_correction(case_id)], sign_offs=[a_sign_off(case_id)])
    with opened(bundle) as archive:
        corrections = TypeAdapter(list[ValueCorrection]).validate_json(
            archive.read("corrections.json")
        )
        sign_offs = TypeAdapter(list[SignOff]).validate_json(archive.read("sign-offs.json"))
    # Both readings survive: the point of a correction is the disagreement.
    assert corrections[0].ai_value == "49500.00"
    assert corrections[0].corrected_value == "49900.00"
    assert sign_offs[0].signed_by != DEMO_USER.user_id  # four eyes, not two


# --------------------------------------------------------------------------- #
# The records round-trip
# --------------------------------------------------------------------------- #


def test_the_audit_trail_round_trips_oldest_first() -> None:
    with opened(a_bundle()) as archive:
        trail = TypeAdapter(list[AuditRecord]).validate_json(archive.read("audit-trail.json"))
    assert [record.audit_id for record in trail] == ["AUD-0001", "AUD-0002"]
    approval = trail[1]
    assert approval.action is AuditAction.ITEM_APPROVED
    assert approval.actor_type is ActorType.HUMAN
    assert approval.actor_id == DEMO_USER.user_id
    assert approval.item_id == "RI-0001"
    assert approval.occurred_at == datetime(2026, 6, 21, 14, 30, tzinfo=timezone.utc)


def test_the_review_queue_round_trips_with_its_decisions_and_amounts() -> None:
    queue = load_sample_queue().items
    with opened(a_bundle()) as archive:
        restored = TypeAdapter(list[ReviewItem]).validate_json(archive.read("review-queue.json"))
    assert restored == queue

    approved = next(item for item in restored if item.decision is ReviewDecision.APPROVED)
    assert approved.decided_by and approved.decided_at  # rule 1: a human, and when
    rejected = next(item for item in restored if item.decision is ReviewDecision.REJECTED)
    assert rejected.rejection_reason
    # Pending items stay in the bundle: what was not decided is part of the record.
    assert sum(1 for item in restored if item.decision is ReviewDecision.PENDING) == 8


def test_amounts_survive_as_exact_decimals() -> None:
    """Serialised through JSON, an amount must not become a float.

    A float would round, and a rounded figure in an evidence bundle is a
    different figure. Pydantic writes a `Decimal` as its digits, in quotes.
    """
    queue = load_sample_queue().items
    with opened(a_bundle()) as archive:
        raw = json.loads(archive.read("review-queue.json"))
    amounts = [item["ledger_entry"]["amount"] for item in raw]
    assert all(isinstance(amount, str) for amount in amounts)
    assert amounts == [str(item.ledger_entry.amount) for item in queue]


# --------------------------------------------------------------------------- #
# Untrusted filenames
# --------------------------------------------------------------------------- #


def test_colliding_document_filenames_are_disambiguated_deterministically() -> None:
    documents = [
        ("scan.pdf", b"first"),
        ("scan.pdf", b"second"),
        ("archive/scan.pdf", b"third"),
        ("SCAN.PDF", b"fourth"),
        ("notes", b"extensionless"),
        ("notes", b"extensionless again"),
    ]
    bundle = a_bundle(documents=documents)
    with opened(bundle) as archive:
        names = [name for name in archive.namelist() if name.startswith("documents/")]
        assert sorted(names) == sorted(
            [
                "documents/scan.pdf",
                "documents/scan-2.pdf",
                "documents/scan-3.pdf",
                "documents/SCAN-4.PDF",
                "documents/notes",
                "documents/notes-2",
            ]
        )
        # Nothing was dropped or swapped, and the naming follows the input order.
        assert archive.read("documents/scan.pdf") == b"first"
        assert archive.read("documents/scan-2.pdf") == b"second"
        assert archive.read("documents/scan-3.pdf") == b"third"
        # Casing collides on Windows, so it counts as a collision here too.
        assert archive.read("documents/SCAN-4.PDF") == b"fourth"
    assert bundle == a_bundle(documents=documents)


def test_a_client_filename_cannot_place_a_file_outside_the_folder() -> None:
    """Uploaded names are untrusted text, and an unextractable bundle is no evidence."""
    bundle = a_bundle(documents=[("../../etc/passwd", b"x"), ('we:ird?.pdf', b"y")])
    with opened(bundle) as archive:
        names = [name for name in archive.namelist() if name.startswith("documents/")]
    assert sorted(names) == ["documents/passwd", "documents/weird.pdf"]
