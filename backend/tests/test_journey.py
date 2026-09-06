"""One firm's month, end to end, through the public API alone.

The feature tests prove each route on its own. This one walks the product the
way a firm would — add the client, run the period, decide the queue, ask the
assistant, sample, sign the report out, hand a key to an integration — and
checks that the pieces agree with each other: the trail records every step,
the dashboard counts what the queue says, the bundle holds what was produced,
and a revoked key stops working at once. It runs on cached extractions, so
it is hermetic, and it is the smoke test to run before any deploy.
"""

from __future__ import annotations

import io
import json
import zipfile

from tests.test_pipeline import a_ledger, a_pdf


def test_a_firm_runs_one_period_from_client_to_report(client, demo_mode) -> None:
    # -- The firm and its client --------------------------------------------
    assert client.get("/health").json()["status"] == "ok"

    created = client.post(
        "/v1/clients",
        json={"name": "Haroon Textiles", "rules": {"approval_limits": [50_000, 500_000]}},
    )
    assert created.status_code == 201, created.text
    client_id = created.json()["client_id"]

    # -- The period is uploaded and processed in the background --------------
    upload = client.post(
        "/v1/upload?background=true",
        files=[
            ("bank_statement", ("statement.pdf", io.BytesIO(a_pdf()))),
            ("ledger", ("ledger.xlsx", io.BytesIO(a_ledger()))),
            ("invoices", ("invoice.pdf", io.BytesIO(a_pdf("INVOICE")))),
        ],
        data={"client_id": client_id},
    )
    assert upload.status_code == 201, upload.text
    case_id = upload.json()["case_id"]
    job = client.get(f"/v1/jobs/{upload.json()['job_id']}").json()
    assert job["finished"] and job["status"] == "succeeded", job

    period = client.get(f"/v1/clients/{client_id}").json()
    assert case_id in {row["case_id"] for row in period["periods"]}

    # -- The queue is decided, one item at a time -----------------------------
    queue = client.get(f"/v1/review-items?case_id={case_id}").json()
    assert queue["case_status"] == "ready_for_review"
    items = queue["items"]
    assert len(items) == 3
    assert all(item["decision"] == "pending" for item in items)

    approved = client.post(f"/v1/review-items/{items[0]['review_item_id']}/approve", json={"note": "Vouched to the invoice."})
    assert approved.status_code == 200, approved.text
    rejected = client.post(f"/v1/review-items/{items[1]['review_item_id']}/reject", json={"reason": "Bank shows a different amount."})
    assert rejected.status_code == 200, rejected.text
    assert client.post(f"/v1/review-items/{items[0]['review_item_id']}/approve", json={}).status_code == 409

    # -- Something is still owed by the client --------------------------------
    ask = client.post(
        "/v1/evidence-requests",
        json={"case_id": case_id, "title": "Send invoice for the third payment",
              "review_item_id": items[2]["review_item_id"]},
    )
    assert ask.status_code == 201, ask.text
    request_id = ask.json()["request"]["request_id"]
    assert client.post(f"/v1/evidence-requests/{request_id}/respond", json={"response_note": "Attached."}).status_code == 200
    assert client.post(f"/v1/evidence-requests/{request_id}/resolve").status_code == 200
    outstanding = client.get(f"/v1/evidence-requests?case_id={case_id}").json()
    assert outstanding["open_total"] == 0 and outstanding["total"] == 1

    # -- The dashboard counts what the queue says -----------------------------
    dashboard = client.get(f"/v1/dashboard?case_id={case_id}").json()
    assert dashboard["decisions"] == {"pending": 1, "approved": 1, "rejected": 1}
    assert dashboard["total_review_items"] == 3

    # -- The assistant answers from the case, with citations ------------------
    answer = client.post("/v1/assistant/chat", json={"question": "How many items are still pending?", "case_id": case_id})
    assert answer.status_code == 200, answer.text
    body = answer.json()["answer"]
    assert body["grounded"] is True
    assert "1" in body["text"]
    refusal = client.post("/v1/assistant/chat", json={"question": "What is the capital of France?", "case_id": case_id})
    assert refusal.status_code == 200
    assert refusal.json()["answer"]["grounded"] is False

    # -- A sample is drawn and can be reproduced ------------------------------
    draw = client.post("/v1/sampling", json={"case_id": case_id, "method": "random", "size": 2, "seed": 7})
    assert draw.status_code == 200, draw.text
    again = client.post("/v1/sampling", json={"case_id": case_id, "method": "random", "size": 2, "seed": 7})
    assert [i["review_item_id"] for i in draw.json()["items"]] == [i["review_item_id"] for i in again.json()["items"]]
    assert draw.json()["sample_size"] == 2

    # -- The report and the bundle hold what was produced ---------------------
    report = client.post("/v1/reports", json={"case_id": case_id})
    assert report.status_code == 201, report.text
    downloads = report.json()["downloads"]
    pdf = client.get(downloads["pdf"])
    excel = client.get(downloads["excel"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    assert excel.status_code == 200 and excel.content[:2] == b"PK"
    assert report.json()["approved_count"] == 1 and report.json()["rejected_count"] == 1

    bundle = client.get(f"/v1/cases/{case_id}/bundle")
    assert bundle.status_code == 200, bundle.text
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        names = set(archive.namelist())
        assert "MANIFEST.txt" in names and "audit-trail.json" in names
        manifest = archive.read("MANIFEST.txt").decode("utf-8")
        # Every file in the bundle is named in the manifest with its digest.
        for name in names - {"MANIFEST.txt"}:
            assert name in manifest, name
        assert any(name.endswith(".pdf") for name in names)
        trail_in_bundle = json.loads(archive.read("audit-trail.json"))
        assert trail_in_bundle

    # -- Every step is in the trail, in order, and nothing was lost -----------
    trail = client.get(f"/v1/audit-trail?case_id={case_id}").json()
    actions = [record["action"] for record in trail["records"]]
    for expected in (
        "case_created", "document_uploaded", "extraction_completed", "matching_completed",
        "item_approved", "item_rejected", "report_generated",
    ):
        assert expected in actions, expected
    assert actions.index("item_approved") < actions.index("report_generated")
    assert len({record["audit_id"] for record in trail["records"]}) == len(trail["records"])

    # -- Documents are readable, with their pages -----------------------------
    documents = client.get(f"/v1/documents?case_id={case_id}").json()["documents"]
    assert len(documents) == 3
    statement = next(doc for doc in documents if doc["document_type"] == "bank_statement")
    page = client.get(f"/v1/documents/{statement['document_id']}/pages/1")
    assert page.status_code == 200 and page.headers["content-type"].startswith("image/")
    assert client.get(f"/v1/documents/{statement['document_id']}/pages/99").status_code == 404

    # -- The firm's insights see the period ------------------------------------
    insights = client.get("/v1/insights")
    assert insights.status_code == 200, insights.text
    compare = client.get(f"/v1/compare?left={case_id}&right={case_id}")
    assert compare.status_code == 200, compare.text

    # -- An integration gets a key, reads, is refused a write, is revoked -----
    key = client.post("/v1/api-keys", json={"name": "nightly", "scopes": ["read"]})
    assert key.status_code == 201, key.text
    secret = key.json()["api_key"]
    machine = {"X-API-Key": secret}
    assert client.get("/v1/cases", headers=machine).status_code == 200
    denied = client.post(f"/v1/review-items/{items[2]['review_item_id']}/approve", json={}, headers=machine)
    assert denied.status_code == 403 and "write" in denied.json()["detail"]
    assert client.post("/v1/api-keys", json={"name": "x", "scopes": ["read"]}, headers=machine).status_code == 403
    assert client.delete(f"/v1/api-keys/{key.json()['key']['key_id']}").status_code == 200
    assert client.get("/v1/cases", headers=machine).status_code == 401

    # -- The period can be renamed, and finally removed ------------------------
    renamed = client.patch(f"/v1/cases/{case_id}", json={"period_start": "2026-06-01", "period_end": "2026-06-30"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["period_end"] == "2026-06-30"
    assert client.delete(f"/v1/cases/{case_id}").status_code == 200
    assert client.get(f"/v1/review-items?case_id={case_id}").status_code == 404
