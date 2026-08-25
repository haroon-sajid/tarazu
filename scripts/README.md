# scripts/

**Purpose:** Developer tooling: environment setup, sample and seed data
generation (synthetic bank statements, invoices, and ledgers for local testing),
and repo-level utilities.

**Inputs:** A fresh clone and a `.env` file copied from `.env.example`.

**Outputs:** A working local development environment and synthetic test
fixtures.

| Script | What it does |
|---|---|
| `apply_supabase_schema.py` | Applies `infra/supabase/*.sql` in order over `SUPABASE_DB_URL`. `--check` reports which migrations have landed and changes nothing. All three files are idempotent, so re-running is safe. |
| `seed_demo_user.py` | Creates the demo auditor in Supabase Auth and puts them in the default organization. Everyone else signs themselves up at `POST /v1/auth/signup`. |
| `seed_demo_case.py` | Loads the sample Haroon Textiles case into whichever store is configured, inside the default organization. |
| `demo_tenant_isolation.py` | Two firms sign up, each opens a case, and each tries every route that could reach the other's data. Runs in-process against a throwaway local store, or against a live server with `TARAZU_BASE_URL`. |

**Does not belong here:**

- Production code, or anything a deployed service imports.
- Real client data. Sample data must be entirely synthetic.
- Deployment automation, which belongs in `infra/`.
