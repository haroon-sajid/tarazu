# 0001 — HTTP routers live in `app/api/`, not inside the modules

- **Status:** Accepted
- **Deciders:** Lead
- **Supersedes:** the sketch in the original `backend/app/main.py` docstring,
  which planned one router per module (`/v1/extractions`, `/v1/matches`,
  `/v1/flags`, `/v1/assistant`, `/v1/reports`).

## Context

The public API the frontend actually needs is five endpoints:

```
POST /v1/upload
GET  /v1/review-items
POST /v1/review-items/{id}/approve
POST /v1/review-items/{id}/reject
GET  /v1/dashboard
```

Only one of them maps cleanly onto a single module. `/v1/upload` belongs to
`extraction/`, but `/v1/review-items` is a **composition** of extraction output,
`matching.service.run_matching`, and `rules.service.evaluate_flags`, and
`/v1/dashboard` counts across all three. Approve and reject belong to neither —
they are a human decision plus an audit-trail write.

Putting a composition route inside one module would mean that module importing
another module's internals, or owning logic that is not its own. Both break the
module rules in CLAUDE.md, and both would block the microservice extraction the
boundaries exist to preserve.

## Decision

HTTP routing lives at the app layer, in `backend/app/api/`:

```
app/api/health.py      GET  /health
app/api/upload.py      POST /v1/upload
app/api/review.py      GET  /v1/review-items, POST .../approve, POST .../reject
app/api/dashboard.py   GET  /v1/dashboard
```

`main.py` stays wiring only: create the app, add CORS, include the routers.

Routers may call any module's `service.py`, and nothing else. They never import
module internals, and they contain no matching, math, or rule logic — the
composition they perform is calling two services and returning the result.

## Consequences

**Good**

- No module imports another module. `matching/` and `rules/` stay pure functions
  with no HTTP, no database, and no framework dependency, which is exactly what
  makes them extractable later and trivially testable now.
- The five documented endpoints are shaped by what the frontend needs, not by
  the backend's internal decomposition.
- Dev-D can build and test `matching/` and `rules/` with no FastAPI knowledge.

**Costs**

- Route-to-module ownership is a convention, not a folder boundary. A future
  reviewer must check that `app/api/` stays thin. The rule to enforce: **if a
  router contains a loop over rows, or arithmetic, it is in the wrong place.**
- Extracting a module into its own service later means writing that service's
  own HTTP layer, since it does not carry one today. That is the intended
  trade — the alternative was carrying an unused HTTP layer in every module.

## Notes

While `extraction/`, `matching/`, and `rules/` are being built, the routers read
hand-written fixtures from `sample-data/fixtures/` through
`app/api/fixtures.py`, so the frontend is never blocked. Each route names the
service call that will replace its fixture read in a `TODO(step-3)` comment.
The response shapes are final; only the data source changes.
