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
| [sample-data/](sample-data/fixtures/) | Synthetic fixtures the API serves while the pipeline is built |
| [infra/](infra/) | Deployment configuration and infrastructure placeholders |
| [scripts/](scripts/) | Development setup and sample data generation |

Module boundaries inside `backend/app/modules/` are strict. Each module exposes a
single `service.py` interface, so any module can later be extracted into a
standalone service without rewrites. See [CLAUDE.md](CLAUDE.md) for the full set
of rules.

## Running the backend

```bash
python -m venv .venv && .venv/Scripts/activate   # macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
```

**Locally, with no Supabase and no Qwen credentials.** The app falls back to a
SQLite store and cached extractions, so the whole flow runs offline:

```bash
export AUTH_ALLOW_DEV_USER=true    # development only — this turns auth off
export DEMO_MODE=true              # replay cached extractions instead of calling Qwen

python scripts/seed_demo_case.py                 # load the sample case
uvicorn app.main:app --reload --app-dir backend
```

```bash
curl http://localhost:8000/health
curl http://localhost:8000/v1/review-items
curl http://localhost:8000/v1/dashboard
curl -X POST http://localhost:8000/v1/review-items/RI-0002/approve \
     -H 'Content-Type: application/json' -d '{"note":"Vouched."}'
```

That last call writes a row to the audit trail. It cannot be edited or deleted
afterwards, by the app or by anyone reaching past it.

**With real accounts, still offline.** A tenant is one accounting firm. Sign up
and the backend creates your organization and makes you its owner; every row you
then create carries its `org_id`, and no other firm can read one of them.

```bash
curl -X POST http://localhost:8000/v1/auth/signup -H 'Content-Type: application/json' \
     -d '{"email":"partner@lahore-audit.pk","password":"at-least-8-chars",
          "organization_name":"Lahore Audit Associates"}'
curl -X POST http://localhost:8000/v1/auth/login -H 'Content-Type: application/json' \
     -d '{"email":"partner@lahore-audit.pk","password":"at-least-8-chars"}'
# then: -H "Authorization: Bearer <access_token>" on every other call
```

To see the isolation rather than take its word for it — two firms, one store,
every cross-tenant route attempted:

```bash
python scripts/demo_tenant_isolation.py
```

**Connecting your own tools.** Generate an API key and n8n, Zapier, or a cron
script can read the queue and post decisions without a person signing in. The
key is shown once, is stored only as a SHA-256 digest, and reaches nothing
outside your organization:

```bash
curl -s -X POST http://localhost:8000/v1/api-keys \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"n8n integration","scopes":["read"]}'
# -> {"api_key":"trz_live_...", ...}   save it now; it is not shown again

curl -s -H 'X-API-Key: trz_live_...' \
  'http://localhost:8000/v1/review-items?decision=pending&flagged=true'
```

Scopes, revocation, and the n8n setup are in
[docs/api-contracts.md](docs/api-contracts.md#api-access).

**Against Supabase.** Follow [infra/README.md](infra/README.md): run
`schema.sql` and then `0002-organizations.sql`, create the private bucket, seed
the demo user, fill in `.env`. Setting `SUPABASE_URL` switches the store over;
nothing else changes.

`pytest` from the repo root. Interactive API docs: <http://localhost:8000/docs>.

## Status

The backend runs end to end. Documents are stored, extracted, persisted, and
reviewed; every mutating call appends to an immutable audit trail; the dashboard
counts real data.

**Done:** data contracts, the five public endpoints plus signup, login, and a
per-item audit trail, Qwen VL extraction with provenance and a verification
pass, the pandas ledger reader, Supabase persistence and auth (with a local
SQLite fallback), the audit-trail hardening, multi-tenancy — organizations,
membership-scoped RLS, and an `org_id` filter on every repository read and
write ([ADR 0003](docs/decisions/0003-tenancy-is-an-org-id-column-and-two-enforcement-layers.md)) —
and scoped API keys for integrations, which the trail records as
`api-key:<prefix>`.

**Not done:** `matching/` and `rules/` are agreed signatures only — until they
land, `POST /v1/upload` stores and extracts a case, then parks it at
`awaiting_matching` and says so rather than inventing results. Reports and the
frontend are also outstanding.

See [docs/api-contracts.md](docs/api-contracts.md) for the contracts,
[docs/architecture.md](docs/architecture.md) for the design, and
[docs/hackathon-plan.md](docs/hackathon-plan.md) for the build sequence.
