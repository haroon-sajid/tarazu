# Tarazu

**AI Audit Assistant for accounting firms.**

**Tarazu reconciles your books, flags what needs attention, and explains it in
plain language. The AI assists, the human decides.**

Tarazu (ترازو, "the scales") sits on top of the records a business already
has. An accountant uploads a bank statement, invoices, and a ledger export.
Vision AI reads the documents, deterministic code matches every entry and
flags the items that need review, and the accountant approves or rejects each
one with the evidence on screen. Every action lands in an audit trail that
nothing can edit or delete, and the report is generated from what was decided.

The product stands on one rule: **the AI suggests, the human decides.** No model
ever produces a number, a match, or a verdict.

**Live app:** [tarazu-one.vercel.app](https://tarazu-one.vercel.app)

## What it does

- **Reads documents with provenance.** Vision extraction of statements, invoices,
  and photos. Every value carries a confidence level and its exact page and
  position, so any number can be traced back to its source.
- **Reconciles deterministically.** Three-tier matching (exact, date window,
  tolerance) in pure Python and pandas. Each match ships a plain-language reason
  an auditor can quote in a report.
- **Flags what needs attention.** Round numbers, duplicates, weekend entries,
  near-limit amounts, structuring, and sequence gaps, each with severity and
  a plain-language explanation, plus a Benford first-digit analysis. Tarazu
  flags items for review; it never claims to detect fraud.
- **Keeps humans in charge.** Every item requires an explicit approve or reject.
  There is no auto-approval path anywhere in the codebase.
- **Records everything.** A case-wide, append-only audit trail of every upload,
  extraction, flag, decision, question, and report, filterable by actor and action.
- **Answers questions.** Ask Tarazu understands the question, runs the query
  in deterministic code, and words the answer in English or Urdu with the
  documents cited and the computed facts shown. A model may rephrase; it never
  computes, and it refuses what the documents cannot answer.
- **Delivers the report.** PDF and Excel, built from decided items with the
  provenance of every figure and the full audit trail. Every generation is an
  immutable record with its digest.
- **Works as a team.** Multi-tenant workspaces, member invitations with
  single-use join codes and roles, and scoped API keys for n8n, Zapier, or your
  own scripts.

## How a case flows

1. **Upload** the ledger (Excel or CSV), the bank statement (PDF), and the
   invoices (PDFs or phone photos). That opens a case.
2. **Tarazu reads and reconciles** in one pass: extraction with confidence and
   provenance, deterministic matching, red-flag rules, Benford analysis.
3. **The auditor decides.** Approve or reject each item with the real source
   page and its highlighted evidence side by side, ask the assistant anything
   about the case, then generate the report. Every step is on the record.

## Product principles

These are enforced in code and tests, not just stated:

- All math and matching is deterministic code. No LLM touches a number.
- Every extracted value is traceable to its document, page, and position.
- Every AI output carries a confidence level.
- The audit trail is append-only at the database level.
- A tenant is one firm. Another firm's data does not exist from where you stand.
- Client data is never used to train models.
- The assistant answers only from uploaded documents.

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, TypeScript, Tailwind CSS |
| Backend | FastAPI (Python), modular monolith with strict module boundaries |
| Data, auth, storage | Supabase (Postgres, GoTrue, storage), with a SQLite fallback for local work |
| AI | Qwen vision models via the Alibaba Model Studio API |

## Repository layout

| Path | Contents |
|---|---|
| [frontend/](frontend/) | The web app: landing, upload, review, documents, assistant, dashboard, audit trail, settings |
| [backend/](backend/) | The API: `core/`, `shared/`, and the bounded modules (extraction, matching, rules, assistant, reports) |
| [docs/](docs/) | [Product plan](docs/product-plan.md), [API contracts](docs/api-contracts.md), architecture, decision records |
| [infra/supabase/](infra/supabase/) | Postgres schema and migrations, numbered and idempotent |
| [scripts/](scripts/) | Seeding and demo tooling |
| [sample-data/](sample-data/fixtures/) | The synthetic demo case |

Each backend module exposes a single `service.py` interface and modules never
import each other's internals, so any module can later be extracted into a
standalone service without rewrites.

## Running locally

Requirements: Python 3.12+, Node 20+.

**Backend** (SQLite, no external accounts needed):

```bash
python -m venv backend/.venv
backend/.venv/Scripts/activate        # macOS/Linux: source backend/.venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env                  # DEMO_MODE=true replays cached extractions
python scripts/seed_demo_case.py      # creates the demo case and a local login
cd backend && uvicorn app.main:app --reload
```

The seed script prints the sign-in credentials. Interactive API docs are at
`http://localhost:8000/docs`.

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_TARAZU_API_URL=http://localhost:8000` in `frontend/.env.local`
to use the local backend. Leave it empty and the app runs on built-in fixtures
with no backend at all.

**Tests:**

```bash
cd backend && pytest
```

## Deployment

The production setup is three free-tier services:

- **Supabase** holds Postgres, auth, and storage. Run the files in
  [infra/supabase/](infra/supabase/) in numeric order, then seed with
  `scripts/seed_demo_user.py` and `scripts/seed_demo_case.py`.
- **Render** runs the backend: root directory `backend`, build
  `pip install -r requirements.txt`, start
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, environment variables from
  `.env.example` (the Supabase block plus `BACKEND_ALLOWED_ORIGINS` set to the
  frontend URL).
- **Vercel** runs the frontend: root directory `frontend`, one environment
  variable, `NEXT_PUBLIC_TARAZU_API_URL`, pointing at the backend.

## API

Every route is versioned under `/v1`, scoped to one organization, and documented
with request and response shapes in [docs/api-contracts.md](docs/api-contracts.md).
Machine access uses scoped API keys (`X-API-Key`); the audit trail records every
key action as `api-key:<prefix>` so automated decisions stay attributable.

## Roadmap

The full plan, with acceptance criteria and delivery status, is
[docs/product-plan.md](docs/product-plan.md).

- **Phase 0 — finish the core: delivered 29 August 2026.** Deterministic
  matching and rules on every upload, PDF and Excel reports with an immutable
  history, the assistant on the backend with citations, and original pages in
  the evidence viewer.
- **Phase 1 — recurring clients and the Business view.** A firm adds a client
  once and runs a period every month; the owner sees a plain-language summary
  with a read-only role.
- **Phase 2 — Ask Tarazu, completed.** The remaining question types (sales,
  profit) once transactions carry direction.
- **Phase 3 — automation.** Webhooks, n8n templates, scheduled monthly reports.
- **Phase 4 — growth.** QuickBooks and Xero import, Pakistani bank-statement
  formats, sales-tax reconciliation, billing.
