# backend/app/shared/

**Purpose:** The shared data contracts for the whole app: schemas and types for
extraction results, match results, flags, audit-trail records, confidence
levels, and provenance. This is the only way data passes between modules.

**Inputs:** Contract decisions from `docs/api-contracts.md`.

**Outputs:** Pydantic schemas and typed models imported by every module and
mirrored by `frontend/` types. Every AI-output schema includes `confidence`
(high, medium, or low) and `source` provenance (document id, page, region).
These fields are structurally required, not optional.

**Does not belong here:**

- Business logic, HTTP handlers, or database access. This package contains pure schema and type definitions only.
- Module-internal types that never cross a module boundary; keep those inside the module.
- Anything that imports from `modules/`. The dependency direction is modules to shared, never the reverse.
