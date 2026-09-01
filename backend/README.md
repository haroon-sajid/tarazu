# backend/

**Purpose:** A single FastAPI application built as a modular monolith. All
business capability lives in `app/modules/` behind strict boundaries, so any
module can later be extracted into a standalone service without rewrites.

**Inputs:** HTTPS requests from `frontend/` carrying a bearer token or a scoped
API key, and the uploaded documents themselves.

**Outputs:** JSON API responses, generated reports and documents in the
configured document store, and records in the immutable audit trail.

## Running it

```bash
python -m venv .venv
.venv/Scripts/activate                  # macOS and Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload           # http://localhost:8000, docs at /docs
```

Configuration is read from `.env` in the repository root; every variable is
named and explained in [.env.example](../.env.example). Two switches decide how
the app behaves locally:

- **`SUPABASE_URL` unset** selects the local store: SQLite at `.local/tarazu.db`
  and documents on the filesystem. The code either side of the store is
  identical ([ADR 0002](../docs/decisions/0002-two-backing-stores-behind-one-repository.md)).
- **`DEMO_MODE=true`** replays cached Qwen extractions deterministically and
  keeps the assistant on its deterministic wording, so no API key is needed.

## Tests

```bash
pytest                                  # from the repository root
```

The suite is hermetic: it ignores `.env` (`TARAZU_DOTENV=0`), makes no network
call, and runs background jobs inline (`TARAZU_JOBS_INLINE=1`, set in
`conftest.py`) so nothing has to be polled or slept on.

## Layout

| Path | What |
|---|---|
| `app/main.py` | App creation, middleware, and router registration. Wiring only, no business logic. |
| `app/api/` | Every HTTP router, plus `deps.py` (auth, tenancy, the active case). Routers live here rather than inside the modules ([ADR 0001](../docs/decisions/0001-http-routers-live-in-app-api.md)). |
| `app/core/` | Config, token and API-key verification, the two `CaseRepository` implementations, background jobs, and the append-only audit writer. |
| `app/shared/` | The Pydantic contracts that cross module boundaries. Confidence and provenance are structurally required. |
| `app/modules/` | The bounded modules: `extraction`, `matching`, `rules`, `sampling`, `analytics`, `assistant`, `reports`. |
| `app/pipeline.py` | The upload pipeline: extract, match, flag, Benford, assemble the review queue. |
| `app/dashboard_metrics.py` | The derived dashboard figures, computed once, in code. |
| `tests/` | The suite, including the module import bans, tenancy, and audit immutability. |

## Module boundaries

| Module | Responsibility | Uses AI? |
|---|---|---|
| `extraction/` | Qwen VL document reading, confidence scoring, second-opinion check, and the deterministic CSV and XLSX readers for statements and ledgers | Yes, extraction only |
| `matching/` | Statement, invoice, and ledger reconciliation in pure Python and pandas | Never |
| `rules/` | Red-flag rules and Benford analysis | Never |
| `sampling/` | Random, monetary-unit, and high-value selection, reproducible from a seed | Never |
| `analytics/` | Deterministic sales analytics over a sales export | Never |
| `assistant/` | Ask Tarazu: intent, deterministic query, worded answer with citations | Yes, to rephrase computed facts only ([ADR 0006](../docs/decisions/0006-ask-tarazu-computes-in-code-and-the-model-only-phrases.md)) |
| `reports/` | PDF and Excel generation from decided items | Never |

Each module directory has a README stating its purpose, inputs, outputs, and
what it must never do. Read it before editing.

**Does not belong here:**

- Frontend code (`frontend/`), deployment configuration (`infra/`), or development scripts (`scripts/`).
- Cross-module imports of internals. Modules talk only through each module's `service.py` and the schemas in `app/shared/`.
- AI or LLM client code outside `app/modules/extraction/` and `app/modules/assistant/`. `test_matching.py`, `test_rules.py`, and `test_sampling.py` assert this, including transitive imports.
