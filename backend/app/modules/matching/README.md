# modules/matching/

**Purpose:** Pure Python and pandas logic that deterministically matches
bank-statement transactions against invoices and ledger entries. The same input
always produces the same output, in the same order, whatever order the rows
arrived in. This module uses no AI.

**Inputs:** Structured extraction results (`app/shared/` schemas) with
provenance.

**Outputs:** Match results (matched, partial, or unmatched), each accompanied by
the exact deterministic rule that produced it, plus audit-trail entries. All
results are suggestions pending human approval or rejection.

**Public interface:** `service.py` only. Other modules import nothing else from
this package.

## How it works

Every ledger row is compared against the bank statement and the invoices, and
the strongest evidence decides the result.

| Tier | Condition | Result | `rule_id` |
|---|---|---|---|
| 1 | Exact amount, same date, party similarity ≥ 85 | matched / high | `exact-amount-exact-date` |
| 2 | Exact amount, date within the tolerance window (3 days) | matched / medium | `exact-amount-date-within-3-days` |
| 3 | Amount within 1%, party ≥ 70, date within window | partial / low | `amount-within-1pct-party-similar` |
| 4 | Party ≥ 85, same date, amount differs (transpositions are named) | partial / low | `same-party-same-date-amount-mismatch` |
| - | No bank line; an invoice agrees on amount and party | partial / medium | `invoice-only-no-bank-payment` |
| - | No bank line; an invoice within 1% | partial / low | `invoice-only-amount-mismatch` |
| - | Nothing | unmatched / low | `no-candidate-found` |

- **Bank matching is one-to-one.** Every candidate pair across the case is
  ranked (tier, date gap, similarity, then the rows' own ids) and assigned
  best-first, so a strong pair is never robbed of its line by a weaker one
  that came earlier in the file, and two identical lines pair the same way on
  every run.
- **Invoice matching is not exclusive.** Two ledger rows pointing at one
  invoice both keep it; that is what `rules/` raises as `duplicate-invoice`.
  An invoice is found by amount and party, or by its number appearing in the
  ledger description, within a 60-day look-back.
- **Party similarity** is `rapidfuzz.fuzz.token_set_ratio` over names
  normalised by `app.shared.text.normalise_party_name` (case, punctuation,
  and legal suffixes removed), so a narration's extra tokens ("IBFT", a cheque
  number) do not count against it.
- Amounts compare on absolute value; currencies must agree.

The tolerance window is a keyword argument (`date_tolerance_days`), so a
client whose bank clears slowly can be matched more generously without a code
change.

**Must never do:**

- **Never call an AI model and never import any AI client.** No LLMs, no embeddings, no "smart" fuzzy AI matching, ever. `test_matching.py` checks the imports.
- Never use nondeterministic logic, such as randomness or time-dependent behavior that affects results.
- Never auto-approve a match. Output is always a suggestion for human review.
- Never modify extracted values. This module reads them and reports matches only.
- Never apply fraud or red-flag rules; that is the job of `rules/`.
