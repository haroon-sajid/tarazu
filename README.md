# Tarazu — AI Audit Assistant

Tarazu (ترازو) — "the scales". The AI weighs the evidence, the auditor delivers the verdict.

Tarazu is a production-grade SaaS where auditors upload a bank statement (PDF), invoices
(PDF/images), and a ledger (Excel/CSV). An AI vision model (Qwen VL) extracts the
data, deterministic Python code does all matching and math, a rules engine flags
fraud risks, a human approves/rejects every item, and the system generates a final
report with a full audit trail.

**Core principle: AI suggests, human decides. All math is deterministic code.**

## Stack

- **Frontend:** Next.js + TypeScript
- **Backend:** ONE FastAPI (Python) app — a modular monolith with strict module boundaries
- **Data/Auth/Storage:** Supabase (Postgres, auth, file storage)
- **AI:** Qwen models (Qwen VL) via Alibaba Model Studio direct API

## Repository Layout

| Path | What it is |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Rules and boundaries for AI coding agents — read first |
| [docs/](docs/) | Architecture, API contracts, decision records |
| [frontend/](frontend/) | Next.js app: upload, review, evidence viewer, dashboard, reports |
| [backend/](backend/) | The FastAPI app: `core/`, `shared/`, and bounded `modules/` (extraction, matching, rules, assistant, reports) |
| [infra/](infra/) | Deployment configs and IaC placeholders |
| [scripts/](scripts/) | Dev setup and sample/seed data generation |

Module boundaries inside `backend/app/modules/` are strict — each module exposes a
single `service.py` interface so any module can later be extracted into a
microservice without rewrites. See [CLAUDE.md](CLAUDE.md).

## Status

Early scaffold — folder structure and contracts only. No business logic yet.
See [docs/architecture.md](docs/architecture.md) for the target design.
