"""Audit sampling: the module's arithmetic, its determinism, and the route.

The module is tested directly — it is a pure function, so most of what matters
about it can be proved without a database — and then through the route, which is
where tenancy and the audit trail live.

The property these tests exist for is reproducibility. A sample that cannot be
drawn again is not audit evidence, so "the same seed gives the same sample" is
asserted first and asserted at both levels.
"""

from __future__ import annotations

import ast
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.sampling import service as sampling
from app.modules.sampling.service import SampleOutcome, draw_sample
from app.shared.api import SamplingMethod
from app.shared.schemas import (
    Confidence,
    LedgerEntry,
    MatchResult,
    MatchStatus,
    MatchStrength,
    Provenance,
    ReviewItem,
)


# --------------------------------------------------------------------------- #
# Population builders
# --------------------------------------------------------------------------- #


def item(number: int, amount: str, *, when: date | None = None) -> ReviewItem:
    """One unmatched review item worth `amount`. Enough for sampling to work on."""
    ledger_row_id = f"LED-{number:04d}"
    return ReviewItem(
        review_item_id=f"RI-{number:04d}",
        case_id="CASE-TEST",
        ledger_entry=LedgerEntry(
            ledger_row_id=ledger_row_id,
            date=when or (date(2026, 6, 1) + timedelta(days=number)),
            amount=Decimal(amount),
            party_name=f"Vendor {number}",
            source=Provenance(document_id="DOC-LED-001", row_number=number + 1),
        ),
        match=MatchResult(
            ledger_row_id=ledger_row_id,
            status=MatchStatus.UNMATCHED,
            match_strength=MatchStrength.LOW,
            reason="Test fixture.",
            rule_id="test",
        ),
        extraction_confidence=Confidence.HIGH,
    )


def population(count: int, *, base: int = 1000) -> list[ReviewItem]:
    """A population of `count` items with varied, positive amounts."""
    return [item(n, str(base + n * 137)) for n in range(1, count + 1)]


def ids(outcome: SampleOutcome) -> list[str]:
    return [selected.item.review_item_id for selected in outcome.selected]


# --------------------------------------------------------------------------- #
# Determinism — the contract
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("method", list(SamplingMethod))
def test_the_same_seed_always_draws_the_same_sample(method: SamplingMethod) -> None:
    items = population(60)
    first = draw_sample(items, method, 10, 4242)
    second = draw_sample(items, method, 10, 4242)

    assert ids(first) == ids(second)
    assert first.sample_total == second.sample_total
    assert first.method_note == second.method_note


@pytest.mark.parametrize(
    "method", [SamplingMethod.RANDOM, SamplingMethod.MONETARY_UNIT]
)
def test_a_different_seed_draws_a_different_sample(method: SamplingMethod) -> None:
    """10 of 60 — the chance of two seeds agreeing by luck is vanishing."""
    items = population(60)
    assert ids(draw_sample(items, method, 10, 1)) != ids(
        draw_sample(items, method, 10, 999_999)
    )


def test_the_caller_s_list_order_cannot_change_the_sample() -> None:
    """Two callers with the same rows and seed must get the same sample."""
    items = population(40)
    shuffled = list(reversed(items))
    for method in SamplingMethod:
        assert ids(draw_sample(items, method, 8, 7)) == ids(
            draw_sample(shuffled, method, 8, 7)
        )


def test_high_value_ignores_the_seed_because_amounts_fix_the_selection() -> None:
    items = population(30)
    assert ids(draw_sample(items, SamplingMethod.HIGH_VALUE, 5, 1)) == ids(
        draw_sample(items, SamplingMethod.HIGH_VALUE, 5, 2)
    )


# --------------------------------------------------------------------------- #
# Monetary-unit sampling
# --------------------------------------------------------------------------- #


def test_monetary_unit_selects_every_item_larger_than_the_interval() -> None:
    """The property the method exists for: a big item cannot be stepped over.

    Nine small items and one that dwarfs them. Whatever the seed, the large one
    is longer than the sampling interval, so some selection point must land in
    it.
    """
    items = [item(n, "1000") for n in range(1, 10)] + [item(99, "500000")]
    total = sum(i.ledger_entry.amount for i in items)

    for seed in range(25):
        outcome = draw_sample(items, SamplingMethod.MONETARY_UNIT, 5, seed)
        interval = total / Decimal(5)
        certain = [
            i.review_item_id for i in items if i.ledger_entry.amount > interval
        ]
        assert certain, "the fixture must contain an item above the interval"
        for review_item_id in certain:
            assert review_item_id in ids(outcome), (
                f"seed {seed} stepped over {review_item_id}, which is larger "
                "than the sampling interval"
            )


def test_monetary_unit_reports_a_repeatedly_hit_item_once() -> None:
    """One item worth most of the population is hit several times, listed once."""
    items = [item(n, "100") for n in range(1, 6)] + [item(99, "900000")]
    outcome = draw_sample(items, SamplingMethod.MONETARY_UNIT, 3, 11)

    assert ids(outcome) == sorted(set(ids(outcome)))
    big = next(s for s in outcome.selected if s.item.review_item_id == "RI-0099")
    assert "hits" in big.reason
    assert "900,000.00" in big.reason


def test_monetary_unit_excludes_zero_and_negative_amounts() -> None:
    items = [item(1, "1000"), item(2, "0"), item(3, "-5000"), item(4, "2000")]
    outcome = draw_sample(items, SamplingMethod.MONETARY_UNIT, 2, 3)

    assert "RI-0002" not in ids(outcome)
    assert "RI-0003" not in ids(outcome)
    assert "excluded" in outcome.method_note


def test_monetary_unit_with_no_positive_amounts_says_so() -> None:
    outcome = draw_sample(
        [item(1, "0"), item(2, "-100")], SamplingMethod.MONETARY_UNIT, 3, 5
    )
    assert outcome.selected == []
    assert "no money to sample" in outcome.method_note


def test_the_monetary_unit_note_names_the_interval_and_the_seed() -> None:
    outcome = draw_sample(population(20), SamplingMethod.MONETARY_UNIT, 4, 8080)
    assert "probability-proportional-to-size" in outcome.method_note
    assert "sampling interval" in outcome.method_note
    assert "seeded with 8080" in outcome.method_note


# --------------------------------------------------------------------------- #
# High value
# --------------------------------------------------------------------------- #


def test_high_value_returns_the_largest_n_in_descending_order() -> None:
    items = [item(1, "100"), item(2, "900"), item(3, "500"), item(4, "700")]
    outcome = draw_sample(items, SamplingMethod.HIGH_VALUE, 3, 1)

    assert ids(outcome) == ["RI-0002", "RI-0004", "RI-0003"]
    assert [s.amount for s in outcome.selected] == [
        Decimal("900"),
        Decimal("700"),
        Decimal("500"),
    ]
    assert outcome.selected[0].reason.startswith("rank 1 of 4 by amount")


def test_high_value_never_claims_to_be_a_statistical_sample() -> None:
    """A working paper must not let a reader mistake this for selection at random."""
    outcome = draw_sample(population(20), SamplingMethod.HIGH_VALUE, 5, 1)
    assert "not a statistical sample" in outcome.method_note
    assert "projected" in outcome.method_note


# --------------------------------------------------------------------------- #
# Coverage and edges
# --------------------------------------------------------------------------- #


def test_coverage_percent_is_the_sample_s_share_of_the_population_s_value() -> None:
    items = [item(1, "100"), item(2, "200"), item(3, "300"), item(4, "400")]
    outcome = draw_sample(items, SamplingMethod.HIGH_VALUE, 2, 1)

    assert outcome.population_total == Decimal("1000")
    assert outcome.sample_total == Decimal("700")
    assert outcome.coverage_percent == 70.0
    assert "70.0% of the population's value" in outcome.method_note


def test_totals_stay_decimal_and_never_become_floats() -> None:
    """Money is never a float here (reliability rule 2)."""
    outcome = draw_sample(population(12), SamplingMethod.RANDOM, 4, 1)
    assert isinstance(outcome.population_total, Decimal)
    assert isinstance(outcome.sample_total, Decimal)


@pytest.mark.parametrize("method", list(SamplingMethod))
def test_a_size_at_or_above_the_population_returns_everything(
    method: SamplingMethod,
) -> None:
    items = population(6)
    outcome = draw_sample(items, method, 6, 1)
    assert sorted(ids(outcome)) == sorted(i.review_item_id for i in items)
    assert outcome.coverage_percent == 100.0

    bigger = draw_sample(items, method, 50, 1)
    assert sorted(ids(bigger)) == sorted(i.review_item_id for i in items)
    assert "whole population" in bigger.method_note


@pytest.mark.parametrize("method", list(SamplingMethod))
def test_an_empty_population_returns_an_empty_sample_not_an_error(
    method: SamplingMethod,
) -> None:
    outcome = draw_sample([], method, 10, 1)
    assert outcome.selected == []
    assert outcome.population_size == 0
    assert outcome.population_total == Decimal("0")
    assert outcome.coverage_percent == 0.0
    assert "population is empty" in outcome.method_note


@pytest.mark.parametrize("method", list(SamplingMethod))
def test_every_selected_item_carries_a_reason(method: SamplingMethod) -> None:
    outcome = draw_sample(population(30), method, 6, 2026)
    assert len(outcome.selected) == 6
    for selected in outcome.selected:
        assert selected.reason.strip()


def test_a_random_sample_s_reason_names_the_seed() -> None:
    outcome = draw_sample(population(30), SamplingMethod.RANDOM, 5, 77)
    assert all(s.reason == "random selection, seed 77" for s in outcome.selected)


# --------------------------------------------------------------------------- #
# The route
# --------------------------------------------------------------------------- #


def test_the_route_draws_a_sample_and_records_it(client, seeded_case: str) -> None:
    response = client.post(
        "/v1/sampling",
        json={"case_id": seeded_case, "method": "monetary_unit", "size": 3, "seed": 42},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["case_id"] == seeded_case
    assert body["method"] == "monetary_unit"
    assert body["seed"] == 42
    assert body["population_size"] == 10
    assert body["sample_size"] == len(body["items"]) <= 3
    assert body["audit_record"]["action"] == "sample_drawn"
    assert "seed 42" in body["audit_record"]["detail"]
    assert "monetary_unit" in body["audit_record"]["detail"]

    trail = client.get(f"/v1/audit-trail?case_id={seeded_case}").json()
    assert any(record["action"] == "sample_drawn" for record in trail["records"])


def test_the_route_generates_and_returns_a_seed_when_none_is_given(
    client, seeded_case: str
) -> None:
    """Without a returned seed the auditor could never repeat the draw."""
    first = client.post(
        "/v1/sampling", json={"case_id": seeded_case, "method": "random", "size": 4}
    ).json()
    assert isinstance(first["seed"], int)

    repeated = client.post(
        "/v1/sampling",
        json={
            "case_id": seeded_case,
            "method": "random",
            "size": 4,
            "seed": first["seed"],
        },
    ).json()
    assert [i["review_item_id"] for i in repeated["items"]] == [
        i["review_item_id"] for i in first["items"]
    ]


def test_the_route_formats_money_as_plain_strings(client, seeded_case: str) -> None:
    body = client.post(
        "/v1/sampling",
        json={"case_id": seeded_case, "method": "high_value", "size": 2, "seed": 1},
    ).json()

    assert body["items"][0]["amount"] == "1,500,000.00"
    assert body["items"][0]["currency"] == "PKR"
    assert body["items"][0]["match_status"] == "matched"
    assert body["population_amount"] == "2,685,830.00"
    assert 0.0 <= body["coverage_percent"] <= 100.0
    assert "not a statistical sample" in body["method_note"]


def test_the_route_defaults_to_the_caller_s_most_recent_case(
    client, seeded_case: str
) -> None:
    body = client.post("/v1/sampling", json={}).json()
    assert body["case_id"] == seeded_case
    assert body["method"] == "monetary_unit"


def test_another_firm_cannot_sample_this_firm_s_case(
    other_client, seeded_case: str
) -> None:
    """Firm B asking for firm A's case is a 404: it does not exist for them."""
    response = other_client.post(
        "/v1/sampling", json={"case_id": seeded_case, "method": "random", "size": 3}
    )
    assert response.status_code == 404
    assert seeded_case in response.json()["detail"]


def test_sampling_requires_a_caller(anonymous_client, seeded_case: str) -> None:
    response = anonymous_client.post(
        "/v1/sampling", json={"case_id": seeded_case, "size": 3}
    )
    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# The boundary
# --------------------------------------------------------------------------- #


def test_the_sampling_module_imports_no_ai_client() -> None:
    """Selection is a numeric result; no model may touch it (reliability rule 2)."""
    forbidden = {"httpx", "openai", "dashscope", "anthropic", "requests"}
    package = Path(sampling.__file__).parent
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                root = name.split(".")[0]
                assert root not in forbidden, f"{path.name} imports {name}"
                assert not name.startswith("app.api"), f"{path.name} imports {name}"
                assert not name.startswith("app.core"), f"{path.name} imports {name}"
                assert not name.startswith("app.modules"), f"{path.name} imports {name}"
