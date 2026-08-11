# backend/

**Purpose:** A single FastAPI application built as a modular monolith. All
backend functionality lives in `app/modules/` behind strict module boundaries,
so any module can later be extracted into a standalone service without rewrites.

**Inputs:** HTTPS requests from `frontend/` carrying a Supabase JWT; documents
stored in Supabase Storage.

**Outputs:** JSON API responses, generated reports in Supabase Storage, and
records in the immutable audit trail (Supabase Postgres).

**Does not belong here:**

- Frontend code (`frontend/`), deployment configuration (`infra/`), or development scripts (`scripts/`).
- Cross-module imports of internals. Modules talk only through each module's `service.py` and the schemas in `app/shared/`.
- AI or LLM client code outside `app/modules/extraction/` and `app/modules/assistant/`.
