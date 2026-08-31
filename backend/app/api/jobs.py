"""`/v1/jobs` — how far a queued upload has got.

Read-only. A job row says what stage the pipeline is at so the upload screen
can show something truthful instead of a spinner; every result it produces is
read from the case, the review queue, and the audit trail exactly as when the
pipeline runs inside the request. Nothing is ever decided here.

Scoped like every other route: another firm's job is a `404`, indistinguishable
from one that never existed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import Principal, get_repository, require_read
from app.core.repository import CaseRepository
from app.shared.api import JobListResponse, JobResponse, JobSummary
from app.shared.schemas import JobStatus

__all__ = ["router"]

router = APIRouter(tags=["jobs"])


@router.get(
    "/jobs",
    response_model=JobListResponse,
    summary="Recent background jobs, newest first",
)
async def list_jobs(
    job_status: JobStatus | None = Query(
        default=None, alias="status", description="Filter by job status"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> JobListResponse:
    records = repository.list_jobs(principal.org_id, job_status, limit)
    return JobListResponse(
        total=len(records), jobs=[JobSummary.of(record) for record in records]
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="One job's progress — what the upload screen polls",
)
async def get_job(
    job_id: str,
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> JobResponse:
    """Poll until `finished` is true, then read the case as usual.

    A finished job is not itself the result: `status` says whether the work
    succeeded, and the review queue, dashboard, and trail say what it produced.
    """
    record = repository.get_job(principal.org_id, job_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No job with id {job_id!r}."
        )
    return JobResponse(**JobSummary.of(record).model_dump())
