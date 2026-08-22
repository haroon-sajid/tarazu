"""`GET /health` — liveness. The only route that never requires a JWT."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.shared.api import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="tarazu-backend", version=__version__)
