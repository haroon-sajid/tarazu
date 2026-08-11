# backend/

**Purpose:** ONE FastAPI application — a modular monolith. All backend
functionality lives in `app/modules/` behind strict module boundaries, so any
module can later be extracted into a microservice without rewrites.

**Inputs:** HTTPS requests from `frontend/` with a Supabase JWT; documents in
Supabase Storage.
**Outputs:** JSON API responses; generated reports in Supabase Storage; records in
the immutable audit trail (Supabase Postgres).

**Does NOT belong here:**
- Frontend code (→ `frontend/`), deployment configs (→ `infra/`), dev scripts (→ `scripts/`).
- Cross-module imports of internals — modules talk only via each module's `service.py` and the schemas in `app/shared/`.
- AI/LLM client code outside `app/modules/extraction/` and `app/modules/assistant/`.
