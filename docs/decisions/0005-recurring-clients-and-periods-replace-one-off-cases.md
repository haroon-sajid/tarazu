# 5. Recurring clients and periods replace one-off cases

Date: 2026-08-29

Status: Proposed — adopted in principle by [docs/product-plan.md](../product-plan.md)
section 5; to be executed in Phase 1, shaped by pilot feedback. Recorded now so
Phase 0 work is built to fit it.

## Context

Today the unit of work is a **case**: one upload of one ledger, one bank
statement, and some invoices, reviewed once. That is the shape of a hackathon
demo and of a one-off engagement. An accounting firm's actual work is
recurring: the same client, every month or quarter, with last period's
decisions and vendors as context for this one.

A tool is used once; a SaaS is used every cycle. The data model has to say
which one Tarazu is.

## Decision

Two entities are added, additively, above the existing case:

- **Client** — a business the firm audits. Belongs to one organization.
  Carries the client's name, its rule configuration (approval limits, and
  later the bank-statement format), and who at the firm owns the
  relationship.
- **Period** — one month or one quarter of one client. Carries the date range
  and a status: `uploaded → extracting → matching → in_review → approved →
  reported`. A period is what documents are uploaded to, what the review queue
  belongs to, what the report is generated for, and what rolls forward: the
  next period is created from the last, with the client's vendors and
  configuration carried across.

The existing `cases` table becomes the implementation of a period. `case_id`
is kept as the row's identity so nothing that references it (review items,
flags, documents, audit records, reports) changes; a period is a case with a
`client_id`, a `period_start`, a `period_end`, and the fuller status set. A
case with no client is a one-off engagement and stays valid.

Alongside them:

- **One normalized transactions table.** Every row from any source — ledger
  row, statement line, invoice — lands in one shape with its source reference
  (document id, page, position, or file row). Matching reads from it rather
  than from per-source lists, and the Business view and Ask Tarazu query it
  directly. Direction (money in / money out) is a column, which is what makes
  "sales" and "profit" answerable questions.
- **Processing as background jobs.** Extraction on a real statement takes tens
  of seconds; a request should not. A period's status is what the job
  advances, and the upload response says "processing" rather than waiting.
- **A read-only owner role.** The business owner is invited to a client, sees
  the Business view for that client's periods, and can approve nothing.

## Consequences

- Phase 0 code was written to fit: `resolve_case_id` is the one place that
  decides which case a request is about and will resolve a period the same
  way; reports and assistant answers are keyed by case id and carry over
  unchanged; rule configuration is already a dictionary the pipeline passes
  in, ready to come from the client row instead of the environment.
- The `awaiting_matching` status is retired as a thing the pipeline produces
  and stays only so pre-existing rows still read; the period statuses above
  replace the case statuses when this ADR is executed.
- The Business view is a view over a period's results, not a second product:
  same engine, same audit trail, a plainer vocabulary, and the accountant
  controls what is shared.
- The migration is additive — new tables and new nullable columns — so it can
  run against a Supabase project with live data without a rewrite.

## Alternatives considered

- **Keep cases and add a "client" label.** Rejected: a label does not roll
  forward, carry configuration, or give the owner something to be invited to.
- **A new `periods` table with cases deleted.** Rejected: every foreign key in
  the system points at `case_id`, and the audit trail's `case_id` must never be
  rewritten. Extending the row is cheaper and keeps history intact.
