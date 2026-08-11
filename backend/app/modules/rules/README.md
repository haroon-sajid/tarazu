# modules/rules/

**Purpose:** Deterministic red-flag rules applied to transactions and matches.
Initial rules: suspiciously round numbers, duplicate payments, weekend/holiday
entries, amounts just under approval limits. Every rule is plain, testable Python.
ZERO AI.

**Inputs:** Extracted transactions and match results (`app/shared/` schemas); rule
configuration (e.g. approval-limit thresholds).
**Outputs:** Flags, each with: the rule id that fired, the evidence (source
provenance), and severity. All flags are suggestions pending human approve/reject.
Writes flag events to the immutable audit trail.

**Public interface:** `service.py` only — other modules import nothing else from here.

**Must NEVER do:**
- **Never call an AI model. Never import any AI client — rules are deterministic code only.**
- Never auto-reject or auto-approve a transaction; flags are for human review.
- Never hide or suppress a fired rule based on heuristics.
- Never perform matching (→ `matching/`) or extraction (→ `extraction/`).
- Never explain flags in natural language via AI — plain-language explanations are `assistant/`'s job, built on this module's structured output.
