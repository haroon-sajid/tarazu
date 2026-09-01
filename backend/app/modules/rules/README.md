# modules/rules/

**Purpose:** Deterministic red-flag rules applied to transactions and matches,
and the Benford first-digit analysis. Every rule is plain, testable Python.
This module uses no AI.

**Inputs:** Extracted transactions and match results (`app/shared/` schemas),
plus rule configuration such as approval-limit thresholds.

**Outputs:** Flags, each carrying the rule id that fired, the evidence (source
provenance), and a severity. All flags are suggestions pending human approval or
rejection. Writes flag events to the immutable audit trail.

**Public interface:** `service.py` only. Other modules import nothing else from
this package.

## The rules

Emitted in this order, numbered `FLG-0001…` within the case.

| `rule_id` | Fires when | Severity |
|---|---|---|
| `round-number` | the amount is a whole multiple of 1,000 and at or above `round_number_floor` | low |
| `weekend-entry` | the ledger date is a Saturday or Sunday (`weekend_days`) | medium |
| `duplicate-invoice` | one invoice is matched to two or more ledger rows | high |
| `duplicate-payment` | the same party received the same amount within `duplicate_window_days` | high |
| `near-limit` | the amount sits within `near_limit_tolerance` (2%) below an approval limit | high |
| `structuring` | two or more payments to one party on one day, each under a limit, summing to it or over | high |
| `invoice-sequence-gap` | a vendor's invoice numbers skip values among the uploaded documents | medium |

Flags that span rows (`duplicate-*`, `structuring`) fire once per row involved
and name the others in `related_row_ids`. A same-day pair of equal payments to
one party can legitimately fire both `duplicate-payment` and `structuring`:
they are two hypotheses, and neither is suppressed in favour of the other.

## Configuration

`evaluate_flags(ledger, matches, config, *, invoices=None, bank=None)` takes a
dictionary with these keys, each falling back to `DEFAULT_CONFIG`:

| Key | Default | Environment override |
|---|---|---|
| `approval_limits` | `[50000, 100000, 500000]` | `RULES_APPROVAL_LIMITS` (comma-separated) |
| `round_number_floor` | `10000` | `RULES_ROUND_NUMBER_FLOOR` |
| `duplicate_window_days` | `3` | `RULES_DUPLICATE_WINDOW_DAYS` |
| `near_limit_tolerance` | `0.02` | `RULES_NEAR_LIMIT_THRESHOLD` |
| `weekend_days` | `[5, 6]` (Sat, Sun) | - |

`default_config()` reads the overrides; the pipeline calls it once at import.
Per-client configuration replaces the environment when clients exist (ADR 0005).

## Benford

`benford_analysis(ledger)` counts the leading digit of every non-zero amount
and compares the distribution with `log10(1 + 1/d)`, reporting a chi-square
statistic on 8 degrees of freedom. `deviates_significantly` is true only when
the statistic exceeds the p = 0.05 critical value (15.507) **and** the sample
has at least 25 amounts; below that the test is indicative and the result
says so by never calling it significant.

**Must never do:**

- **Never call an AI model and never import any AI client.** Rules are deterministic code only. `test_rules.py` checks the imports.
- Never auto-approve or auto-reject a transaction. Flags exist for human review.
- Never hide or suppress a fired rule based on heuristics.
- Never perform matching (that belongs to `matching/`) or extraction (that belongs to `extraction/`).
- Never explain flags in natural language via AI. Plain-language explanations are the job of `assistant/`, built on this module's structured output.
