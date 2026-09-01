# modules/sampling/

**Purpose:** Deterministic audit sampling: substantive testing's first step.
Draw a defensible subset of a case's population and state exactly how it was
drawn, in the words a working paper needs. Every selection is plain, testable
Python over `Decimal`. This module uses no AI.

**Inputs:** The case's population as `list[ReviewItem]` (`app/shared/schemas.py`),
a `SamplingMethod`, a sample size, and a seed.

**Outputs:** A `SampleOutcome`: the selected items, each with a one-line reason
it was selected; the population size and total; the sample total; the coverage
percentage; and a `method_note` describing the draw. Pure data: the module
persists nothing, writes no trail, and decides nothing. Every selected item goes
to a human for review exactly like any other item.

**Public interface:** `service.py` only, one function, `draw_sample(items,
method, size, seed) -> SampleOutcome`. Other modules import nothing else from
this package.

## The methods

| `method` | Selects | Statistical? |
|---|---|---|
| `random` | every item equally likely, without replacement, from `random.Random(seed)` | yes |
| `monetary_unit` | probability proportional to amount, by systematic monetary-unit sampling | yes |
| `high_value` | the `size` largest amounts, descending | **no, judgemental** |

**`random`** says something about the population's rows and little about its
money: a population where one item is 90% of the value will usually not include
that item.

**`monetary_unit`** (MUS, probability-proportional-to-size) is the standard
substantive method. The sampling unit is one rupee, not one row: lay the
amounts end to end, take an interval of `population value / size`, start at a
random point inside the first interval, and select whichever item each
subsequent step lands in. **An item larger than the interval is certain to be
selected**: the steps are exactly one interval apart, so no stretch of the line
that long can be stepped over. That is the property the method exists for. An
item hit more than once is reported once, with its hits named in its reason.
Items with a zero or negative amount are excluded: MUS draws from money and they
contribute none, and a credit would run the cumulative total backwards and
corrupt every later interval. The `method_note` says how many were excluded, so
an untested tail of credits is visible rather than silently dropped.

**`high_value`** is targeted work an auditor does constantly and is perfectly
legitimate, but it is not a sample, because the items were chosen *because*
they are large. Nothing observed in them may be projected over the items that
were not selected, and the `method_note` says so in as many words.

## Rules that hold for every method

- **`Decimal` throughout.** Money is never a float (reliability rule 2).
- **The same `(items, method, size, seed)` always gives the same sample.** The
  population is sorted into a fixed order (date, then `review_item_id`) before
  anything is drawn, so the caller's list order cannot change the answer, and
  `random.Random(seed)` is seeded per call and never shared with the global RNG.
- `size` at or above the population returns the whole population; the note calls
  it a census rather than a sample.
- An empty population returns an empty sample with a valid note, not an error.
- Coverage is clamped to 0–100%: a population that nets off can otherwise put
  the selected amounts above the net total.

## Where the trail is written

`api/sampling.py`, not here. The route records `AuditAction.SAMPLE_DRAWN` with
the method, size, seed, and coverage, because a sample nobody can trace to who
drew it and how is not audit evidence. The module stays a pure function so it
can be tested, replayed, and reasoned about without a database.

**Must never do:**

- **Never call an AI model and never import any AI client.** Selection is a
  numeric result and belongs to deterministic code. `test_sampling.py` checks
  the imports.
- Never import from `app.api`, `app.core`, or another module's internals. Only
  `app/shared/` and the standard library.
- Never read or write the repository, storage, or the audit trail. No I/O at all.
- Never decide anything about a selected item. A sample nominates work for a
  human; approval and rejection stay where they always are (reliability rule 1).
- Never draw a sample that cannot be reproduced. If a source of randomness is
  not seeded, it does not belong in this module.
- Never describe `high_value` as a statistical sample, and never project a
  conclusion from it over the population.
