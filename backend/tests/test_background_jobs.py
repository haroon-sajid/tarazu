"""Background processing: `POST /v1/upload?background=true` and `/v1/jobs`.

The pipeline is the same code either way — same steps, same order, same audit
trail. What these tests pin down is that queueing it changes only *when* the
work happens: the case exists immediately, the job reports where the work got
to, and the review queue at the end is the one the synchronous path produces.

Jobs run inline here (`TARAZU_JOBS_INLINE=1`, set in `conftest.py`), so a job's
effects are visible the moment the request returns and nothing has to be polled
or slept on. That is a test-harness choice, not a different code path: the same
`jobs.submit` runs the same work function, on this thread instead of a pooled
one.
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

from app.core.sqlite_store import SqliteCaseRepository
from app.shared.schemas import CaseStatus, JobStatus
from tests.test_pipeline import a_ledger, a_pdf


def _upload(client: TestClient, *, background: bool) -> dict:
    response = client.post(
        f"/v1/upload?background={'true' if background else 'false'}",
        files=[
            ("bank_statement", ("statement.pdf", io.BytesIO(a_pdf()))),
            ("ledger", ("ledger.xlsx", io.BytesIO(a_ledger()))),
            ("invoices", ("invoice.pdf", io.BytesIO(a_pdf("INVOICE")))),
        ],
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_a_queued_upload_returns_a_job_to_poll(client, demo_mode) -> None:
    body = _upload(client, background=True)

    assert body["job_id"], "a queued upload must say what to poll"
    assert body["case_id"]

    job = client.get(f"/v1/jobs/{body['job_id']}")
    assert job.status_code == 200
    assert job.json()["case_id"] == body["case_id"]
    assert job.json()["finished"] is True  # inline in the suite
    assert job.json()["status"] == JobStatus.SUCCEEDED.value
    assert job.json()["progress"] == 100


def test_the_case_exists_before_the_work_finishes(
    client, repository: SqliteCaseRepository, demo_mode
) -> None:
    """The upload screen navigates to the case as soon as the POST returns.

    The case row is therefore written on the request thread, not by the worker
    — otherwise the screen would 404 in the gap before a worker picked the job
    up. Here the job has already run, so what this really pins is that the row
    exists and belongs to the case the response named.
    """
    body = _upload(client, background=True)
    case = client.get(f"/v1/review-items?case_id={body['case_id']}")
    assert case.status_code == 200


def test_queued_and_synchronous_uploads_produce_the_same_queue(
    client, demo_mode
) -> None:
    """The only difference is which thread runs it."""
    queued = _upload(client, background=True)
    direct = _upload(client, background=False)

    queued_items = client.get(f"/v1/review-items?case_id={queued['case_id']}").json()
    direct_items = client.get(f"/v1/review-items?case_id={direct['case_id']}").json()

    assert queued_items["total"] == direct_items["total"] == 3
    assert [item["match"]["status"] for item in queued_items["items"]] == [
        item["match"]["status"] for item in direct_items["items"]
    ]


def test_a_synchronous_upload_carries_no_job(client, demo_mode) -> None:
    body = _upload(client, background=False)
    assert body["job_id"] is None
    assert body["status"] == CaseStatus.READY_FOR_REVIEW.value
    assert body["review_item_count"] == 3


def test_the_job_list_is_newest_first_and_filterable(client, demo_mode) -> None:
    first = _upload(client, background=True)
    second = _upload(client, background=True)

    listing = client.get("/v1/jobs").json()
    assert listing["total"] == 2
    assert [job["case_id"] for job in listing["jobs"]] == [
        second["case_id"],
        first["case_id"],
    ]

    succeeded = client.get("/v1/jobs?status=succeeded").json()
    assert succeeded["total"] == 2
    assert client.get("/v1/jobs?status=failed").json()["total"] == 0


def test_a_failed_job_records_why(
    client, repository: SqliteCaseRepository, demo_mode, monkeypatch
) -> None:
    """A background failure is recorded on the job, not swallowed or crashed.

    The case is marked `failed` by the pipeline exactly as in the synchronous
    path; the job carries the same reason so the upload screen can show it
    without having to re-read the case.
    """
    from app.modules import matching

    def explode(*_args, **_kwargs):
        raise RuntimeError("matching blew up")

    monkeypatch.setattr(matching.service, "run_matching", explode)

    body = _upload(client, background=True)
    job = client.get(f"/v1/jobs/{body['job_id']}").json()

    assert job["status"] == JobStatus.FAILED.value
    assert "matching blew up" in job["error"]
    assert repository.get_case(
        "00000000-0000-4000-8000-0000000000d0", body["case_id"]
    ).status is CaseStatus.FAILED


def test_another_firms_job_is_a_404(client, other_client, demo_mode) -> None:
    body = _upload(client, background=True)

    assert other_client.get(f"/v1/jobs/{body['job_id']}").status_code == 404
    assert other_client.get("/v1/jobs").json()["total"] == 0


def test_jobs_require_an_identity(anonymous_client) -> None:
    assert anonymous_client.get("/v1/jobs").status_code in (401, 403)
