<div align="center">

# Tarazu

**AI Audit Assistant for accounting firms**

*Tarazu reconciles your books, flags what needs attention, and explains it in
plain language. The AI assists, the human decides.*

[![License: MIT](https://img.shields.io/badge/License-MIT-1f6feb.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776ab.svg)](backend/requirements.txt)
[![Node 20+](https://img.shields.io/badge/Node-20%2B-5fa04e.svg)](frontend/package.json)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688.svg)](backend/)
[![Next.js 15](https://img.shields.io/badge/Web-Next.js%2015-000000.svg)](frontend/)

[Live app](https://tarazu-one.vercel.app) · [Product plan](docs/product-plan.md) · [API contracts](docs/api-contracts.md) · [Architecture](docs/architecture.md) · [Decision records](docs/decisions/)

</div>

---

Tarazu (ترازو, "the scales") sits on top of the records a business already has.
An accountant uploads a bank statement, invoices, and a ledger export. Vision AI
reads the documents, deterministic code matches every entry and flags the items
that need review, and the accountant approves or rejects each one with the
evidence on screen. Every action lands in an audit trail that nothing can edit
or delete, and the report is generated from what was decided.

The product stands on one rule: **the AI suggests, the human decides.** No model
ever produces a number, a match, or a verdict.

## Contents

- [What Tarazu does](#what-tarazu-does)
- [How a period runs](#how-a-period-runs)
- [Reliability rules](#reliability-rules)
- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Testing](#testing)
- [Deployment](#deployment)
- [The API](#the-api)
- [Documentation](#documentation)
- [Status and roadmap](#status-and-roadmap)
- [Security and data handling](#security-and-data-handling)
- [License](#license)

## What Tarazu does

**Reads documents, with provenance.** Vision extraction of bank statements,
invoices, and phone photos through Qwen VL. Every value carries a confidence
level (high, medium, low) and its exact page and position, so any number on
screen can be traced back to the pixels it came from. A low-confidence field
gets a second opinion from the model, and where the two passes disagree the
schema has no field in which the AI could declare a winner: it goes to a human.
Spreadsheet statements and ledgers (CSV, XLSX) skip the model entirely and are
read by pandas, which the audit trail records by name.

**Reconciles deterministically.** Three-tier matching (exact, date window,
tolerance) in pure Python and pandas. Bank matching is one to one and globally
ranked, so the same file produces the same result whatever order the rows
arrived in. Each match ships the rule id and a plain-language reason an auditor
can quote in a report.

**Flags what needs attention.** Round numbers, weekend entries, duplicate
invoices, duplicate payments, near-limit amounts, structuring, and invoice
sequence gaps, each with a severity and an explanation, plus a Benford
first-digit analysis with an honest significance test. Thresholds are per
client, not global. Tarazu flags items for review; it never claims to detect
fraud.

**Keeps humans in charge.** Every item requires an explicit approve or reject.
There is no auto-approval path anywhere in the codebase. A misread value can be
corrected without re-running the match, and both readings are kept.

**Records everything.** A case-wide, append-only audit trail of every upload,
extraction, flag, decision, correction, question, and report, filterable by
actor and action. Append-only is enforced by database privileges and triggers in
both backing stores, not by convention.

**Runs the same client every cycle.** A firm adds a client once, with its own
rule thresholds and reporting preferences, then runs a period each month against
them. Uploads can run as a background job the upload screen polls for real
progress.

**Answers questions.** Ask Tarazu classifies the question, runs the query in
deterministic code, and words the answer in English or Urdu with the documents
cited and the computed facts shown. A model may choose which fixed query runs
and may rephrase the result under a number guard; it never computes, and the
assistant refuses what the uploaded documents cannot answer.

**Analyses sales.** A separate data source from the audit documents: the
client's sales export in whatever shape their software produced it (Excel, ODS,
CSV, TSV, JSON), read with title rows, worksheets, column names, encodings, and
quantity by price all handled. Every cleaning decision is reported back as a
data-quality readout rather than applied silently. The analysis itself is
pandas: revenue by month, product and region breakdowns, top customers, and
anomaly findings, downloadable as a workbook.

**Samples for substantive testing.** Random, monetary-unit, and high-value
selection, reproducible from a seed, so a reviewer can redraw the identical
sample and a workpaper can cite it.

**Delivers the report.** PDF and Excel built from decided items, carrying the
provenance of every figure and the full audit trail, on the firm's own
letterhead, with an Urdu executive summary for the business owner. Every
generation is an immutable record with its SHA-256 digest, and the whole
engagement exports as a byte-reproducible zip with a manifest.

**Works as a team.** Multi-tenant workspaces, member invitations with single-use
join codes, maker-checker sign-off that the item's own decider may not perform,
evidence requests tracked from ask to resolution, firm-wide insights, period
comparison, and scoped API keys for your own scripts and automations.

## How a period runs

1. **Add the client once.** Name, contact, reporting language, and the rule
   thresholds that suit their business.
2. **Open a period and upload** the ledger (Excel or CSV), the bank statement
   (PDF, CSV, or XLSX), and the invoices (PDFs or phone photos). Large uploads
   run as a background job with real progress.
3. **Tarazu reads and reconciles** in one pass: extraction with confidence and
   provenance, deterministic matching, red-flag rules, Benford analysis, and the
   review queue assembled from the result. If a deterministic step fails, the
   case is marked failed with the reason rather than half-finished.
4. **The auditor decides.** Approve or reject each item with the real source
   page and its highlighted evidence side by side. Correct a misread value, ask
   the client for a missing document, or ask the assistant about the case.
5. **A second pair of eyes signs off**, where the client requires it. The signer
   may not be someone who decided items on the case.
6. **Generate the report.** PDF and Excel from what was decided, plus the
   evidence bundle if the file needs to leave the building. Every step above is
   on the record.

## Reliability rules

These are enforced in code and in tests, not merely stated. The full text is in
[CLAUDE.md](CLAUDE.md).

| # | Rule |
|---|---|
| 1 | The AI suggests, the human decides. Every item needs an explicit decision; there are no auto-approval paths. |
| 2 | All math and matching is deterministic code. No LLM call may produce or influence a number. |
| 3 | Every extracted number is traceable to its document, page, and position. |
| 4 | Every AI output carries a confidence level. No confidence, no output. |
| 5 | Every action, by AI or human, is appended to an immutable audit trail. |
| 6 | Client data is never used for model training. |
| 7 | The assistant answers only from uploaded documents, never from outside knowledge. |

Rules 2 and 4 are checked by the test suite: `test_matching.py` and
`test_rules.py` assert that no AI client is importable from those modules, even
transitively.

## Architecture

The backend is a single FastAPI application built as a modular monolith. Module
boundaries mirror a microservice split without the deployment overhead, so any
module can later be extracted into its own service without rewrites.

```
                    Browser (Next.js 15, TypeScript, Tailwind v4)
                                     |
                                HTTPS /v1/*
                                     |
                    FastAPI app  (backend/app/main.py = wiring only)
                                     |
          app/api/*  routers, auth, tenancy scoping  (ADR 0001)
                                     |
        +----------------------------+----------------------------+
        |                            |                            |
    app/core/                   app/shared/                 app/modules/
  config, auth, jobs,        Pydantic contracts       extraction  (Qwen VL)
  repository, audit          crossing boundaries      matching    (no AI)
                                                      rules       (no AI)
                                                      sampling    (no AI)
                                                      analytics   (no AI)
                                                      assistant   (phrasing only)
                                                      reports     (no AI)
                                     |
              Supabase (Postgres, GoTrue, Storage)  or  SQLite + filesystem
```

| Module | Responsibility | Uses AI? |
|---|---|---|
| `extraction/` | Qwen VL document reading, confidence scoring, second-opinion check, deterministic CSV and XLSX readers | Yes, extraction only |
| `matching/` | Statement, invoice, and ledger reconciliation in pure Python and pandas | Never |
| `rules/` | Red-flag rules and Benford analysis | Never |
| `sampling/` | Random, monetary-unit, and high-value selection, reproducible from a seed | Never |
| `analytics/` | Deterministic sales analytics over a sales export | Never |
| `assistant/` | Ask Tarazu: intent, deterministic query, worded answer with citations | Yes, to rephrase computed facts only ([ADR 0006](docs/decisions/0006-ask-tarazu-computes-in-code-and-the-model-only-phrases.md)) |
| `reports/` | PDF and Excel generation from decided items | Never |

Each module exposes a single `service.py` interface; modules never import each
other's internals, and data passes between them as `app/shared/` schemas. Every
module directory has a README stating what it must never do.

## Repository layout

| Path | Contents |
|---|---|
| [frontend/](frontend/) | The Next.js web app: landing, demo, upload, review, evidence viewer, dashboard, analytics, sampling, assistant, reports, insights, settings |
| [backend/](backend/) | The FastAPI app: `api/` routers, `core/` infrastructure, `shared/` contracts, `modules/` business capability, `tests/` |
| [docs/](docs/) | [Product plan](docs/product-plan.md), [API contracts](docs/api-contracts.md), [architecture](docs/architecture.md), [decision records](docs/decisions/) |
| [infra/supabase/](infra/supabase/) | Postgres schema and migrations, numbered and idempotent, plus the audit-immutability proof |
| [scripts/](scripts/) | Schema application, demo seeding, synthetic document generation, tenant-isolation check |
| [sample-data/](sample-data/fixtures/) | The synthetic demo case, parsed through the real schemas on every test run |

## Getting started

**Requirements:** Python 3.12+, Node 20+. No external accounts are needed for
local development.

### Backend

```bash
python -m venv backend/.venv
backend/.venv/Scripts/activate          # macOS and Linux: source backend/.venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env                    # DEMO_MODE=true replays cached extractions
python scripts/seed_demo_case.py        # creates the demo case and a local login
cd backend && uvicorn app.main:app --reload
```

Leaving `SUPABASE_URL` unset is what selects the local store: SQLite at
`.local/tarazu.db` and documents on the filesystem. The code either side of the
store is identical, so the whole pipeline runs before a Supabase project exists.
`DEMO_MODE=true` replays cached Qwen extractions deterministically and keeps the
assistant on its deterministic wording, so no API key is required.

The seed script prints the sign-in credentials. Interactive API docs are served
at <http://localhost:8000/docs>.

### Frontend

```bash
cd frontend
npm install
npm run dev                             # http://localhost:3000
```

Set `NEXT_PUBLIC_TARAZU_API_URL=http://localhost:8000` in `frontend/.env.local`
to use the local backend. Leave it empty and the app runs on built-in fixtures
with no backend at all, which is also what `/demo` uses.

### Optional: run the real pipeline on real files

```bash
python scripts/generate_demo_documents.py   # synthetic ledger, statement, invoices
```

Upload the generated folder through the upload screen with `DEMO_MODE=false` and
an `EXTRACTION_QWEN_API_KEY` set to exercise live extraction end to end.

## Configuration

All variable names are documented with their defaults in
[.env.example](.env.example), grouped by module. The ones that decide how the
app behaves:

| Variable | Effect |
|---|---|
| `SUPABASE_URL` | Set: Supabase Postgres, Storage, and Auth. Unset: local SQLite and filesystem. |
| `DEMO_MODE` | `true` replays cached extractions and deterministic assistant wording. No API key needed. |
| `EXTRACTION_QWEN_API_KEY` | Live vision extraction through Alibaba Model Studio. Falls back to `DASHSCOPE_API_KEY`. |
| `ASSISTANT_QWEN_API_KEY` | Lets the model rephrase computed facts. Without it, the deterministic wording is the answer. |
| `AUTH_ALLOW_DEV_USER` | Serves unauthenticated requests as the dev user. Local only. Must be `false` anywhere deployed. |
| `BACKEND_ALLOWED_ORIGINS` | Comma-separated CORS origins. Add the deployed frontend URL. |
| `RULES_*` | Default red-flag thresholds. Per-client configuration overrides these once clients exist. |
| `NEXT_PUBLIC_TARAZU_API_URL` | Frontend only. Empty means fixture mode. |

Secrets never reach the browser: only `NEXT_PUBLIC_*` variables are exposed, and
the service-role key is backend-only by design.

## Testing

```bash
pytest                                   # from the repository root
```

The suite is hermetic: it ignores `.env`, makes no network calls, and runs
background jobs inline (`TARAZU_JOBS_INLINE=1`, set in `conftest.py`) so nothing
has to be polled or slept on. It covers the pipeline end to end, tenant
isolation, audit-trail immutability, the module import bans, and the fixture
contracts.

The frontend type-checks with:

```bash
cd frontend && npx tsc --noEmit
```

Two checks are worth knowing about:

- `scripts/demo_tenant_isolation.py` signs up two firms, opens a case in each,
  and attempts every route that could reach the other's data.
- `infra/supabase/verify-audit-immutability.sql` proves the trail cannot be
  rewritten. Every UPDATE, DELETE, and TRUNCATE in it must fail.

## Deployment

The production setup is three services, all of which have a usable free tier.

**Supabase** holds Postgres, auth, and storage.

```bash
python scripts/apply_supabase_schema.py          # applies all eleven SQL files in order
python scripts/apply_supabase_schema.py --check  # reports which have landed, changes nothing
python scripts/seed_demo_user.py
python scripts/seed_demo_case.py
```

Create the `tarazu-documents` storage bucket as **private**. Client documents
must never be world-readable; the backend hands out short-lived signed URLs
instead. A project with only `schema.sql` applied is one where any authenticated
user can read any firm's cases, so do not stop halfway. See
[infra/README.md](infra/README.md) for the file-by-file detail.

**Render** runs the backend: root directory `backend`, build
`pip install -r requirements.txt`, start
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`, environment variables from
`.env.example` (the Supabase block plus `BACKEND_ALLOWED_ORIGINS` set to the
frontend URL).

**Vercel** runs the frontend: root directory `frontend`, one environment
variable, `NEXT_PUBLIC_TARAZU_API_URL`, pointing at the backend.

## The API

Every route is versioned under `/v1`, scoped to one organization, and documented
with full request and response shapes in
[docs/api-contracts.md](docs/api-contracts.md).

Two authentication schemes reach the same routes:

- **A bearer token** from `POST /v1/auth/login` or `POST /v1/auth/signup`, which
  is what the web app uses.
- **A scoped API key** in the `X-API-Key` header, for scripts and automations.
  The raw key is shown exactly once at creation and never stored: only its
  prefix and a SHA-256 digest are persisted. The audit trail records key actions
  as `api-key:<prefix>`, so automated activity stays attributable to a named
  key.

```bash
curl -s http://localhost:8000/v1/dashboard \
  -H "X-API-Key: $TARAZU_API_KEY"
```

Which organization a request acts inside is decided on the server from the
caller's identity, never from anything the client sends. See
[ADR 0003](docs/decisions/0003-tenancy-is-an-org-id-column-and-two-enforcement-layers.md).

## Documentation

| Document | What it is |
|---|---|
| [CLAUDE.md](CLAUDE.md) | The working agreement: reliability rules, module rules, conventions, and current delivery status |
| [docs/product-plan.md](docs/product-plan.md) | Positioning, phases with acceptance criteria, and delivery status per item |
| [docs/api-contracts.md](docs/api-contracts.md) | The single source of truth for the HTTP API and module interfaces |
| [docs/architecture.md](docs/architecture.md) | System design |
| [docs/decisions/](docs/decisions/) | One ADR per significant decision, immutable once accepted |
| Module READMEs | Purpose, inputs, outputs, and prohibitions for each bounded module |

## Status and roadmap

Delivery status per item lives in [docs/product-plan.md](docs/product-plan.md).

| Phase | Scope | Status |
|---|---|---|
| **0** | Finish the core: matching and rules on every upload, PDF and Excel reports with immutable history, the assistant with citations, original pages in the evidence viewer | **Delivered** |
| **1** | Recurring clients and periods: a client added once, run every cycle against its own thresholds, as a background job ([ADR 0005](docs/decisions/0005-recurring-clients-and-periods-replace-one-off-cases.md)) | **Delivered** |
| **2** | Ask Tarazu across every question type | **Mostly delivered.** Sales and profit questions need transaction direction, which the normalized transactions table would provide; the assistant says so rather than guessing. |
| **3** | Automation: webhooks, n8n templates, scheduled reports | **Deferred** at the owner's request. The API keys and scopes it builds on are live. |
| **4** | Growth: QuickBooks and Xero import, Pakistani bank-statement formats, sales-tax reconciliation, billing | Not started |

Known gaps, deliberately taken:

- **The Business view** has no dedicated screen yet. The owner-facing artefact
  shipped as the Urdu executive summary in the report, which is what an owner
  actually receives.
- **The Urdu summary is not drawn into the PDF.** reportlab's built-in fonts
  carry no Arabic-script glyphs and it performs neither bidirectional reordering
  nor contextual shaping, so it would render as empty boxes. The workbook and
  the evidence bundle carry it; the PDF prints a pointer to the sheet. Doing it
  properly means bundling a Nastaliq font and adding a shaping pass.
- **Live Qwen extraction** has a working code path and is exercised locally, but
  the first full run over a real client folder is a pilot task, recorded in the
  product plan when it happens.

## Security and data handling

- **Tenancy is enforced twice.** Row-level security in Postgres, and an
  `org_id` filter in every repository read and write. Another firm's row is *not
  found* rather than *refused*.
- **The audit trail is append-only at the database level.** Privileges are
  revoked, no update or delete policy exists, and a trigger refuses the write
  even for a superuser. The SQLite store carries equivalent triggers.
- **Reports are immutable.** Regenerating produces a new record; the old file
  stays downloadable and its digest stays on record.
- **API keys are unrecoverable.** Only a prefix and a SHA-256 digest are stored,
  and `key_hash` is hidden from browser-facing roles by a column-level grant.
- **Documents are private.** The storage bucket is not public; the frontend
  receives short-lived signed URLs.
- **Client data is never used for training.** Documents reach a model only as
  part of an inference call, and no telemetry or feedback loop sends client data
  anywhere else.

## License

[MIT](LICENSE). Copyright (c) 2026 The Tarazu contributors.
