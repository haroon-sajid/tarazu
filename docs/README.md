# docs/: Tarazu Documentation

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

**Outputs:**

| File | What it is |
|---|---|
| `architecture.md` | System design: the modular monolith, its boundaries, and the data flow through a case. |
| `api-contracts.md` | The single source of truth for the public HTTP API and the internal module interfaces. Changing a contract means changing this file and `backend/app/shared/` in the same commit. |
| `product-plan.md` | Positioning, phases with acceptance criteria, and a delivery status kept current per item. |
| `decisions/` | One ADR per significant decision, numbered and immutable once accepted. |
| `hackathon-plan.md` | The step-by-step hackathon build plan. Superseded once the event ended; kept for the record. |

The delivery status a reader is most likely to want is the one in
[CLAUDE.md](../CLAUDE.md), which is updated with each change; `product-plan.md`
carries the same status per acceptance criterion.

**Does not belong here:** Code, generated API docs, user-facing help content,
and per-service implementation notes; those live in each service's README.
