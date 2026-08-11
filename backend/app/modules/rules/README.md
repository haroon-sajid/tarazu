# modules/rules/

**Purpose:** Deterministic red-flag rules applied to transactions and matches.
The initial rules cover suspiciously round numbers, duplicate payments, weekend
and holiday entries, and amounts just under approval limits. Every rule is
plain, testable Python. This module uses no AI.

**Inputs:** Extracted transactions and match results (`app/shared/` schemas),
plus rule configuration such as approval-limit thresholds.

**Outputs:** Flags, each carrying the rule id that fired, the evidence (source
provenance), and a severity. All flags are suggestions pending human approval or
rejection. Writes flag events to the immutable audit trail.

**Public interface:** `service.py` only. Other modules import nothing else from
this package.

**Must never do:**

- **Never call an AI model and never import any AI client.** Rules are deterministic code only.
- Never auto-approve or auto-reject a transaction. Flags exist for human review.
- Never hide or suppress a fired rule based on heuristics.
- Never perform matching (that belongs to `matching/`) or extraction (that belongs to `extraction/`).
- Never explain flags in natural language via AI. Plain-language explanations are the job of `assistant/`, built on this module's structured output.
