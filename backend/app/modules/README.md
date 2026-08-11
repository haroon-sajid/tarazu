# backend/app/modules/

**Purpose:** All business capability, one folder per bounded module:
`extraction/`, `matching/`, `rules/`, `assistant/`, and `reports/`. Boundaries
mirror a microservice split, so any module can later be extracted into its own
service without rewrites.

**Module rules** (see CLAUDE.md for the full list):

- Each module exposes one public interface file, `service.py`. Other modules may import only that.
- No cross-module imports of internals. Data passes via `app/shared/` schemas.
- `matching/` and `rules/` must never import any AI client.

**Does not belong here:** Cross-cutting infrastructure (`core/`), shared schemas
(`shared/`), and app wiring (`main.py`).

Each module README states what that module must never do. Read it before
editing.
