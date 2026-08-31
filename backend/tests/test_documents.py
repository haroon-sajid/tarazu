"""Documents: the list, the original bytes, and pages rendered for the viewer."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

from app.core.config import DEFAULT_ORG_ID as ORG
from app.core.sqlite_store import SqliteCaseRepository
from tests.test_pipeline import a_ledger, a_pdf


def upload(client: TestClient) -> dict:
    two_pages = _two_page_pdf()
    response = client.post(
        "/v1/upload",
        files=[
            ("bank_statement", ("statement.pdf", io.BytesIO(two_pages))),
            ("ledger", ("ledger.xlsx", io.BytesIO(a_ledger()))),
            ("invoices", ("invoice.pdf", io.BytesIO(a_pdf("INVOICE")))),
        ],
    )
    assert response.status_code == 201
    return response.json()


def _two_page_pdf() -> bytes:
    import pymupdf

    document = pymupdf.open()
    for text in ("STATEMENT PAGE ONE", "STATEMENT PAGE TWO"):
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 120), text, fontsize=16)
    data = document.tobytes()
    document.close()
    return data


def test_the_case_lists_its_documents_with_page_counts(client: TestClient, demo_mode) -> None:
    case_id = upload(client)["case_id"]
    listed = client.get("/v1/documents", params={"case_id": case_id}).json()
    assert listed["case_id"] == case_id
    assert listed["total"] == 3
    by_type = {doc["document_type"]: doc for doc in listed["documents"]}

    ledger = by_type["ledger"]
    assert ledger["page_count"] is None
    assert ledger["page_url_template"] is None
    assert ledger["file_url"].endswith("/file")

    statement = by_type["bank_statement"]
    # DEMO_MODE replays the cached extraction, which reports one page; the
    # template still names the right document and the right shape.
    assert statement["page_url_template"] == f"/v1/documents/{statement['document_id']}/pages/{{page}}"
    assert statement["page_count"] >= 1


def test_the_original_file_downloads_with_its_type(client: TestClient, demo_mode) -> None:
    uploaded = upload(client)
    ledger = next(doc for doc in uploaded["documents"] if doc["document_type"] == "ledger")
    response = client.get(f"/v1/documents/{ledger['document_id']}/file")
    assert response.status_code == 200
    assert response.content[:2] == b"PK"
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert 'filename="ledger.xlsx"' in response.headers["content-disposition"]


def test_a_pdf_page_renders_as_a_png(client: TestClient, demo_mode) -> None:
    uploaded = upload(client)
    statement = next(doc for doc in uploaded["documents"] if doc["document_type"] == "bank_statement")
    page = client.get(f"/v1/documents/{statement['document_id']}/pages/2")
    assert page.status_code == 200
    assert page.headers["content-type"] == "image/png"
    assert page.content.startswith(b"\x89PNG")
    assert client.get(f"/v1/documents/{statement['document_id']}/pages/3").status_code == 404
    assert client.get(f"/v1/documents/{statement['document_id']}/pages/0").status_code == 404


def test_the_ledger_has_no_pages(client: TestClient, demo_mode) -> None:
    uploaded = upload(client)
    ledger = next(doc for doc in uploaded["documents"] if doc["document_type"] == "ledger")
    response = client.get(f"/v1/documents/{ledger['document_id']}/pages/1")
    assert response.status_code == 404
    assert "spreadsheet" in response.json()["detail"]


def test_a_photographed_invoice_is_served_as_itself(client: TestClient, demo_mode) -> None:
    import pymupdf

    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 60), False)
    pixmap.clear_with(255)
    photo = pixmap.tobytes("png")
    response = client.post(
        "/v1/upload",
        files=[
            ("bank_statement", ("statement.pdf", io.BytesIO(a_pdf()))),
            ("ledger", ("ledger.xlsx", io.BytesIO(a_ledger()))),
            ("invoices", ("invoice.png", io.BytesIO(photo))),
        ],
    )
    invoice = next(doc for doc in response.json()["documents"] if doc["document_type"] == "invoice")
    page = client.get(f"/v1/documents/{invoice['document_id']}/pages/1")
    assert page.status_code == 200
    assert page.headers["content-type"] == "image/png"
    assert page.content == photo
    assert client.get(f"/v1/documents/{invoice['document_id']}/pages/2").status_code == 404


def test_another_firms_documents_do_not_exist(
    client: TestClient, other_client: TestClient, demo_mode
) -> None:
    uploaded = upload(client)
    document_id = uploaded["documents"][0]["document_id"]
    assert other_client.get(f"/v1/documents/{document_id}/file").status_code == 404
    assert other_client.get(f"/v1/documents/{document_id}/pages/1").status_code == 404
    assert other_client.get("/v1/documents", params={"case_id": uploaded["case_id"]}).status_code == 404


def test_the_repository_lookup_is_org_scoped(
    client: TestClient, repository: SqliteCaseRepository, demo_mode
) -> None:
    uploaded = upload(client)
    document_id = uploaded["documents"][0]["document_id"]
    found = repository.get_document(ORG, document_id)
    assert found is not None and found.case_id == uploaded["case_id"]
    assert repository.get_document("11111111-1111-4111-8111-111111111111", document_id) is None
