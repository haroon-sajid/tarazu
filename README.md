# Tarazu — AI Audit Assistant

Tarazu (ترازو, "the scales") is a production-grade SaaS platform for audit firms.
An auditor uploads a bank statement (PDF), invoices (PDF or images), and a ledger
(Excel or CSV). An AI vision model reads the documents, deterministic Python code
performs all matching and math, a rules engine flags potential fraud risks, and a
human auditor approves or rejects every item before the system generates the
final report with a complete audit trail.

The core principle: the AI suggests, the human decides. All math is deterministic code.

## Stack

- **Frontend:** Next.js with TypeScript
- **Backend:** a single FastAPI application (Python), built as a modular monolith with strict module boundaries
- **Data, auth, and storage:** Supabase (Postgres, authentication, file storage)
- **AI:** Qwen vision models (Qwen VL) via the Alibaba Model Studio API

## Repository Layout

| Path | Contents |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Rules and boundaries for AI coding agents. Read this first. |
| [docs/](docs/) | Architecture, API contracts, and decision records |
| [frontend/](frontend/) | Next.js app: upload, review screen, evidence viewer, dashboard, and reports UI |
| [backend/](backend/) | The FastAPI app: `core/`, `shared/`, and the bounded modules (extraction, matching, rules, assistant, reports) |
| [infra/](infra/) | Deployment configuration and infrastructure placeholders |
| [scripts/](scripts/) | Development setup and sample data generation |

Module boundaries inside `backend/app/modules/` are strict. Each module exposes a
single `service.py` interface, so any module can later be extracted into a
standalone service without rewrites. See [CLAUDE.md](CLAUDE.md) for the full set
of rules.

## Status

Early scaffold. The repository currently contains the folder structure and
contracts only; no business logic has been implemented yet. See
[docs/architecture.md](docs/architecture.md) for the target design.
