# infra/

**Purpose:** Deployment configuration and infrastructure-as-code: the Supabase
schema, container orchestration, environments, and CI/CD definitions.

**Inputs:** The frontend and backend Dockerfiles and their environment
requirements (variable names in `.env.example`).

**Outputs:** Deployable environment definitions for two deployables:
`frontend/` and the `backend/` modular monolith. If a module is later extracted
into its own service, it gets its own deployment definition here.

**Does not belong here:** Application code, secrets or filled-in credentials
(names only; values come from a secret manager), and local-only development
scripts (`scripts/`).

## supabase/

| File | What it does |
|---|---|
| `schema.sql` | The base tables and the audit-trail hardening. **Single-tenant on its own** — its RLS policies grant every authenticated user every row. Idempotent. |
| `0002-organizations.sql` | Adds `organizations`, `organization_members`, and `org_id` everywhere; backfills existing rows into the default organization; replaces those policies with membership-scoped ones. Idempotent. |
| `0003-api-keys.sql` | Adds `api_keys`, so a firm can connect n8n, Zapier, or its own software. Column privileges keep `key_hash` unreadable to every browser-facing role. Idempotent. |
| `0004-revoke-truncate.sql` | Revokes TRUNCATE, which RLS does not cover. Without it `anon` could empty every table, `audit_trail` included. Idempotent. |
| `0005-audit-id-is-text.sql` | Makes `audit_trail.audit_id` text, matching the `AUD-…` ids the application mints. Idempotent. |
| `verify-audit-immutability.sql` | Proves the trail cannot be rewritten. Every UPDATE, DELETE, and TRUNCATE in it must fail. |

**Run all five, in order** — or `python scripts/apply_supabase_schema.py`, which
does it for you and reports which have landed. A project with only `schema.sql`
applied is one in which any authenticated user can read any firm's cases.

### Setting up a project

1. Create the Supabase project.
2. Put `SUPABASE_DB_URL` in `.env` and run `python scripts/apply_supabase_schema.py`,
   which applies every file above in order. To do it by hand instead, paste
   `schema.sql`, `0002-organizations.sql`, `0003-api-keys.sql`,
   `0004-revoke-truncate.sql`, and `0005-audit-id-is-text.sql` into the SQL
   editor, in that order.
3. Storage → New bucket → `tarazu-documents`. **Leave "Public bucket" off.**
   Client documents must never be world-readable; the backend hands the frontend
   short-lived signed URLs instead.
4. Copy `SUPABASE_URL`, the anon/publishable key, the service-role key, and the
   JWT secret (Project Settings → API) into `.env`.
5. `python scripts/seed_demo_user.py` — creates the demo auditor, puts them in
   the default organization, and prints their UUID. **Paste that UUID into
   `AUTH_DEV_USER_ID`**: `cases.created_by` is a foreign key into `auth.users`,
   so the local store's placeholder id will not insert. Everyone else signs
   themselves up at `POST /v1/auth/signup`, which also creates the organization
   they own.
6. `python scripts/seed_demo_case.py` — loads the sample case into that
   organization, so the review screen has something in it before the pipeline
   has been run.
7. Run `verify-audit-immutability.sql`. Every UPDATE, DELETE, and TRUNCATE in it
   must fail.

Step 7 is worth doing on camera. "We did not just promise the trail is
immutable, we revoked the permission — watch" beats a slide claiming it.

### Which JWT scheme is this project on?

New Supabase projects sign access tokens with **asymmetric keys (ES256)** and
publish the public half at `/auth/v1/.well-known/jwks.json`. Older ones use
**HS256** with the shared secret from Project Settings → API → JWT Settings.
Tarazu accepts either — it reads the algorithm from the token header and maps it
to the right key — so there is nothing to configure. Set `SUPABASE_JWT_SECRET`
regardless: it costs nothing and is what an HS256 project needs.

To check which yours uses:

```bash
curl -s https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json
```

A key with `"alg": "ES256"` means asymmetric. An empty `keys` array means the
project is on the legacy shared secret.

### Tenancy

A tenant is one accounting firm. `0002-organizations.sql` puts an `org_id` on
every tenant-owned table and writes one policy shape against
`public.current_user_org_ids()`, so "can this caller see this row" has one
definition in one place. The reasoning, and why the application layer filters as
well even though RLS is in place, is
[ADR 0003](../docs/decisions/0003-tenancy-is-an-org-id-column-and-two-enforcement-layers.md).

The short version of the second half: the backend uses the service role, and
`service_role` bypasses RLS. The policies protect every path that is *not* the
backend; the repository's `where org_id = ...` protects the one that is.

To check the isolation without Postgres, run
`python scripts/demo_tenant_isolation.py` — two firms, one local store, every
cross-tenant route attempted.

### API keys

`0003-api-keys.sql` adds the table a firm's integrations authenticate against.
Two details in it are worth knowing:

- **The raw key is not stored.** `key_hash` is a SHA-256 digest and `key_prefix`
  is the key's non-secret head. Nothing in this table can be turned back into a
  working credential.
- **`key_hash` is not readable by any browser-facing role.** RLS hides other
  organizations' rows but cannot hide a *column*, so the grant is column-level:
  `authenticated` may select every column except that one. A leaked anon key
  yields a list of names and prefixes.

Keys are revoked, never deleted, so the audit trail's `api-key:<prefix>` entries
stay resolvable to a name, a creator, and a date.

### Why the audit-trail hardening is three layers

A convention any future line of code can break is not a guarantee.

1. **`revoke update, delete ... from anon, authenticated, service_role`.** The
   layer that matters most, for a reason that is easy to miss: `service_role`
   **bypasses row-level security**, so RLS alone would not stop a leaked or
   careless service key rewriting history. `BYPASSRLS` does not bypass table
   privileges, so the REVOKE stops it and RLS could not.
2. **RLS policies for insert and select only.** No update policy and no delete
   policy exist, so those actions have no route in even if a privilege were
   granted back by mistake. `force row level security` subjects the table owner
   to them too. `0002-organizations.sql` narrows the *select* policy to your own
   organization and changes nothing else about this list: the REVOKE, the
   trigger, and the absence of an update or delete policy all stand. Its
   backfill uses `add column ... default` rather than an `UPDATE`, because an
   `UPDATE` on this table is refused — correctly — by layer 3.
3. **A `before update or delete` trigger that raises.** Privileges can be
   granted back and policies can be dropped; this refuses the write itself, for
   every role including the owner and a superuser.

The local SQLite store carries equivalent triggers, so the guarantee holds in
both stores — see [ADR 0002](../docs/decisions/0002-two-backing-stores-behind-one-repository.md).

## Still to come

Deployment targets for the backend (Alibaba Cloud ECS or Simple Application
Server) and the frontend, plus the TLS approach that keeps an HTTPS frontend
from being blocked when it calls an HTTP backend.
