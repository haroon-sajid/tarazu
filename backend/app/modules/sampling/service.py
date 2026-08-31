"""Public interface of the sampling module.

This is the only file other modules may import from `modules/sampling/`.

Substantive testing, done the way a working paper has to be able to describe it:
draw a subset of the population and say exactly how it was drawn. Everything
here is plain Python and `Decimal`. This module must never import an AI client —
a sample a model picked is a sample nobody can reproduce or defend, and a
selection is a numeric result, which belongs to deterministic code (reliability
rule 2).

Three methods, because auditors use three:

- ``RANDOM``        every item equally likely, without replacement. The honest
                    choice when the population is homogeneous and the question
                    is about the population as a whole.
- ``MONETARY_UNIT`` probability proportional to size. The standard substantive
                    method: it tests the money rather than the rows, so an item
                    bigger than the sampling interval cannot be missed.
- ``HIGH_VALUE``    the largest amounts, in order. Targeted, judgemental, and
                    **not statistical** — `method_note` says so out loud,
                    because presenting a judgemental pick as a statistical
                    sample would misrepresent the work in the file.

**Determinism is the contract.** The same `(items, method, size, seed)` always
produces the same sample. A sample that cannot be reproduced six months later,
when somebody asks how these twenty items were chosen, is not audit evidence.
That is why the seed is an input rather than an implementation detail, and why
the population is sorted into a fixed order before anything is drawn: the
caller's list order must not be able to change the answer.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from decimal import Decimal

from app.shared.api import SamplingMethod
from app.shared.schemas import ReviewItem

__all__ = [
    "SampleOutcome",
    "SelectedItem",
    "draw_sample",
]


# --------------------------------------------------------------------------- #
# What a draw produces
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SelectedItem:
    """One item in the sample, and the one-line reason it is there.

    The reason travels with the item rather than being reconstructed later, so
    that the working paper can show, row by row, why this row was tested: the
    monetary unit that landed on it, its rank by amount, or the seed that chose
    it. "It was in the sample" is not a reason; this is.
    """

    item: ReviewItem
    reason: str

    @property
    def amount(self) -> Decimal:
        return self.item.ledger_entry.amount


@dataclass(frozen=True)
class SampleOutcome:
    """A drawn sample and everything needed to defend or reproduce it.

    Pure data. Nothing here is decided, approved, or persisted: a sample says
    which items a human should look at, and the human still looks.
    """

    method: SamplingMethod
    #: The seed actually used. Always populated, so the draw can be repeated.
    seed: int
    selected: list[SelectedItem] = field(default_factory=list)
    population_size: int = 0
    population_total: Decimal = Decimal("0")
    sample_total: Decimal = Decimal("0")
    #: Share of the population's money the sample covers, 0-100.
    coverage_percent: float = 0.0
    #: How the sample was drawn, in the words that belong in a working paper.
    method_note: str = ""

    @property
    def sample_size(self) -> int:
        return len(self.selected)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _amount(value: Decimal) -> str:
    """Money as a working paper prints it. Never a float — see reliability rule 2."""
    return f"{value:,.2f}"


def _ordered(items: list[ReviewItem]) -> list[ReviewItem]:
    """Put the population in one fixed order before anything is drawn.

    Date then id: the order an auditor would list the population in anyway, and
    unique because `review_item_id` is. Sorting here is what makes the draw
    independent of however the caller happened to hand the rows over — two
    callers with the same population and the same seed must get the same sample,
    even if one of them read the rows back in a different order.
    """
    return sorted(items, key=lambda i: (i.ledger_entry.date, i.review_item_id))


def _total(items: list[ReviewItem]) -> Decimal:
    return sum((i.ledger_entry.amount for i in items), Decimal("0"))


def _coverage(sample_total: Decimal, population_total: Decimal) -> float:
    """Share of the population's value in the sample, as a percentage.

    Clamped to 0-100. A population that nets off (credits against debits) can
    otherwise put the selected amounts above the net total, and a coverage
    figure over 100% would read as an error rather than as the arithmetic of a
    mixed-sign population.
    """
    if population_total == 0:
        return 0.0
    percent = float(round(sample_total / population_total * 100, 2))
    return min(100.0, max(0.0, percent))


def _census(
    ordered: list[ReviewItem], reason: str
) -> list[SelectedItem]:
    """Select every item. Used when the requested size covers the population."""
    return [SelectedItem(item=item, reason=reason) for item in ordered]


# --------------------------------------------------------------------------- #
# The three methods
# --------------------------------------------------------------------------- #


def _draw_random(
    ordered: list[ReviewItem], size: int, seed: int
) -> tuple[list[SelectedItem], str]:
    """Simple random selection without replacement.

    Every item has the same chance of selection, whatever it is worth. That is
    the method's virtue and its limitation: it says something about the
    population's rows and very little about its money, since a population where
    one item is 90% of the value will usually not include that item.

    `random.Random(seed)` is seeded per call and never shared, so the draw is a
    function of its arguments alone. Nothing here reads the global RNG, whose
    state depends on whatever else the process has done.
    """
    population_size = len(ordered)
    if size >= population_size:
        note = (
            f"Random selection of all {population_size} items: the requested sample "
            f"size of {size} is at or above the population, so the whole population "
            "was tested and no selection was needed. 100% coverage."
        )
        return _census(ordered, f"whole population tested, seed {seed}"), note

    rng = random.Random(seed)
    chosen = set(rng.sample(range(population_size), size))
    selected = [
        SelectedItem(item=item, reason=f"random selection, seed {seed}")
        for position, item in enumerate(ordered)
        if position in chosen
    ]
    note = (
        f"Random selection of {size} items from a population of {population_size}, "
        f"drawn without replacement with a seeded pseudo-random generator "
        f"(seed {seed}). Every item had an equal chance of selection regardless of "
        "amount. Re-running this draw with the same seed over the same population "
        "reproduces this sample exactly."
    )
    return selected, note


def _draw_monetary_unit(
    ordered: list[ReviewItem], size: int, seed: int
) -> tuple[list[SelectedItem], str]:
    """Systematic monetary-unit (probability-proportional-to-size) sampling.

    The sampling unit is one rupee, not one row. Lay the population's amounts
    end to end, take an interval of ``population value / size``, start at a
    random point inside the first interval, and select whichever item each
    subsequent step lands inside. An item's chance of selection is therefore
    proportional to its amount.

    **An item larger than the sampling interval is certain to be selected.**
    That property is the whole point of the method: the steps are exactly one
    interval apart, so any stretch of the number line as long as the interval
    contains one, and an item that occupies such a stretch cannot be stepped
    over. It is what lets an auditor say the large items were all tested without
    having to abandon statistical selection to do it.

    Items with a zero or negative amount are excluded. Monetary-unit sampling
    draws from money, and they contribute none: a zero-amount row occupies no
    stretch of the line and can never be landed on, and a credit would run the
    cumulative total backwards and corrupt every later interval. Excluding them
    is a documented limitation of the method, not a silent filter — the note
    below says how many were left out, so a population of credits is visible
    rather than quietly untested.
    """
    population_size = len(ordered)
    eligible = [item for item in ordered if item.ledger_entry.amount > 0]
    excluded = population_size - len(eligible)
    excluded_note = (
        ""
        if excluded == 0
        else (
            f" {excluded} item(s) with a zero or negative amount were excluded: "
            "monetary-unit sampling draws from money and they contribute none."
        )
    )

    if not eligible:
        note = (
            f"No monetary-unit sample could be drawn: none of the {population_size} "
            "items in the population has a positive amount, so there is no money to "
            "sample. Test this population by another method."
        )
        return [], note

    eligible_total = _total(eligible)

    if size >= len(eligible):
        note = (
            f"Monetary-unit selection of all {len(eligible)} items with a positive "
            f"amount: the requested sample size of {size} is at or above that "
            f"population, so the whole population with a positive amount was "
            f"tested and no interval was needed.{excluded_note}"
        )
        return _census(eligible, f"whole population tested, seed {seed}"), note

    interval = eligible_total / Decimal(size)
    rng = random.Random(seed)
    # A random start inside the first interval. Derived from the seeded RNG and
    # converted through `str` so the Decimal is exact and the same seed always
    # produces the same start.
    start = interval * Decimal(str(rng.random()))

    hits: dict[int, list[Decimal]] = {}
    position = 0
    cumulative = Decimal("0")
    for step in range(size):
        point = start + interval * step
        while position < len(eligible) - 1 and cumulative + eligible[position].ledger_entry.amount <= point:
            cumulative += eligible[position].ledger_entry.amount
            position += 1
        hits.setdefault(position, []).append(point)

    selected: list[SelectedItem] = []
    for index in sorted(hits):
        item = eligible[index]
        points = hits[index]
        units = ", ".join(_amount(point) for point in points)
        if len(points) == 1:
            reason = (
                f"monetary-unit selection: amount {_amount(item.ledger_entry.amount)}, "
                f"hit at monetary unit {units}"
            )
        else:
            reason = (
                f"monetary-unit selection: amount {_amount(item.ledger_entry.amount)}, "
                f"hit at monetary units {units} ({len(points)} hits — the amount "
                f"exceeds the sampling interval of {_amount(interval)}, so its "
                "selection was certain)"
            )
        selected.append(SelectedItem(item=item, reason=reason))

    note = (
        f"Monetary-unit (probability-proportional-to-size) selection from a "
        f"population of {population_size} items worth {_amount(eligible_total)}. The "
        f"population was placed in date order, its amounts accumulated, and "
        f"{size} systematic selections taken one sampling interval of "
        f"{_amount(interval)} apart (population value / {size}) from a random start "
        f"of {_amount(start)} within the first interval, seeded with {seed}. Every "
        f"item larger than the interval is therefore certain to be selected; an "
        f"item hit more than once appears once, with its hits recorded. "
        f"{len(selected)} distinct items were selected."
        f"{excluded_note} Re-running this draw with the same seed over the same "
        "population reproduces this sample exactly."
    )
    return selected, note


def _draw_high_value(
    ordered: list[ReviewItem], size: int, seed: int
) -> tuple[list[SelectedItem], str]:
    """The `size` largest amounts, descending. Judgemental, not statistical.

    Auditors do this constantly and it is perfectly legitimate work — the
    largest items carry the most misstatement, and testing them is often the
    fastest route to comfort. What it is not is a sample: the items were chosen
    *because* they are large, so nothing observed in them can be projected over
    the items that were not chosen. `method_note` says exactly that, because a
    working paper that lets a reader mistake this for statistical selection has
    overstated the evidence obtained.

    Ties break on `review_item_id`, so two equal amounts always rank the same
    way. The seed is not used and is recorded only so every response can be
    replayed by the same call.
    """
    population_size = len(ordered)
    ranked = sorted(
        ordered,
        key=lambda i: (-i.ledger_entry.amount, i.review_item_id),
    )
    taken = ranked[:size]
    selected = [
        SelectedItem(
            item=item,
            reason=(
                f"rank {rank} of {population_size} by amount: "
                f"{_amount(item.ledger_entry.amount)}"
            ),
        )
        for rank, item in enumerate(taken, start=1)
    ]

    judgement = (
        "This is a judgemental (targeted) selection, not a statistical sample: the "
        "items were chosen because they are large, so no conclusion drawn from them "
        "may be projected over the items that were not selected."
    )
    if size >= population_size:
        note = (
            f"All {population_size} items, in descending amount order: the requested "
            f"size of {size} is at or above the population, so the whole population "
            f"was tested. 100% coverage. {judgement}"
        )
    else:
        note = (
            f"The {len(selected)} largest amounts in a population of "
            f"{population_size}, in descending order. {judgement}"
        )
    return selected, note


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #


_DRAWERS = {
    SamplingMethod.RANDOM: _draw_random,
    SamplingMethod.MONETARY_UNIT: _draw_monetary_unit,
    SamplingMethod.HIGH_VALUE: _draw_high_value,
}


def draw_sample(
    items: list[ReviewItem],
    method: SamplingMethod,
    size: int,
    seed: int,
) -> SampleOutcome:
    """Draw a sample from a case's population and say how it was drawn.

    Args:
        items: The population — the case's review queue. Order does not matter;
            the population is sorted into a fixed order first, so the same rows
            always give the same sample.
        method: Which selection method to use. See the module docstring.
        size: How many items to select. A size at or above the population
            returns the whole population, which is a census rather than a
            sample, and the note says so.
        seed: The reproducibility handle. Required, never optional here — the
            caller decides whether it was given by the auditor or generated for
            them, but by the time the draw happens there is always one on
            record.

    Returns:
        A `SampleOutcome`: the selected items each with their reason, the
        population and sample totals as `Decimal`, the coverage percentage, and
        a `method_note` written for a working paper.

    An empty population returns an empty sample with a note saying so. It is a
    real answer — this case has nothing to test — and not an error to raise at a
    caller who asked a reasonable question.
    """
    ordered = _ordered(items)
    population_size = len(ordered)
    population_total = _total(ordered)

    if population_size == 0:
        return SampleOutcome(
            method=method,
            seed=seed,
            method_note=(
                "No sample drawn: the population is empty. There is nothing to test "
                "in this case yet."
            ),
        )

    selected, note = _DRAWERS[method](ordered, size, seed)
    sample_total = sum((s.amount for s in selected), Decimal("0"))
    coverage = _coverage(sample_total, population_total)

    return SampleOutcome(
        method=method,
        seed=seed,
        selected=selected,
        population_size=population_size,
        population_total=population_total,
        sample_total=sample_total,
        coverage_percent=coverage,
        method_note=(
            f"{note} The sample covers {coverage}% of the population's value "
            f"({_amount(sample_total)} of {_amount(population_total)})."
        ),
    )
