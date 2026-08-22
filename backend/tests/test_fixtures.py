"""Every fixture must validate against the real schemas, and agree with itself.

These tests are the contract's tripwire. If someone edits a fixture into a shape
the backend cannot produce, the frontend would build against a lie — so the
fixtures are parsed through the same Pydantic models the API returns.
"""

from __future__ import annotations

import inspect
import json

import pytest
from pydantic import BaseModel

from app.api import fixtures
from app.shared import api as api_schemas
from app.shared import schemas
from app.shared.api import ReviewItemsResponse
from app.shared.schemas import (
    DashboardSummary,
    ExtractionResult,
    MatchStatus,
    ReviewDecision,
)

FIXTURE_FILES = ["review-items.json", "dashboard.json", "extraction-result.json"]


# --------------------------------------------------------------------------- #
# Each fixture validates against its schema
# --------------------------------------------------------------------------- #


def test_review_items_fixture_validates() -> None:
    payload = json.loads((fixtures.FIXTURES_DIR / "review-items.json").read_text("utf-8"))
    response = ReviewItemsResponse.model_validate(payload)
    assert response.total == len(response.items)
    assert response.items, "the review queue fixture must not be empty"


def test_dashboard_fixture_validates() -> None:
    payload = json.loads((fixtures.FIXTURES_DIR / "dashboard.json").read_text("utf-8"))
    DashboardSummary.model_validate(payload)


def test_extraction_result_fixture_validates() -> None:
    payload = json.loads((fixtures.FIXTURES_DIR / "extraction-result.json").read_text("utf-8"))
    result = ExtractionResult.model_validate(payload)
    assert result.fields, "an extraction result must carry at least one field"


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_fixture_file_exists_and_is_json(filename: str) -> None:
    path = fixtures.FIXTURES_DIR / filename
    assert path.is_file(), f"missing fixture: {path}"
    json.loads(path.read_text("utf-8"))


# --------------------------------------------------------------------------- #
# Reliability rule 3: provenance everywhere
# --------------------------------------------------------------------------- #


def test_every_extracted_value_has_provenance() -> None:
    """No extracted field may exist without a document and a usable locator."""
    for item in fixtures.review_items().items:
        for field in item.evidence:
            assert field.source.document_id
            assert field.source.page is not None or field.source.row_number is not None

    for field in fixtures.extraction_result().fields:
        assert field.source.document_id
        assert field.source.page is not None or field.source.row_number is not None


def test_second_opinion_disagreement_escalates_to_a_human() -> None:
    """Reliability rule: the AI never resolves its own disagreement."""
    result = fixtures.extraction_result()
    assert result.second_opinion is not None
    assert result.second_opinion.agrees is False
    assert result.second_opinion.disagreements
    assert result.needs_human_review is True


# --------------------------------------------------------------------------- #
# Extraction confidence and match strength stay separate
# --------------------------------------------------------------------------- #


def _models_defined_in(module) -> list[type[BaseModel]]:
    return [
        obj
        for _, obj in inspect.getmembers(module, inspect.isclass)
        if issubclass(obj, BaseModel) and obj.__module__ == module.__name__
    ]


def test_no_schema_has_a_bare_confidence_field() -> None:
    """`confidence` alone is ambiguous: AI reading, or deterministic match score?

    Collapsing the two would imply the AI scores matches, which it never does.
    The field is `extraction_confidence` on AI output and `match_strength` on
    deterministic output, and this test keeps it that way.
    """
    offenders = [
        f"{model.__name__}.confidence"
        for model in (*_models_defined_in(schemas), *_models_defined_in(api_schemas))
        if "confidence" in model.model_fields
    ]
    assert not offenders, f"ambiguous field name(s): {offenders}"


def _keys(node: object) -> set[str]:
    if isinstance(node, dict):
        found = set(node)
        for value in node.values():
            found |= _keys(value)
        return found
    if isinstance(node, list):
        found: set[str] = set()
        for value in node:
            found |= _keys(value)
        return found
    return set()


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_no_fixture_uses_a_bare_confidence_key(filename: str) -> None:
    payload = json.loads((fixtures.FIXTURES_DIR / filename).read_text("utf-8"))
    assert "confidence" not in _keys(payload)


def test_review_items_carry_both_confidence_and_strength() -> None:
    for item in fixtures.review_items().items:
        assert item.extraction_confidence is not None
        assert item.match.match_strength is not None


# --------------------------------------------------------------------------- #
# The fixtures agree with each other
# --------------------------------------------------------------------------- #


def test_dashboard_counts_match_the_review_queue() -> None:
    """A dashboard that disagrees with the queue would teach the frontend a lie."""
    items = fixtures.review_items().items
    summary = fixtures.dashboard()

    assert summary.total_review_items == len(items)
    assert summary.case_id == fixtures.review_items().case_id

    counted = {status: 0 for status in MatchStatus}
    for item in items:
        counted[item.match.status] += 1
    assert summary.match_status.matched == counted[MatchStatus.MATCHED]
    assert summary.match_status.partial == counted[MatchStatus.PARTIAL]
    assert summary.match_status.unmatched == counted[MatchStatus.UNMATCHED]

    decisions = {decision: 0 for decision in ReviewDecision}
    for item in items:
        decisions[item.decision] += 1
    assert summary.decisions.pending == decisions[ReviewDecision.PENDING]
    assert summary.decisions.approved == decisions[ReviewDecision.APPROVED]
    assert summary.decisions.rejected == decisions[ReviewDecision.REJECTED]

    confidences = {"high": 0, "medium": 0, "low": 0}
    for item in items:
        confidences[item.extraction_confidence.value] += 1
    assert summary.extraction_confidence.high == confidences["high"]
    assert summary.extraction_confidence.medium == confidences["medium"]
    assert summary.extraction_confidence.low == confidences["low"]


def test_dashboard_flag_counts_match_the_review_queue() -> None:
    items = fixtures.review_items().items
    summary = fixtures.dashboard()

    all_flags = [flag for item in items for flag in item.flags]
    assert summary.total_flags == len(all_flags)
    assert summary.flagged_item_count == sum(1 for item in items if item.flags)

    severities = {"high": 0, "medium": 0, "low": 0}
    for flag in all_flags:
        severities[flag.severity.value] += 1
    assert summary.flags_by_severity.high == severities["high"]
    assert summary.flags_by_severity.medium == severities["medium"]
    assert summary.flags_by_severity.low == severities["low"]


def test_benford_matches_the_ledger_amounts_in_the_queue() -> None:
    """Benford is arithmetic over the ledger, so it must reproduce exactly."""
    summary = fixtures.dashboard()
    assert summary.benford is not None

    observed = {digit: 0 for digit in range(1, 10)}
    for item in fixtures.review_items().items:
        digits = "".join(c for c in f"{item.ledger_entry.amount:f}" if c.isdigit()).lstrip("0")
        observed[int(digits[0])] += 1

    assert summary.benford.sample_size == sum(observed.values())
    for digit in summary.benford.digits:
        assert digit.observed_count == observed[digit.digit], f"digit {digit.digit}"


def test_dashboard_readiness_matches_what_the_metrics_compute() -> None:
    """The hand-written breakdown must be what the code actually produces."""
    from app.dashboard_metrics import audit_readiness

    assert fixtures.dashboard().audit_readiness_score == audit_readiness(
        fixtures.review_items().items
    )


def test_dashboard_confidence_sentence_matches_what_the_metrics_compute() -> None:
    from app.dashboard_metrics import data_confidence

    summary = fixtures.dashboard()
    assert summary.data_confidence == data_confidence(
        fixtures.review_items().items, summary.period_start, summary.period_end
    )


def test_dashboard_next_best_actions_match_what_the_metrics_compute() -> None:
    from app.dashboard_metrics import next_best_actions

    assert fixtures.dashboard().next_best_actions == next_best_actions(
        fixtures.review_items().items
    )


def test_extraction_fixture_backs_a_real_review_item() -> None:
    """The low-confidence extraction should be the evidence behind an actual row."""
    document_id = fixtures.extraction_result().document_id
    referenced = {
        field.source.document_id
        for item in fixtures.review_items().items
        for field in item.evidence
    }
    assert document_id in referenced
