# scripts/

**Purpose:** Developer tooling: environment setup, sample and seed data
generation (synthetic bank statements, invoices, and ledgers for local testing),
and repo-level utilities.

**Inputs:** A fresh clone and a `.env` file copied from `.env.example`.

**Outputs:** A working local development environment and synthetic test
fixtures.

**Does not belong here:**

- Production code, or anything a deployed service imports.
- Real client data. Sample data must be entirely synthetic.
- Deployment automation, which belongs in `infra/`.
