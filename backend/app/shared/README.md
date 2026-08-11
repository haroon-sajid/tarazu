# backend/app/shared/

**Purpose:** The shared data contracts for the whole app: schemas/types for
extraction results, match results, flags, audit-trail records, confidence levels,
and provenance. This is the ONLY way data passes between modules.

**Inputs:** Contract decisions from `docs/api-contracts.md`.
**Outputs:** Pydantic schemas / typed models imported by every module and mirrored
by `frontend/` types. Every AI-output schema includes `confidence`
(high/medium/low) and `source` provenance (document id, page, region) —
these fields are structurally required, not optional.

**Does NOT belong here:**
- Business logic, HTTP handlers, DB access — pure schema/type definitions only.
- Module-internal types that never cross a module boundary (keep those inside the module).
- Anything importing from `modules/` (dependency direction is modules → shared, never the reverse).
