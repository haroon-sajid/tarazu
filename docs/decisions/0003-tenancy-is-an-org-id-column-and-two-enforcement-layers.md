# 3. Tenancy is an `org_id` column, enforced twice

Date: 2026-08-22

Status: Accepted

## Context

Tarazu was built with one seeded demo auditor. Every Postgres row-level security
policy read `using (true) with check (true)` for `authenticated`, and every
repository method took a `case_id` and nothing else. That is correct for one
firm and catastrophic for two: any authenticated user could read any case.

A tenant here is an accounting firm. Firms are small, long-lived, and never
share an engagement, so the boundary is hard and total — there is no "shared
case", no cross-firm report, and no reason to ever join across the boundary.

Three shapes were considered:

1. **A schema per tenant.** Airtight, but every migration becomes N migrations,
   and Supabase's RLS, Storage, and PostgREST are all built around one schema.
2. **A database per tenant.** Airtight and operationally heavy, for a product
   whose whole persistence story is one Supabase project.
3. **An `org_id` column on every tenant-owned table.** One schema, one
   migration, and isolation expressed as a predicate.

## Decision

**Option 3, with the predicate enforced in two independent layers.**

- `organizations` and `organization_members` are the tenancy tables. Membership
  is the only thing that grants access to a firm's rows.
- Every tenant-owned table — `cases`, `documents`, `extractions`,
  `review_items`, `flags`, `benford_results`, and `audit_trail` — carries
  `org_id`.
- **Layer one, the database.** RLS policies admit a row only when its `org_id`
  is in `public.current_user_org_ids()`. This protects anything that reaches
  Postgres without going through the backend: the browser with an anon key,
  `psql`, a future edge function.
- **Layer two, the application.** Every `CaseRepository` method takes `org_id`
  as its first argument and puts it in the `where` clause. This is not
  redundant: the backend talks to PostgREST with the service role, which
  *bypasses RLS*, so layer one would not protect the path the app actually uses.

Neither layer is trusted to be the only one.

### The organization is resolved, never supplied

`get_current_org` maps the caller's verified `user_id` to an
`organization_members` row on every request. No route accepts an `org_id` in a
body, a query string, or a header, and no `org_id` claim is read from the token.
An org id supplied by the caller is an authorisation decision made by the
caller.

### Cross-tenant reads are `404`, not `403`

A `403` on another firm's case id confirms that the case exists — that some firm
on this platform has a case `CASE-abc123` and an item `RI-0007`. That is itself
a disclosure, and it is exactly the primitive an attacker enumerates with.

So the filter is in the query, not in a check after the fetch: the application
code cannot tell "belongs to someone else" from "was never created", and
therefore cannot leak the difference. `403` is kept for the one case where no
resource is named at all — an authenticated user who belongs to no organization.

### The audit trail is narrowed, never loosened

`audit_trail` gains `org_id` and a membership-scoped `select` policy. It gains
nothing else. The `revoke update, delete ... from anon, authenticated,
service_role` stands, the `before update or delete` trigger is untouched, and
there is still no `update` policy and no `delete` policy.

The backfill matters here. Adding a column and then `UPDATE`-ing it would be
refused by the table's own trigger — correctly. So both migrations use
`alter table ... add column ... default`, which fills existing rows as DDL
without ever issuing a row update. The trail gained a tenant column without
anyone having to ask it for an exemption.

## Consequences

- One migration, one schema, one set of policies. A new tenant is two rows.
- **Every repository signature changed.** `get_case(case_id)` became
  `get_case(org_id, case_id)`, and so on throughout. That churn is the point: a
  method that can be called without a tenant is a method that will be.
- Two identifiers had to be widened, because they were only ever unique within
  one case and would otherwise have let one firm's write clobber another's:
  - `review_item_id` is now `{case_id}-RI-{n}`. `POST
    /v1/review-items/{id}/approve` names an item and nothing else, so a bare
    `RI-0001` was ambiguous the moment a second case existed — and an ambiguous
    approve is a decision recorded against the wrong row.
  - `flags` is keyed on `(org_id, case_id, flag_id)`. `flag_id` is minted by
    `rules/`, which numbers flags within the case it was handed.
- A user belongs to one organization for now. The table is a join table and the
  `owner`/`member` roles exist, so inviting a colleague, and later switching
  between firms, are additive changes — a route, not a reshape.
- The local SQLite store became its own identity provider (`users`, PBKDF2,
  locally signed JWTs) so the two-firm flow can be run end to end with no
  network. With Supabase configured none of it is reachable: identities live in
  `auth.users` and tokens come from GoTrue.

## Verifying it

- `backend/tests/test_tenancy.py` — two firms in one store, every route tried
  across the boundary.
- `scripts/demo_tenant_isolation.py` — the same thing end to end over the real
  app and the real local store.
- `infra/supabase/0002-organizations.sql` — the RLS half, with a `set local
  role` recipe at the bottom for checking it in Postgres.
