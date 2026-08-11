# CLAUDE.md — Tarazu — AI Audit Assistant

Tarazu (ترازو) — "the scales". The AI weighs the evidence, the auditor delivers the verdict.

Guidance for AI agents (Claude Code, Cursor, etc.) working in this repository.
Read this file fully before making any change.

## Project Overview

Tarazu is a production-grade SaaS for auditors. The workflow:

1. Auditor uploads a bank statement (PDF), invoices (PDF/images), and a ledger (Excel/CSV).
2. An AI vision model (Qwen VL via Alibaba Model Studio) extracts structured data from the documents.
3. Deterministic Python code (pandas) performs ALL matching, math, and comparisons.
4. A rules engine flags fraud risks (round numbers, duplicates, weekend entries, near-limit amounts).
5. A human auditor explicitly approves or rejects EVERY flagged/matched item.
6. The system generates a final report (PDF/Excel) with a full, immutable audit trail.

**Stack:** Next.js + TypeScript (frontend) · ONE FastAPI backend as a modular
monolith (Python) · Supabase (Postgres, auth, file storage) · Qwen models via direct API.

## The 7 Reliability Rules (NON-NEGOTIABLE)

Any change that violates one of these rules is wrong, no matter what else it improves.

1. **AI suggests, human decides.** Every item requires an explicit human approve/reject. No auto-approval paths, ever.
2. **All math and matching is deterministic code, never AI.** Sums, comparisons, reconciliation, and matching live in pure Python (pandas). No LLM call may produce or influence a numeric result.
3. **Every extracted number must be traceable to its source** document, page, and location. Extraction output without provenance is invalid.
4. **Every AI output carries a confidence level** (high / medium / low). No confidence, no output.
5. **Every action — AI and human — is logged to an immutable audit trail** in Supabase. Logs are append-only; never add code that updates or deletes audit records.
6. **Client data is never used for model training.** No telemetry, fine-tuning, or feedback loops that send client documents or extracted data to model providers beyond the inference call itself.
7. **AI answers only from uploaded documents, never from external knowledge.** The assistant must refuse questions it cannot ground in the client's uploaded files.

## Architecture: Modular Monolith

The backend is ONE FastAPI app (`backend/app/`) organized as bounded modules under
`app/modules/`. The boundaries mirror a microservice split without the deployment
overhead.

| Component | Responsibility | Uses AI? |
|---|---|---|
| `frontend/` | Upload, human review screen, evidence viewer, dashboard, reports UI | No (displays AI output only) |
| `backend/app/main.py` | App wiring: router registration, middleware. No business logic | No |
| `backend/app/core/` | Config, Supabase JWT auth, Supabase client, append-only audit-trail writer | No |
| `backend/app/shared/` | Schemas/types crossing module boundaries; confidence + provenance structurally required | No |
| `backend/app/modules/extraction/` | Qwen VL document reading, confidence scoring, AI second-opinion check | **Yes** (extraction only) |
| `backend/app/modules/matching/` | Deterministic matching of statement ↔ invoices ↔ ledger (pure Python + pandas) | **Never** |
| `backend/app/modules/rules/` | Deterministic red-flag rules (round numbers, duplicates, weekend entries, near-limit) | **Never** |
| `backend/app/modules/assistant/` | Chat with documents; plain-language + Urdu explanations | **Yes** (grounded in uploaded docs only) |
| `backend/app/modules/reports/` | PDF/Excel report generation, client-friendly summary | No |

## Module Rules (NON-NEGOTIABLE)

- **Each module exposes ONE public interface file: `service.py`.** Other modules may import only that.
- **No cross-module imports of internals.** Data passes between modules via `app/shared/` schemas.
- **`matching/` and `rules/` must never import any AI client** — not even transitively via a helper.
- **Boundaries exist so any module can later be extracted into a microservice without rewrites.** Never take a shortcut (shared mutable state, reaching into another module's files, bypassing `service.py`) that would break extractability.

Each module directory has a README stating its purpose, inputs/outputs, and what it
must NEVER do. Respect those constraints.

## Naming Conventions

- **Product naming** (use consistently in all files, UI, and future scaffolding):
  - Display name: **Tarazu**
  - Full title: **Tarazu — AI Audit Assistant** (use for the first mention in a file; just "Tarazu" after that)
  - Code slug / package / repo name: `tarazu` (lowercase)
  - Env var prefixes and module names stay unchanged (`EXTRACTION_*`, `matching/`, etc. — no renaming to tarazu-*).
- **All folder and file names: `lowercase-kebab-case`** (e.g. `api-contracts.md`).
  Exceptions: conventional files (`README.md`, `CLAUDE.md`, `Dockerfile`) and
  language-mandated names (Python modules use `snake_case.py`, React components may use framework conventions inside `frontend/`).
- Python: `snake_case` functions/variables, `PascalCase` classes; module packages under `app/modules/` are single-word lowercase (`extraction`, `matching`, `rules`, `assistant`, `reports`).
- TypeScript: `camelCase` functions/variables, `PascalCase` types/components.
- API routes: `lowercase-kebab-case` paths, versioned (`/v1/...`).
- Environment variables: `SCREAMING_SNAKE_CASE`, prefixed per module (see `.env.example`).

## Rules for AI Agents Working Here

- Do not move logic across module boundaries; propose an ADR in `docs/decisions/` instead.
- Do not add AI/LLM calls or AI client imports to `matching/`, `rules/`, `reports/`, `core/`, or `main.py`.
- Update `docs/api-contracts.md` and `backend/app/shared/` in the same change whenever a contract changes.
- Read the README of any folder before modifying its contents.
