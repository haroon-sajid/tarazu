# backend/app/shared/

**Purpose:** The shared data contracts for the whole app: schemas and types for
extraction results, match results, flags, audit-trail records, confidence
levels, and provenance. This is the only way data passes between modules.

**Inputs:** Contract decisions from `docs/api-contracts.md`.

**Outputs:** Pydantic schemas and typed models imported by every module and
mirrored by `frontend/` types. Every AI-output schema includes `confidence`
(high, medium, or low) and `source` provenance (document id, page, region).
These fields are structurally required, not optional.

**`problems.py`** is the one place an upload refusal is worded. Every reader
that cannot use a file — the ledger and bank readers in `extraction/`, the
sales reader in `analytics/`, the pipeline when the document reader is down —
raises a `ReadProblemError` carrying a `ReadProblem`: a stable `code`, a title,
a message complete on its own, and the structure a screen lays out as a guide
(which document, the columns found, the ones missing with the header names
that would satisfy them, and the steps that fix it). `app/api/problems.py`
puts it on the wire beside `detail`; `core/jobs.py` records it on a failed
job. Keeping the copy here, next to the schema it fills, is what stops two
readers from refusing the same file in two different voices.

**Does not belong here:**

- Business logic, HTTP handlers, or database access. This package contains pure schema and type definitions only.
- Module-internal types that never cross a module boundary; keep those inside the module.
- Anything that imports from `modules/`. The dependency direction is modules to shared, never the reverse.
