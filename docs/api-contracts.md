# API Contracts

> Placeholder — the single source of truth for (a) the public HTTP API between
> `frontend/` and `backend/`, and (b) the internal module interfaces
> (`service.py` signatures + `app/shared/` schemas).
> Any contract change MUST update this file and `backend/app/shared/` in the same change.

## Conventions

- All public routes versioned: `/v1/...`, paths in `lowercase-kebab-case`.
- JSON request/response bodies; schemas defined in `backend/app/shared/`.
- Every AI-produced field carries `confidence: "high" | "medium" | "low"` and
  `source: { document_id, page, region? }` provenance.
- All mutating endpoints emit an audit-trail record.
- Module-to-module calls go through `service.py` only, passing `shared/` schema
  objects — these interfaces are contracts too, kept microservice-extractable.

## Public API surface (contracts to be defined)

| Module | Base path | Contract status |
|---|---|---|
| extraction | `/v1/extractions` | TBD |
| matching | `/v1/matches` | TBD |
| rules | `/v1/flags` | TBD |
| assistant | `/v1/assistant` | TBD |
| reports | `/v1/reports` | TBD |
