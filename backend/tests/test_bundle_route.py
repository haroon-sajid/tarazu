"""`GET /v1/cases/{case_id}/bundle` — the engagement as one verifiable zip.

`test_bundle.py` proves the archive itself. What is pinned here is the route:
that it gathers the right things from the right organization, that a file
missing from storage degrades the bundle instead of losing it, and that
exporting is recorded — a bundle handed to a regulator should be traceable to
whoever took it out of the building.
"""

from __future__ import annotations

import hashlib
import io
import zipfile

from app.core.sqlite_store import SqliteCaseRepository
from app.shared.schemas import AuditAction

DEMO_ORG = "00000000-0000-4000-8000-0000000000d0"


def _bundle(client, case_id: str) -> zipfile.ZipFile:
    response = client.get(f"/v1/cases/{case_id}/bundle")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "evidence-bundle.zip" in response.headers["content-disposition"]
    return zipfile.ZipFile(io.BytesIO(response.content))


def test_the_bundle_carries_the_whole_engagement(client, seeded_case: str) -> None:
    archive = _bundle(client, seeded_case)
    names = set(archive.namelist())

    assert {
        "README.txt",
        "MANIFEST.txt",
        "audit-trail.json",
        "review-queue.json",
        "corrections.json",
        "sign-offs.json",
    } <= names


def test_every_file_in_the_manifest_hashes_correctly(client, seeded_case: str) -> None:
    """The point of the bundle: each file can be shown to be the file that was made."""
    archive = _bundle(client, seeded_case)
    manifest = archive.read("MANIFEST.txt").decode("utf-8")

    listed = {}
    for line in manifest.splitlines():
        # Digest lines are "<64 hex>  <path>"; the header lines are indented
        # or prose, so a strict split on exactly two spaces finds only these.
        parts = line.split("  ")
        if len(parts) == 2 and len(parts[0]) == 64 and not line.startswith(" "):
            listed[parts[1].strip()] = parts[0]

    assert listed, "the manifest must list digests"
    assert "MANIFEST.txt" not in listed, "the manifest does not hash itself"

    for path, digest in listed.items():
        assert hashlib.sha256(archive.read(path)).hexdigest() == digest, path


def test_a_generated_report_is_carried_in_the_bundle(client, seeded_case: str) -> None:
    created = client.post("/v1/reports", json={"case_id": seeded_case})
    assert created.status_code == 201, created.text

    archive = _bundle(client, seeded_case)
    reports = [name for name in archive.namelist() if name.startswith("reports/")]
    assert len(reports) == 2, "the PDF and the workbook both travel with the bundle"
    assert any(name.endswith(".pdf") for name in reports)
    assert any(name.endswith(".xlsx") for name in reports)


def test_exporting_is_recorded_in_the_trail(
    client, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    client.get(f"/v1/cases/{seeded_case}/bundle")

    exported = [
        record
        for record in repository.list_audit(DEMO_ORG, seeded_case)
        if record.action is AuditAction.BUNDLE_EXPORTED
    ]
    assert exported, "taking the evidence out of the building is an act worth recording"
    assert "sha256" in exported[0].detail


def test_a_missing_file_degrades_the_bundle_rather_than_losing_it(
    client, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    """A bundle complete except one unreadable document beats no bundle at all."""
    from app.core.repository import StoredDocument
    from app.shared.schemas import DocumentType

    repository.add_documents(
        DEMO_ORG,
        seeded_case,
        [
            StoredDocument(
                document_id="DOC-BNK-gone",
                document_type=DocumentType.BANK_STATEMENT,
                filename="never-stored.pdf",
                size_bytes=10,
                storage_path=f"{seeded_case}/DOC-BNK-gone/never-stored.pdf",
            )
        ],
        "tester",
    )

    archive = _bundle(client, seeded_case)
    assert "documents/never-stored.pdf" not in archive.namelist()
    assert "MANIFEST.txt" in archive.namelist()


def test_another_firms_bundle_is_a_404(client, other_client, seeded_case: str) -> None:
    assert other_client.get(f"/v1/cases/{seeded_case}/bundle").status_code == 404


def test_an_unknown_case_is_a_404(client, demo_org: str) -> None:
    assert client.get("/v1/cases/CASE-nope/bundle").status_code == 404
