"""Background jobs: run the pipeline off the request thread.

Extraction over a real bank statement takes tens of seconds. A browser request
should not, so `POST /v1/upload?background=true` creates the case, queues the
work here, and answers immediately with a `job_id` the upload screen polls.

**A job is working state, never evidence.** The row this writes says how far
the work has got so a screen can show a bar; what actually happened is in the
append-only audit trail, written by the pipeline exactly as it is when the same
code runs inside a request. Losing every job row would cost the progress bar
and nothing else.

The executor is deliberately small and in-process. This is a modular monolith
serving one firm's uploads at a time, not a queue: a real broker (Celery, RQ,
Supabase queues) is a deployment decision, and when it arrives it replaces the
three lines in `submit` without anything above this file changing — the route
already hands over a callable and gets a job id back.
"""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Protocol

from app.core.repository import CaseRepository
from app.shared.schemas import JobRecord, JobStatus

__all__ = ["Progress", "install_executor", "run_inline_by_default", "submit"]

logger = logging.getLogger(__name__)


class Progress(Protocol):
    """What a job's work is handed so it can say where it has got to."""

    def __call__(self, percent: int, step: str) -> None: ...


#: One small pool for the whole process. Two workers because the work is
#: network-bound on the model API rather than CPU-bound, and because a local
#: SQLite store serialises its writes behind one lock anyway.
_MAX_WORKERS = max(1, int(os.getenv("TARAZU_JOB_WORKERS") or 2))

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _pool() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=_MAX_WORKERS, thread_name_prefix="tarazu-job"
            )
        return _executor


def install_executor(executor: ThreadPoolExecutor | None) -> None:
    """Replace the pool. For tests that want to control when work runs."""
    global _executor
    with _executor_lock:
        _executor = executor


def run_inline_by_default() -> bool:
    """Whether jobs run on the calling thread instead of in the pool.

    On by default in the test suite (`TARAZU_JOBS_INLINE=1`), so a job's effects
    are visible the moment the request returns and nothing has to be polled or
    slept on. Never on in a deployment: that is what the pool is for.
    """
    return (os.getenv("TARAZU_JOBS_INLINE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def submit(
    repository: CaseRepository,
    org_id: str,
    job: JobRecord,
    work: Callable[[Progress], None],
    *,
    inline: bool | None = None,
) -> Future | None:
    """Persist `job` as queued and run `work` with a progress reporter.

    `work` is handed one argument: a `progress(percent, step)` callable it may
    call as often as it likes. Every call updates the job row and nothing else
    — a job that never reports progress still succeeds, and a progress write
    that fails never fails the work.

    Returns the `Future` when the work was handed to the pool, or None when it
    ran inline. Exceptions inside `work` are caught, recorded on the job as
    `failed` with the reason, and logged: a background failure must not be able
    to take the process down, and the case it belongs to has already been
    marked `failed` by the pipeline itself.
    """
    repository.create_job(org_id, job)
    inline = run_inline_by_default() if inline is None else inline

    def _progress(percent: int, step: str) -> None:
        try:
            current = repository.get_job(org_id, job.job_id)
            if current is None or current.status.is_terminal:
                return
            repository.update_job(
                org_id,
                current.model_copy(
                    update={
                        "status": JobStatus.RUNNING,
                        "progress": max(0, min(100, int(percent))),
                        "step": step or current.step,
                        "started_at": current.started_at or _now(),
                    }
                ),
            )
        except Exception:  # noqa: BLE001 - progress is decoration, never the work
            logger.warning("Could not record progress for job %s", job.job_id, exc_info=True)

    def _run() -> None:
        started = _now()
        try:
            repository.update_job(
                org_id,
                job.model_copy(
                    update={
                        "status": JobStatus.RUNNING,
                        "step": "Starting",
                        "started_at": started,
                    }
                ),
            )
            work(_progress)
        except Exception as error:  # noqa: BLE001 - recorded on the job, not raised
            detail = f"{type(error).__name__}: {error}"
            logger.exception("Job %s failed: %s", job.job_id, detail)
            _finish(repository, org_id, job.job_id, JobStatus.FAILED, detail)
            return
        _finish(repository, org_id, job.job_id, JobStatus.SUCCEEDED, None)

    if inline:
        _run()
        return None
    return _pool().submit(_run)


def _finish(
    repository: CaseRepository,
    org_id: str,
    job_id: str,
    status: JobStatus,
    error: str | None,
) -> None:
    """Stamp a job's ending. Best-effort: the work itself is already done."""
    try:
        current = repository.get_job(org_id, job_id)
        if current is None:
            return
        repository.update_job(
            org_id,
            current.model_copy(
                update={
                    "status": status,
                    "progress": 100 if status is JobStatus.SUCCEEDED else current.progress,
                    "step": "Done" if status is JobStatus.SUCCEEDED else "Failed",
                    "finished_at": _now(),
                    "error": error,
                }
            ),
        )
    except Exception:  # noqa: BLE001 - never raise out of a finished job
        logger.warning("Could not record the end of job %s", job_id, exc_info=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)
