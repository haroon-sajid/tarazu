# scripts/

**Purpose:** Developer tooling: schema application, seed and sample data
generation (synthetic bank statements, invoices, and ledgers for local testing),
and repo-level checks.

**Inputs:** A fresh clone and a `.env` file copied from `.env.example`.

**Outputs:** A working local development environment, synthetic test fixtures,
and an applied Supabase schema.

| Script | What it does |
|---|---|
| `apply_supabase_schema.py` | Applies the eleven `infra/supabase/*.sql` migrations in order over `SUPABASE_DB_URL`. `--check` reports which have landed and changes nothing. Every file is idempotent, so re-running is safe. |
| `seed_demo_user.py` | Creates the demo auditor in Supabase Auth and puts them in the default organization. Prints the UUID to paste into `AUTH_DEV_USER_ID`. Everyone else signs themselves up at `POST /v1/auth/signup`. |
| `seed_demo_case.py` | Loads the sample Haroon Textiles case into whichever store is configured, inside the default organization. Idempotent, and it also creates a local login from `DEMO_USER_EMAIL` and `DEMO_USER_PASSWORD`. |
| `generate_demo_documents.py` | Writes `sample-data/demo-documents/`: a synthetic ledger workbook, a multi-page bank statement PDF, and the invoice PDFs, carrying the documented planted errors. Upload these to exercise the real pipeline end to end. |
| `demo_tenant_isolation.py` | Two firms sign up, each opens a case, and each tries every route that could reach the other's data. Runs in-process against a throwaway local store, or against a live server with `TARAZU_BASE_URL`. |

`demo_tenant_isolation.py` sets `TARAZU_DOTENV=0` before anything loads, as the
test suite does, so the check can never reach a real project by accident.
`apply_supabase_schema.py` is the one script that deliberately reads `.env`: it
needs `SUPABASE_DB_URL`, which nothing else in the codebase uses.

**Does not belong here:**

- Production code, or anything a deployed service imports.
- Real client data. Sample data must be entirely synthetic.
- Deployment automation, which belongs in `infra/`.
