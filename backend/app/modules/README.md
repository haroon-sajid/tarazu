# backend/app/modules/

**Purpose:** All business capability, one folder per bounded module: `extraction/`,
`matching/`, `rules/`, `assistant/`, `reports/`. Boundaries mirror the former
microservice split so any module can later be extracted into its own service
without rewrites.

**Module rules (see CLAUDE.md for the full list):**
- Each module exposes ONE public interface file: `service.py`. Other modules may import only that.
- No cross-module imports of internals. Data passes via `app/shared/` schemas.
- `matching/` and `rules/` must never import any AI client.

**Does NOT belong here:** Cross-cutting infrastructure (→ `core/`), shared schemas
(→ `shared/`), app wiring (→ `main.py`).

Each module README states what that module must NEVER do — read it before editing.
