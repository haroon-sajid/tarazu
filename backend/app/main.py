"""Tarazu — AI Audit Assistant: FastAPI application entry point.

Wiring only: create the app, attach middleware, include the routers. No business
logic belongs in this file, and none of it imports a module's internals.

Run it with::

    uvicorn app.main:app --reload --app-dir backend

The public surface is documented in
[docs/api-contracts.md](../../docs/api-contracts.md).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import (
    api_keys,
    assistant,
    audit_trail,
    auth,
    business,
    cases,
    clients,
    dashboard,
    documents,
    evidence_requests,
    health,
    insights,
    jobs,
    members,
    org_profile,
    profile,
    reports,
    review,
    sampling,
    sign_offs,
    upload,
)
from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Say out loud how this process is configured. Secrets are never logged."""
    logger.info(
        "Tarazu %s starting. Persistence: %s. Extraction: %s.",
        __version__,
        "Supabase" if settings.uses_supabase else "local SQLite",
        "DEMO_MODE (cached)" if settings.demo_mode else "live Qwen VL",
    )
    if settings.allow_dev_user:
        logger.warning(
            "AUTH_ALLOW_DEV_USER is on: unauthenticated requests are served as the "
            "development user. This must be off in any deployed environment."
        )
    yield


app = FastAPI(
    title="Tarazu — AI Audit Assistant",
    version=__version__,
    summary="The AI suggests, the human decides. All math is deterministic code.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router, prefix="/v1")
app.include_router(profile.router, prefix="/v1")
app.include_router(members.router, prefix="/v1")
app.include_router(api_keys.router, prefix="/v1")
app.include_router(upload.router, prefix="/v1")
app.include_router(review.router, prefix="/v1")
app.include_router(dashboard.router, prefix="/v1")
app.include_router(cases.router, prefix="/v1")
app.include_router(audit_trail.router, prefix="/v1")
app.include_router(documents.router, prefix="/v1")
app.include_router(reports.router, prefix="/v1")
app.include_router(assistant.router, prefix="/v1")
app.include_router(clients.router, prefix="/v1")
app.include_router(jobs.router, prefix="/v1")
app.include_router(evidence_requests.router, prefix="/v1")
app.include_router(sign_offs.router, prefix="/v1")
app.include_router(insights.router, prefix="/v1")
app.include_router(sampling.router, prefix="/v1")
app.include_router(org_profile.router, prefix="/v1")
app.include_router(business.router, prefix="/v1")
