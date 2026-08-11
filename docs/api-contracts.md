# API Contracts

> Placeholder. This file is the single source of truth for (a) the public HTTP
> API between `frontend/` and `backend/`, and (b) the internal module interfaces
> (`service.py` signatures and `app/shared/` schemas). Any contract change must
> update this file and `backend/app/shared/` in the same change.

## Conventions

- All public routes are versioned (`/v1/...`) with paths in `lowercase-kebab-case`.
- Request and response bodies are JSON; schemas are defined in `backend/app/shared/`.
- Every AI-produced field carries `confidence: "high" | "medium" | "low"` and
  `source: { document_id, page, region? }` provenance.
- All mutating endpoints emit an audit-trail record.
- Module-to-module calls go through `service.py` only, passing `shared/` schema
  objects. These interfaces are contracts too, and are kept microservice-extractable.

## Public API Surface

Contracts to be defined:

| Module | Base path | Contract status |
|---|---|---|
| extraction | `/v1/extractions` | To be defined |
| matching | `/v1/matches` | To be defined |
| rules | `/v1/flags` | To be defined |
| assistant | `/v1/assistant` | To be defined |
| reports | `/v1/reports` | To be defined |
