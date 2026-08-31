# Tarazu Product Plan v2

From hackathon project to a SaaS for accountants and small businesses.

- **Date:** 29 August 2026
- **Owner:** Muhammad Haroon Sajid
- **Status:** Adopted. Phase 0 delivered on 29 August 2026 (see
  [Delivery status](#delivery-status) at the end). Phases 1–4 are sequenced
  behind pilot feedback, as section 12 requires.

The decisions in this plan that shape the codebase are recorded as ADRs:
[0004](decisions/0004-tarazu-is-an-audit-layer-not-a-system-of-record.md)
(stay an audit layer),
[0005](decisions/0005-recurring-clients-and-periods-replace-one-off-cases.md)
(clients and periods), and
[0006](decisions/0006-ask-tarazu-computes-in-code-and-the-model-only-phrases.md)
(Ask Tarazu).

## 1. The decision

The proposed "all in one financial platform" direction has good ideas but
expands scope too fast. Tarazu should not become bookkeeping software. It
should stay a financial intelligence and audit layer that sits on top of the
records a business already has.

The direction in one line:

> Tarazu takes the files a business already has (ledger exports, bank
> statements, invoices, receipts), reconciles them, flags issues with evidence,
> explains everything in plain language, and automates the reporting.

**Primary customer:** accounting firms and independent accountants.
**Secondary customer:** small business owners, reached mainly through their
accountants.

Why accountants first:

- One accountant serves 20 to 50 businesses, so every sale multiplies.
- They feel the reconciliation pain directly and bill hours for it.
- They already work in the review-and-approve model Tarazu is built on.
- Small business owners in Pakistan rarely pay for software early. Reach them
  later through a simple mode, not as the first sale.
- The market is not only Pakistan. The product already works in English and
  Urdu, so overseas firms are also reachable.

## 2. What to keep from the current build

These are the real differentiators. Do not dilute them.

- Deterministic matching and math. No model ever produces a number.
- Provenance on every extracted value: document, page, position.
- Human approval on every item. No auto-approve path.
- Append-only audit trail.
- Scoped API keys with attributable actions.
- Assistant grounded only in uploaded documents, in English and Urdu.

Generic dashboards are a commodity. Evidence-grade reconciliation is not. This
is the moat.

## 3. What to change in the proposed plan

**Keep:** the positioning language, the Ask Tarazu query pipeline, API scopes,
the phased rollout.

**Change:**

1. Do not become a system of record. No manual bookkeeping, no invoicing, no
   payroll, no inventory. Data comes in through imports. Direct integrations
   come later.
2. Do not target everyone. Firms first, owners second.
3. Replace one-off cases with recurring clients. A firm adds a client once,
   then runs a period (month or quarter) every cycle. Recurring use is what
   makes this a SaaS instead of a tool.
4. Ship the small-business experience as a view, not a separate product. After
   a period is processed, the owner sees a plain-language summary.
5. Finish the core loop before building anything new. Nothing new ships until
   one real case goes from upload to report inside the product.

## 4. Product structure

Two views on one engine.

**Auditor view** (exists today): cases, matching review, flags, evidence
viewer, audit trail, reports.

**Business view** (new, the simple mode):

- Money in, money out, and profit for the period.
- Issues found: mismatches, missing documents, duplicates, unusual entries.
- Every issue written as one plain sentence, with the evidence behind it.
- Ask Tarazu chat.

The owner never sees auditor language. The accountant controls what is shared.

## 5. Data model changes for production

- **Client entity:** a firm manages many clients.
- **Period entity:** each client has monthly or quarterly periods. The period
  replaces the one-off case as the unit of work.
- **One normalized transactions table:** every row from any source lands in one
  shape with a source reference (document id, page, position, or file row).
- **Processing runs as background jobs** with a queue and retries, not inside
  the request.
- **Clear period status:** uploaded, extracting, matching, in review, approved,
  reported.

## 6. Ask Tarazu architecture

Never send the database to the model.

1. Understand the intent (metric, comparison, search, or explanation).
2. Plan the query over the period data or the documents.
3. Run the calculation in deterministic code.
4. The model writes the explanation from the computed result.
5. The answer shows its sources so the user can verify.

Rules:

- The model formats and explains. It never computes.
- If the data cannot answer, Tarazu says so. No guessing.
- Every question, plan, and answer lands in the audit trail.

## 7. API and automation

- Keep scoped keys: read transactions, run reconciliation, read findings, read
  reports, use assistant.
- Add webhooks: period completed, issue found, report ready.
- Publish ready-made n8n templates: monthly report to email, mismatch alert to
  Slack or WhatsApp. These templates also work as marketing content.

## 8. Roadmap with acceptance criteria

### Phase 0. Finish the core. Target 3 to 4 weeks.

- Live uploads run the full pipeline without parking.
- Matching and rules run on real data, not only the demo case.
- PDF and Excel report generation with an immutable report history.
- Assistant moved to the backend with grounding and citations.
- Original documents served in the evidence viewer.

**Done when** a real client folder (one ledger, one bank statement, about 20
invoices) goes from upload to a finished report with no manual steps outside
the product.

### Phase 1. Recurring clients and Business view. Target 3 weeks.

- Client and period entities, rolling forward each month.
- Business view dashboard with plain-language issues.
- Owner invite with a read-only role.

**Done when** one firm runs two consecutive monthly periods for one client and
the owner understands the summary without help.

### Phase 2. Ask Tarazu backend. Target 2 to 3 weeks.

- The query planning pipeline above.
- Ten core question types: sales, expenses, profit, top vendor, largest
  expenses, unmatched items, missing evidence, duplicates, month comparison,
  search by amount.

**Done when** all ten return correct numbers with sources on the demo case and
one real case.

### Phase 3. Automation. Target 2 weeks.

- Webhooks live.
- n8n templates published.
- Scheduled monthly report automation.

**Done when** a scheduled n8n flow emails the monthly report with zero clicks.

### Phase 4. Growth features. Later.

- QuickBooks and Xero import.
- A library of Pakistani bank statement formats.
- Sales tax reconciliation to support FBR filing work.
- Billing and subscriptions.
- Team roles per client.

## 9. Pricing starting point

A hypothesis to test with real firms, not a final price.

- Firms: per client per month, in the range of Rs 1,000 to 3,000. First client
  free.
- Direct small businesses later: one simple monthly plan.
- Talk to 5 firms before fixing any number.

## 10. Positioning

Use this line everywhere:

> Tarazu reconciles your books, flags what needs attention, and explains it in
> plain language. The AI assists, the human decides.

Never claim fraud detection or a fully automated audit. Say "flags items that
need review."

## 11. What not to build

- Bookkeeping and data entry screens.
- Invoicing, payroll, inventory, or point of sale.
- Tax filing. Support it later through integrations, never file directly.
- Auto-approval of anything.
- A general chat AI that answers without grounding.

## 12. Next 30 days

1. Finish the hackathon round with the focused auditor demo. Do not present the
   pivot to judges.
2. Weeks 1 and 2: complete Phase 0.
3. Week 3: recruit 3 accounting firms in Lahore as pilots. Free for 2 months in
   exchange for weekly feedback.
4. Week 4: start Phase 1, shaped by pilot feedback.

**Done when** 3 firms are processing real periods by 1 October 2026.

---

## Delivery status

Kept current as phases land. Dates are absolute.

### Phase 0 — delivered 29 August 2026

| Item | Where | Status |
|---|---|---|
| Live uploads run the full pipeline without parking | `backend/app/pipeline.py` — matching, rules, Benford, and assembly run on every upload; a failure marks the case `failed` with the reason rather than saving a partial queue. `awaiting_matching` is a legacy status no longer produced. | Done |
| Matching on real data | `backend/app/modules/matching/service.py` — four bank tiers, one-to-one statement assignment with global best-first pairing, non-exclusive invoice matching, `rapidfuzz` party similarity, deterministic under input reordering. | Done |
| Rules on real data | `backend/app/modules/rules/service.py` — round-number, weekend-entry, duplicate-invoice, duplicate-payment, near-limit, structuring, invoice-sequence-gap; `RULES_*` environment overrides; `benford_analysis`. | Done |
| PDF and Excel reports with an immutable history | `backend/app/modules/reports/` (content → reportlab PDF, openpyxl workbook, byte-reproducible), `POST/GET /v1/reports`, `GET /v1/reports/{id}/download`; `reports` table is append-only in SQLite (triggers) and Postgres (`0006`: REVOKE + RLS + triggers). Pending items are counted, never listed as findings. | Done |
| Assistant on the backend with grounding and citations | `backend/app/modules/assistant/` — intent → deterministic query → composed answer (EN/UR) → optional model phrasing with a number guard → citations and facts; `POST /v1/assistant/chat`; both sides of every exchange in the audit trail. | Done |
| Original documents in the evidence viewer | `GET /v1/documents`, `/file`, `/pages/{page}` (PyMuPDF render); the evidence viewer and Documents screen draw provenance boxes on the real page, schematic fallback kept. | Done |
| Acceptance: a real client folder from upload to report with no manual steps | The code path is complete and tested end to end over the demo extraction (`DEMO_MODE`). The run over a real folder with live Qwen extraction is the pilot's first task and is recorded here when it happens. | Pending real-folder run |

### Phase 1 — not started

Sequenced after pilot recruitment (section 12, week 4). The client/period
data model is designed in ADR 0005 so it lands as an additive change.

### Phase 2 — partly delivered with Phase 0

The Ask Tarazu pipeline of section 6 was built as part of moving the
assistant to the backend, because building the backend twice would have been
the more expensive route. Of the ten question types: top vendor, largest
expenses, expenses (as the ledger's payments), unmatched items, missing
evidence, duplicates, month comparison, and search by amount return computed
figures with sources today. **Sales and profit cannot be answered from a
payments ledger and the assistant says so** rather than guessing; they become
answerable once the Phase 1 normalized transactions table carries direction
(money in / money out). The "done when" criterion — all ten correct on the
demo case and one real case — therefore stays open until Phase 1.

### Phase 3 and Phase 4 — not started
