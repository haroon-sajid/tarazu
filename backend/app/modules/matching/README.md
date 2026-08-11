# modules/matching/

**Purpose:** Pure Python + pandas logic that deterministically matches
bank-statement transactions ↔ invoices ↔ ledger entries. Same input always
produces the same output. ZERO AI.

**Inputs:** Structured extraction results (`app/shared/` schemas) with provenance.
**Outputs:** Match results (matched / partial / unmatched) with the exact
deterministic rule that produced each match, plus audit-trail entries.
All results are suggestions pending human approve/reject.

**Public interface:** `service.py` only — other modules import nothing else from here.

**Must NEVER do:**
- **Never call an AI model. Never import any AI client. No LLM, no embeddings, no "smart" fuzzy AI matching — ever.**
- Never use nondeterministic logic (randomness, time-dependent behavior affecting results).
- Never auto-approve a match — output is always a suggestion for human review.
- Never modify extracted values; it reads them and reports matches only.
- Never apply fraud/red-flag rules — that is `rules/`'s job.
