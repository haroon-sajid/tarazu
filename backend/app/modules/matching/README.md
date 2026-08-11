# modules/matching/

**Purpose:** Pure Python and pandas logic that deterministically matches
bank-statement transactions against invoices and ledger entries. The same input
always produces the same output. This module uses no AI.

**Inputs:** Structured extraction results (`app/shared/` schemas) with
provenance.

**Outputs:** Match results (matched, partial, or unmatched), each accompanied by
the exact deterministic rule that produced it, plus audit-trail entries. All
results are suggestions pending human approval or rejection.

**Public interface:** `service.py` only. Other modules import nothing else from
this package.

**Must never do:**

- **Never call an AI model and never import any AI client.** No LLMs, no embeddings, no "smart" fuzzy AI matching, ever.
- Never use nondeterministic logic, such as randomness or time-dependent behavior that affects results.
- Never auto-approve a match. Output is always a suggestion for human review.
- Never modify extracted values. This module reads them and reports matches only.
- Never apply fraud or red-flag rules; that is the job of `rules/`.
