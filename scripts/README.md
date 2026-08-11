# scripts/

**Purpose:** Developer tooling: environment setup, sample/seed data generation
(synthetic bank statements, invoices, ledgers for local testing), and repo-level
utilities.

**Inputs:** A fresh clone + `.env` (copied from `.env.example`).
**Outputs:** A working local dev environment; synthetic test fixtures.

**Does NOT belong here:**
- Production code or anything a deployed service imports.
- Real client data — sample data must be entirely synthetic.
- Deployment automation (→ `infra/`).
