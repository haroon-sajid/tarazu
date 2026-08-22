# 0002 — Two backing stores behind one repository interface

- **Status:** Accepted
- **Deciders:** Lead

## Context

Supabase is the production store: Postgres for data, Storage for documents, Auth
for the demo user. That is settled and not in question here.

The problem is the gap before it exists. Provisioning the project, running the
schema, creating the bucket, and seeding the user are steps that can stall —
account verification, a key that has not propagated, a teammate who has not been
added to the project. Meanwhile Dev-F needs a backend that responds, Dev-D needs
somewhere to see their matching output land, and the test suite must not depend
on a network round-trip to a shared database that three people are writing to.

An in-memory dictionary would have covered the tests but not the demo, and a
store that forgets everything on restart cannot show an approve click landing in
an audit trail.

## Decision

Two implementations behind the protocols in `app/core/repository.py`:

| | Production | Local |
|---|---|---|
| Data | Supabase Postgres via PostgREST | SQLite |
| Documents | Supabase Storage (private bucket) | A directory on disk |
| Identity | Supabase Auth, JWT verified per request | `AUTH_ALLOW_DEV_USER`, off by default |

`SUPABASE_URL` selects between them, once, at startup. Everything above
`core/` — the pipeline, the routes, the audit writer — is written against
`CaseRepository` and `DocumentStore` and cannot tell which is underneath.

**The append-only guarantee is implemented in both.** Postgres gets revoked
privileges, insert/select-only RLS, and a `before update or delete` trigger;
SQLite gets triggers that abort UPDATE and DELETE. This is the part that makes
the decision defensible rather than merely convenient: a test proving the trail
cannot be rewritten is proving a property of the system, not of one database.

## Consequences

**Good**

- The pipeline runs, is demoed, and is tested before Supabase exists.
- The test suite needs no network and no shared state, so three people can run
  it at once without stepping on each other.
- `DEMO_MODE` plus the local store is a complete offline fallback for demo day:
  no Qwen call, no Supabase call, the same code path throughout.

**Costs**

- Two implementations of one interface to keep in step. The mitigation is that
  the interface is deliberately small — eleven methods — and both are exercised
  by the same tests through the same routes.
- SQLite and Postgres differ in ways this design deliberately does not paper
  over: no `auth.users` foreign key locally, and `status_detail` is a column in
  SQLite but application state against Supabase. Neither affects behaviour the
  API exposes.
- Someone could ship to production having only ever run against SQLite. The
  startup log says which store is in use, and `AUTH_ALLOW_DEV_USER` logs a
  warning on every request it serves, so this is loud rather than silent.

## Alternatives considered

- **Supabase only.** Rejected: it makes the whole backend unrunnable and
  untestable until an external dependency is provisioned, on a build with days,
  not weeks.
- **An in-memory fake.** Rejected: adequate for tests, useless for a demo, and
  it could not have demonstrated the append-only guarantee, which is the point
  of the audit trail.
- **Local Supabase via Docker.** Closer to production, but it is a container
  stack to install and keep running on three machines, and it would not have
  removed the need for the interface anyway.
