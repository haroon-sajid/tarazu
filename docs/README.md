# docs/ — Tarazu Documentation

Tarazu (ترازو, "the scales") is a production-grade platform for audit firms. AI
vision models extract structured data from bank statements, invoices, and
ledgers, while all matching, math, and red-flag rules are performed by
deterministic code. Every AI output carries a confidence level and source
provenance, every item requires explicit human approval, and every action is
recorded in an immutable audit trail.

**Stack:** Next.js (frontend), FastAPI modular monolith (backend), Supabase
(Postgres, auth, storage), and Qwen VL via Alibaba Model Studio.

**Purpose:** Human- and agent-readable documentation for the whole system:
architecture, API contracts, and architecture decision records (ADRs).

**Inputs:** Design discussions, contract changes, and decisions made during
development.

**Outputs:** `architecture.md` (system design), `api-contracts.md` (the single
source of truth for the public HTTP API and internal module interfaces),
`decisions/` (one ADR per decision), `product-plan.md` (the product plan v2:
positioning, phases with acceptance criteria, and a delivery status that is
kept current), and `hackathon-plan.md` (the step-by-step hackathon build plan;
superseded once the event ends).

**Does not belong here:** Code, generated API docs, user-facing help content,
and per-service implementation notes; those live in each service's README.
