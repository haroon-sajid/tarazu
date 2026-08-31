# Architecture

> Placeholder. This document will be expanded as the system is built.

## Overview

Tarazu — AI Audit Assistant is a modular monolith: a Next.js frontend and a
single FastAPI backend whose business capability lives in strictly bounded
modules, with Supabase providing Postgres, auth, and file storage.

```
frontend (Next.js)          integrations (n8n, Zapier, the firm's own code)
   |  Supabase JWT             |  X-API-Key: trz_live_...
   |  (identifies the user;    |  (identifies the key; scoped read / write)
   |   never the organization) |
   v                           v
backend (single FastAPI app)
|-- api/        routers; get_principal authenticates and resolves the firm
|-- core/       config, JWT + API-key auth, the two stores, audit-trail writer
|-- shared/     schemas crossing module boundaries (confidence and provenance required)
`-- modules/    each exposes one public interface: service.py
    |-- extraction/  Qwen VL: documents to structured data with confidence   [AI]
    |-- matching/    pandas: deterministic matching, no AI
    |-- rules/       deterministic red-flag rules, no AI
    |-- analytics/   pandas: sales-analytics readout, no AI
    |-- assistant/   grounded chat and explanations, English and Urdu        [AI]
    `-- reports/     PDF and Excel report generation

Supabase: Postgres (data and immutable audit trail), Auth (JWT), Storage (documents)
```

## Core Flow

1. **Upload.** The auditor uploads a bank statement (PDF), invoices (PDF or images), and a ledger (Excel or CSV). The bytes go to document storage; the ledger is read by pandas.
2. **Extract.** `extraction/` reads the documents with Qwen VL. Every value carries source document and page provenance plus a confidence level, and an AI second-opinion pass cross-checks low-confidence extractions.
3. **Match.** `matching/` reconciles the statement, invoices, and ledger with deterministic pandas logic: one-to-one bank assignment, best pairs first; invoices shared where a duplicate payment demands it.
4. **Flag.** `rules/` applies deterministic red-flag rules — round numbers, weekend entries, duplicate invoices and payments, near-limit amounts, structuring, invoice-sequence gaps — and the Benford first-digit analysis. When the upload includes a sales export, `analytics/` computes the sales readout — revenue by month, product, region, and top customers, with anomaly findings — on the same no-AI path.
5. **Review.** A human approves or rejects every item in the review screen, with the real source page and its provenance box beside the figures (`/v1/documents`). Nothing is finalized without an explicit human decision.
6. **Ask.** `assistant/` answers questions about the case from its persisted results: intent → deterministic query → worded answer with citations and the computed facts. A model, when configured, only rephrases (ADR 0006).
7. **Report.** `reports/` renders the PDF and Excel deliverable from decided items, with provenance and the full audit trail; every generation is an immutable record.

The product boundary — an audit layer over records the client already has,
never a system of record — is ADR 0004; the move from one-off cases to
recurring clients and periods is ADR 0005. The plan they come from is
[product-plan.md](product-plan.md).

## Principles

- Modules communicate only through each module's `service.py` public interface, passing `app/shared/` schema objects. No imports of module internals.
- Module boundaries mirror a microservice split, so any module can later be extracted into its own service without rewrites.
- AI is confined to `extraction/` and `assistant/`. All math and matching is deterministic.
- Every action, by AI or human, is appended to an immutable audit trail in Supabase.
- A tenant is one accounting firm. Every tenant-owned row carries its `org_id`, the organization is resolved server-side from the caller's membership, and another firm's row is `404` rather than `403` — see [ADR 0003](decisions/0003-tenancy-is-an-org-id-column-and-two-enforcement-layers.md).
- A request is authenticated by a person's token or by an organization's API key. Both resolve to one `Principal`, so no route branches on which it was; only the audit trail records the difference, as `api-key:<prefix>`. Keys never manage keys, and a raw key is never stored or logged.
- See [CLAUDE.md](../CLAUDE.md) for the seven non-negotiable reliability rules and the module rules.

## Open Topics

To be documented as decisions are made:

- Async processing and background jobs for long extractions (planned with the
  period entity, ADR 0005)
- Belonging to more than one organization (invitations exist; switching does not)
- Webhooks and the finer API scopes of the product plan, section 7
- Module-boundary enforcement tooling (the matching and rules tests check
  imports by hand; an import linter would generalise it)
- Deployment topology (see `infra/`)
