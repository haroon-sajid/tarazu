"""Tarazu — AI Audit Assistant — FastAPI application entry point (placeholder).

Wiring only: create the FastAPI app, attach auth middleware from core/,
and include each module's router. No business logic in this file.

Planned:
    app = FastAPI(title="Tarazu")
    app.include_router(extraction.router, prefix="/v1/extractions")
    app.include_router(matching.router,   prefix="/v1/matches")
    app.include_router(rules.router,      prefix="/v1/flags")
    app.include_router(assistant.router,  prefix="/v1/assistant")
    app.include_router(reports.router,    prefix="/v1/reports")
"""
