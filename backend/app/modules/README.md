# backend/app/modules/

**Purpose:** All business capability, one folder per bounded module:
`extraction/`, `matching/`, `rules/`, `sampling/`, `analytics/`, `assistant/`,
and `reports/`. Boundaries mirror a microservice split, so any module can later
be extracted into its own service without rewrites.

**Module rules** (see [CLAUDE.md](../../../CLAUDE.md) for the full list):

- Each module exposes one public interface file, `service.py`. Other modules may import only that.
- No cross-module imports of internals. Data passes via `app/shared/` schemas.
- `matching/`, `rules/`, `sampling/`, `analytics/`, and `reports/` must never import any AI client, not even transitively through a helper. The test suite asserts this rather than trusting it.
- Only `extraction/` and `assistant/` may hold an AI client, and `assistant/` may use it to word a computed answer, never to compute one ([ADR 0006](../../../docs/decisions/0006-ask-tarazu-computes-in-code-and-the-model-only-phrases.md)).
- Never take a shortcut that would break extractability: no shared mutable state, no reaching into another module's files, no bypassing `service.py`.

**Does not belong here:** Cross-cutting infrastructure (`core/`), shared schemas
(`shared/`), HTTP routers (`api/`, see [ADR 0001](../../../docs/decisions/0001-http-routers-live-in-app-api.md)),
and app wiring (`main.py`).

Each module README states what that module must never do. Read it before
editing.
