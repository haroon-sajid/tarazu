# 4. Tarazu is an audit layer, not a system of record

Date: 2026-08-29

Status: Accepted

## Context

After the hackathon build, the product direction under discussion was an
"all in one financial platform": bookkeeping screens, invoicing, payroll,
inventory, tax filing, and the reconciliation engine underneath. Each of those
is a product in its own right with incumbents, and each would have pulled the
team away from the one thing the current build does that nothing generic does:
evidence-grade reconciliation with provenance, deterministic math, human
decisions, and an append-only trail.

The question was where the product boundary sits. See
[docs/product-plan.md](../product-plan.md), sections 1, 3, and 11.

## Decision

**Tarazu sits on top of the records a business already has. It is never the
place those records are created or kept.**

- Data enters through imports: ledger exports (Excel/CSV), bank statements
  (PDF), invoices and receipts (PDF/images). Direct integrations (QuickBooks,
  Xero) are imports too, when they come.
- Tarazu never becomes the source of truth for a transaction. It records what
  it read, what it matched, what it flagged, and what a human decided — and
  those records are evidence about the client's books, not the books.
- Consequently there are **no bookkeeping or data-entry screens, no invoicing,
  no payroll, no inventory, no point of sale, and no direct tax filing.** Tax
  work is supported through reconciliation output and, later, integrations.
- Two things stay absolute whatever else is built: **no auto-approval of
  anything**, and **no assistant answer that is not grounded in the uploaded
  documents**.

The primary customer is the accounting firm, whose review-and-approve workflow
is the one the product already models; the business owner is reached through
the firm, as a read-only view (ADR 0005), not as a separate product.

## Consequences

- The module map does not grow a `bookkeeping/` or `invoicing/` module, and
  proposals to add one are out of scope by this decision rather than by
  argument each time.
- Every new feature has to answer "does this reconcile, flag, explain, or
  report on records the client already has?" If not, it belongs in an
  integration or in someone else's product.
- The positioning line follows from the boundary and is used everywhere:
  *Tarazu reconciles your books, flags what needs attention, and explains it in
  plain language. The AI assists, the human decides.* The product never claims
  fraud detection or a fully automated audit; it "flags items that need
  review". Copy in the README, the landing page, and CLAUDE.md was aligned with
  this decision.
- Recurring use — the thing that makes a SaaS rather than a tool — comes from
  running periods for clients (ADR 0005), not from owning the ledger.

## Alternatives considered

- **The all-in-one platform.** Rejected: it dilutes the differentiator, competes
  with entrenched bookkeeping products on their strongest ground, and multiplies
  the surface area before a single firm has run a real period.
- **Bookkeeping as a "later" module with the boundary left open.** Rejected: an
  open boundary is one every roadmap discussion re-litigates. Closing it is the
  decision.
