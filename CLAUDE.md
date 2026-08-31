# CLAUDE.md — Tarazu — AI Audit Assistant

Tarazu (ترازو), "the scales": the AI weighs the evidence, the auditor delivers the verdict.

Guidance for AI agents (Claude Code, Cursor, and others) working in this repository.
Read this file fully before making any change.

## Project Overview

Tarazu is a production-grade SaaS platform for accounting firms and the
businesses they serve. The workflow:

1. The auditor uploads a bank statement (PDF), invoices (PDF or images), and a ledger (Excel or CSV).
2. An AI vision model (Qwen VL via Alibaba Model Studio) extracts structured data from the documents.
3. Deterministic Python code (pandas) performs all matching, math, and comparisons.
4. A rules engine flags items that need review: round numbers, duplicates, weekend entries, near-limit amounts, structuring, and invoice-sequence gaps.
5. A human auditor explicitly approves or rejects every flagged or matched item.
6. The system generates a final report (PDF and Excel) with a full, immutable audit trail.
7. An assistant answers questions about the case — computed in code from its results, worded with citations, in English or Urdu.

**Positioning (use this line everywhere):** *Tarazu reconciles your books,
flags what needs attention, and explains it in plain language. The AI assists,
the human decides.* Never claim fraud detection or a fully automated audit;
say "flags items that need review."

**Product boundary** ([ADR 0004](docs/decisions/0004-tarazu-is-an-audit-layer-not-a-system-of-record.md)):
Tarazu is an audit layer over records the client already has, never a system
of record. Do not build bookkeeping or data-entry screens, invoicing, payroll,
inventory, point of sale, direct tax filing, auto-approval of anything, or a
chat AI that answers without grounding. The product plan, its phases, and the
delivery status live in [docs/product-plan.md](docs/product-plan.md).

**Stack:** Next.js with TypeScript on the frontend; a single FastAPI backend built
as a modular monolith (Python); Supabase for Postgres, auth, and file storage;
Qwen models called through their direct API.

## The 7 Reliability Rules (non-negotiable)

Any change that violates one of these rules is wrong, no matter what else it improves.

1. **The AI suggests, the human decides.** Every item requires an explicit human approval or rejection. There are no auto-approval paths, ever.
2. **All math and matching is deterministic code, never AI.** Sums, comparisons, reconciliation, and matching live in pure Python (pandas). No LLM call may produce or influence a numeric result.
3. **Every extracted number must be traceable to its source** document, page, and location. Extraction output without provenance is invalid.
4. **Every AI output carries a confidence level** (high, medium, or low). No confidence, no output.
5. **Every action, by AI or human, is logged to an immutable audit trail** in Supabase. Logs are append-only; never add code that updates or deletes audit records.
6. **Client data is never used for model training.** No telemetry, fine-tuning, or feedback loop may send client documents or extracted data to model providers beyond the inference call itself.
7. **The AI answers only from uploaded documents, never from external knowledge.** The assistant must refuse questions it cannot ground in the client's uploaded files.

## Architecture: Modular Monolith

The backend is a single FastAPI app (`backend/app/`) organized as bounded modules
under `app/modules/`. The boundaries mirror a microservice split without the
deployment overhead.

| Component | Responsibility | Uses AI? |
|---|---|---|
| `frontend/` | Upload, human review screen, evidence viewer, dashboard, reports UI | No (displays AI output only) |
| `backend/app/main.py` | App wiring: router registration and middleware. No business logic | No |
| `backend/app/core/` | Config, Supabase JWT auth, Supabase client, append-only audit-trail writer | No |
| `backend/app/shared/` | Schemas and types crossing module boundaries; confidence and provenance structurally required | No |
| `backend/app/modules/extraction/` | Qwen VL document reading, confidence scoring, AI second-opinion check | **Yes** (extraction only) |
| `backend/app/modules/matching/` | Deterministic matching of statement, invoices, and ledger (pure Python and pandas) | **Never** |
| `backend/app/modules/rules/` | Deterministic red-flag rules (round numbers, duplicates, weekend entries, near-limit amounts, structuring, sequence gaps) and Benford | **Never** |
| `backend/app/modules/analytics/` | Deterministic sales analytics over a `sales_data` export (pandas): revenue by month, product, region, top customers, and anomaly findings | **Never** |
| `backend/app/modules/assistant/` | Ask Tarazu: intent → deterministic query → worded answer with citations and facts, English and Urdu | **Yes** (only to rephrase computed facts; never to compute — ADR 0006) |
| `backend/app/modules/reports/` | PDF and Excel report generation from decided items, with provenance and the trail; immutable history | No |

## Module Rules (non-negotiable)

- **Each module exposes one public interface file: `service.py`.** Other modules may import only that.
- **No cross-module imports of internals.** Data passes between modules via `app/shared/` schemas.
- **`matching/`, `rules/`, and `analytics/` must never import any AI client**, not even transitively through a helper.
- **Boundaries exist so any module can later be extracted into a microservice without rewrites.** Never take a shortcut (shared mutable state, reaching into another module's files, bypassing `service.py`) that would break extractability.

Each module directory has a README stating its purpose, inputs and outputs, and
what it must never do. Respect those constraints.

## Naming Conventions

- **Product naming** (use consistently in all files, UI, and future scaffolding):
  - Display name: **Tarazu**
  - Full title: **Tarazu — AI Audit Assistant** (use for the first mention in a file; just "Tarazu" after that)
  - Code slug, package, and repo name: `tarazu` (lowercase)
  - Env var prefixes and module names stay unchanged (`EXTRACTION_*`, `matching/`, and so on; no renaming to tarazu-*).
- **All folder and file names use `lowercase-kebab-case`** (for example `api-contracts.md`).
  Exceptions: conventional files (`README.md`, `CLAUDE.md`, `Dockerfile`) and
  language-mandated names (Python modules use `snake_case.py`; React components may follow framework conventions inside `frontend/`).
- Python: `snake_case` functions and variables, `PascalCase` classes; module packages under `app/modules/` are single-word lowercase (`extraction`, `matching`, `rules`, `analytics`, `assistant`, `reports`).
- TypeScript: `camelCase` functions and variables, `PascalCase` types and components.
- API routes: `lowercase-kebab-case` paths, versioned (`/v1/...`).
- Environment variables: `SCREAMING_SNAKE_CASE`, prefixed per module (see `.env.example`).

## Rules for AI Agents Working Here

- Do not move logic across module boundaries; propose an ADR in `docs/decisions/` instead.
- Do not add AI/LLM calls or AI client imports to `matching/`, `rules/`, `analytics/`, `reports/`, `core/`, or `main.py`.
- Update `docs/api-contracts.md` and `backend/app/shared/` in the same change whenever a contract changes.
- Read the README of any folder before modifying its contents.

## Development Status (last updated 2026-08-31 — keep this section current)

**Phase 0 of [docs/product-plan.md](docs/product-plan.md) ("finish the
core") is delivered:** a case goes from upload to a finished report inside
the product with no step outside it. Full route list: the table in
`docs/api-contracts.md`. The delivery table at the end of the product plan
maps each Phase 0 item to its code.

**How to run it locally**

- Backend: `pip install -r backend/requirements.txt` (adds `reportlab`), then
  `uvicorn app.main:app --reload` from `backend/` (port 8000). The local
  `.env` has Supabase commented out, so it uses SQLite at
  `<repo>/.local/tarazu.db`. `DEMO_MODE=true` replays cached Qwen
  extractions deterministically and keeps the assistant on its deterministic
  wording — no API key needed.
- Seed: `python scripts/seed_demo_case.py` (idempotent) — creates the demo
  case (client "Haroon Textiles") **and a local login** from
  `DEMO_USER_EMAIL`/`DEMO_USER_PASSWORD` in `.env`.
- Frontend: `npm run dev` from `frontend/` (port 3000, Turbopack). Blanking
  `NEXT_PUBLIC_TARAZU_API_URL` in `frontend/.env.local` switches it to
  zero-backend fixture mode.
- Tests: `pytest` from the repo root (hermetic: no `.env`, no network).
- Supabase: nine migrations, `python scripts/apply_supabase_schema.py`;
  `0006-sales-analytics.sql` is the newest.

**Live end to end** (backend + frontend + tests): auth (signup/login/change
password), tenancy, the **full upload pipeline** — extraction (stubbed by
`DEMO_MODE`), deterministic matching, red-flag rules, Benford, review queue
assembly; a deterministic-step failure marks the case `failed` with the
reason — review queue with approve/reject and audit trail, dashboard with
Benford, **sales analytics** (`POST/GET /v1/cases/{case_id}/analytics`: the
deterministic pandas readout over a case's `sales_data` exports — revenue by
month, product, region, top five customers, anomaly findings — saved beside
the Benford result, replaced by a re-run, every run in the trail; the pipeline
computes it at upload time when a sales export rides along), **documents** (`GET /v1/documents`, `/file`, `/pages/{n}`: the
evidence viewer and `/documents` draw provenance on the real page),
**reports** (`POST/GET /v1/reports`, `/download`: PDF + Excel from decided
items with provenance and the trail; append-only `reports` history in both
stores), **Ask Tarazu** (`POST /v1/assistant/chat`: intent → deterministic
query → answer with `answer_confidence`, citations, and facts, EN/UR; both
sides of every exchange in the trail; answers *from* the data as well as
about it — match results, one item by any identifier, the invoices, the bank
lines, every row, a day or month, confidence, the case record; a Qwen key
may choose which fixed query runs for a question the keywords miss, under
checks, and rephrases under a number guard — ADR 0006 amendment), API keys (create / rename / revoke / permanent delete), user
profiles, the case list (the active case is a localStorage selection every
screen passes as `?case_id=`), the case-wide audit trail viewer, and members
with invitations (single-use `TZ-…` join codes).

**Frontend-only or presentational**: the upload screen's staged "analyzing"
panel is presentation over the synchronous request; fixture mode composes
assistant answers in `frontend/src/lib/assistant.ts`; chat attachments are
acknowledged, never read (upload them instead); Settings → webhooks /
notifications / integrations are static "planned" copy (product plan Phase 3).

**Not implemented (next, per the plan's sequence)**: Phase 1 — client and
period entities (ADR 0005), the Business view, the read-only owner role,
background jobs; Phase 2's remaining question types (sales, profit — need
transaction direction from Phase 1); Phase 3 — webhooks, n8n templates,
scheduled reports; real Qwen extraction has the code path (`DEMO_MODE=false`
+ `EXTRACTION_*` vars) but the first run over a real client folder is a
pilot task and is recorded in the product plan when it happens.
`awaiting_matching` is a legacy case status the pipeline no longer produces.
