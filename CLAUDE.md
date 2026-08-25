# CLAUDE.md — Tarazu — AI Audit Assistant

Tarazu (ترازو), "the scales": the AI weighs the evidence, the auditor delivers the verdict.

Guidance for AI agents (Claude Code, Cursor, and others) working in this repository.
Read this file fully before making any change.

## Project Overview

Tarazu is a production-grade SaaS platform for auditors. The workflow:

1. The auditor uploads a bank statement (PDF), invoices (PDF or images), and a ledger (Excel or CSV).
2. An AI vision model (Qwen VL via Alibaba Model Studio) extracts structured data from the documents.
3. Deterministic Python code (pandas) performs all matching, math, and comparisons.
4. A rules engine flags fraud risks: round numbers, duplicates, weekend entries, and near-limit amounts.
5. A human auditor explicitly approves or rejects every flagged or matched item.
6. The system generates a final report (PDF and Excel) with a full, immutable audit trail.

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
| `backend/app/modules/rules/` | Deterministic red-flag rules (round numbers, duplicates, weekend entries, near-limit amounts) | **Never** |
| `backend/app/modules/assistant/` | Chat with documents; plain-language and Urdu explanations | **Yes** (grounded in uploaded docs only) |
| `backend/app/modules/reports/` | PDF and Excel report generation, client-friendly summary | No |

## Module Rules (non-negotiable)

- **Each module exposes one public interface file: `service.py`.** Other modules may import only that.
- **No cross-module imports of internals.** Data passes between modules via `app/shared/` schemas.
- **`matching/` and `rules/` must never import any AI client**, not even transitively through a helper.
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
- Python: `snake_case` functions and variables, `PascalCase` classes; module packages under `app/modules/` are single-word lowercase (`extraction`, `matching`, `rules`, `assistant`, `reports`).
- TypeScript: `camelCase` functions and variables, `PascalCase` types and components.
- API routes: `lowercase-kebab-case` paths, versioned (`/v1/...`).
- Environment variables: `SCREAMING_SNAKE_CASE`, prefixed per module (see `.env.example`).

## Rules for AI Agents Working Here

- Do not move logic across module boundaries; propose an ADR in `docs/decisions/` instead.
- Do not add AI/LLM calls or AI client imports to `matching/`, `rules/`, `reports/`, `core/`, or `main.py`.
- Update `docs/api-contracts.md` and `backend/app/shared/` in the same change whenever a contract changes.
- Read the README of any folder before modifying its contents.

## Development Status (last updated 2026-08-25 — keep this section current)

The project runs as a **local dummy-data demo** while the deterministic
modules and real AI are built. Full route list: the table at the end of
`docs/api-contracts.md`.

**How to run the demo**

- Backend: `uvicorn app.main:app --reload` from `backend/` (port 8000). The
  local `.env` has Supabase commented out, so it uses SQLite at
  `<repo>/.local/tarazu.db`. `DEMO_MODE=true` stubs Qwen extraction
  deterministically — no API key needed.
- Seed: `python scripts/seed_demo_case.py` (idempotent) — creates the demo
  case (client "Haroon Textiles") **and a local login** from
  `DEMO_USER_EMAIL`/`DEMO_USER_PASSWORD` in `.env`.
- Frontend: `npm run dev` from `frontend/` (port 3000, Turbopack). Blanking
  `NEXT_PUBLIC_TARAZU_API_URL` in `frontend/.env.local` switches it to
  zero-backend fixture mode.

**Live end to end** (backend + frontend + tests): auth (signup/login/change
password), tenancy, upload pipeline (extraction stubbed by DEMO_MODE), review
queue with approve/reject and audit trail, dashboard with Benford, API keys
(create / rename / revoke / permanent delete — delete works on active keys),
user profiles (`GET/PUT /v1/profile`: name, job title, phone, avatar as a
size-capped data: URL; Settings → Profile edits it), the case list
(`GET /v1/cases` + `/cases` page; the active case is a localStorage selection
every screen passes as `?case_id=`), the case-wide audit trail viewer
(`GET /v1/audit-trail` + `/audit-trail` page), and members with invitations
(`/v1/members`, `/v1/members/invites`: the owner cuts a single-use `TZ-…`
join code; signup accepts `invite_code` to join that org instead of founding
one — Settings → Members and the signup screen cover both ends).

**Frontend-only previews** (UI is finished; backend does not exist yet):

- `/assistant` — chat grounded in real case data; responses are composed in
  `frontend/src/lib/assistant.ts` until `modules/assistant/` ships. The
  composer accepts document attachments (metadata-acknowledged only for now)
  and voice input via the browser's Web Speech API (`frontend/src/lib/speech.ts`,
  English/Urdu, Chrome/Edge).
- `/documents` — side-by-side audit view; pages render schematically from
  provenance until the backend serves document files.
- Upload's staged "analyzing" panel is presentation over the synchronous
  request.
- Settings: webhooks / notifications / integrations / members-invites are
  static "planned" copy.

**Not implemented (the real work remaining)**: `modules/matching/` and
`modules/rules/` raise `NotImplementedError` (live uploads park at
`awaiting_matching`; the seeded case carries the review data), Benford for
newly uploaded cases, `POST /v1/reports`, the `assistant` backend, document
file serving, and real Qwen extraction (`DEMO_MODE=false` + `EXTRACTION_*`
vars).
