# Architecture

> Placeholder — to be expanded as the system is built.

## Overview

Tarazu — AI Audit Assistant is a modular monolith: a Next.js frontend and ONE FastAPI
backend whose business capability lives in strictly bounded modules, with Supabase
for Postgres, auth, and file storage.

```
frontend (Next.js)
   │  HTTPS + Supabase JWT
   ▼
backend (ONE FastAPI app)
├── core/       — config, JWT auth, Supabase client, append-only audit-trail writer
├── shared/     — schemas crossing module boundaries (confidence + provenance required)
└── modules/    — each exposes ONE public interface: service.py
    ├── extraction/  (Qwen VL: document → structured data + confidence)   [AI]
    ├── matching/    (pandas: deterministic matching, ZERO AI)
    ├── rules/       (deterministic red-flag rules, ZERO AI)
    ├── assistant/   (grounded chat + explanations, English/Urdu)         [AI]
    └── reports/     (PDF/Excel report generation)

Supabase: Postgres (data + immutable audit trail), Auth (JWT), Storage (documents)
```

## Core Flow

1. **Upload** — auditor uploads bank statement (PDF), invoices (PDF/images), ledger (Excel/CSV) → Supabase Storage.
2. **Extract** — `extraction/` reads documents with Qwen VL; every value carries source document/page provenance and a confidence level; an AI second-opinion pass cross-checks low-confidence extractions.
3. **Match** — `matching/` reconciles statement ↔ invoices ↔ ledger with deterministic pandas logic.
4. **Flag** — `rules/` applies deterministic fraud-risk rules (round numbers, duplicates, weekend entries, near-limit amounts).
5. **Review** — a human approves/rejects every matched/flagged item in the frontend review screen; nothing is finalized without explicit human decision.
6. **Report** — `reports/` generates PDF/Excel output with the full audit trail.

## Principles

- Modules communicate only through each module's `service.py` public interface, passing `app/shared/` schema objects. No imports of module internals.
- Module boundaries mirror a microservice split so any module can later be extracted into its own service without rewrites.
- AI is confined to `extraction/` and `assistant/`. All math/matching is deterministic.
- Every action (AI and human) is appended to an immutable audit trail in Supabase.
- See [CLAUDE.md](../CLAUDE.md) for the 7 non-negotiable reliability rules and module rules.

## Open Topics (to document as decided)

- Async processing / background jobs for long extractions
- Supabase row-level security model
- Module-boundary enforcement tooling (e.g. import linter)
- Deployment topology (see `infra/`)
