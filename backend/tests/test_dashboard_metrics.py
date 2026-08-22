"""Readiness, the data-confidence sentence, and next best actions.

All three are pure functions of the review queue, so these tests build queues by
hand and assert exact numbers and exact wording. Nothing here mocks anything:
there is nothing to mock, which is the point of keeping them deterministic.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.dashboard_metrics import (
    audit_readiness,
    data_confidence,
    next_best_actions,
)
from app.shared.schemas import (
    BankTransaction,
    Confidence,
    ExtractedField,
    Flag,
    LedgerEntry,
    MatchResult,
    MatchStatus,
    MatchStrength,
    Provenance,
    ReviewDecision,
    ReviewItem,
    Severity,
)


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def an_item(
    number: int,
    *,
    status: MatchStatus = MatchStatus.MATCHED,
    decision: ReviewDecision = ReviewDecision.PENDING,
    flags: list[Flag] | None = None,
    party: str = "Gulberg Traders (Pvt) Ltd",
    amount: str = "100000",
    when: date = date(2026, 6, 2),
    description: str | None = "Yarn purchase",
    account_code: str | None = "5010",
    evidence: list[ExtractedField] | None = None,
) -> ReviewItem:
    ledger_row_id = f"LED-{number:04d}"
    decided = decision is not ReviewDecision.PENDING

    # A matched or partial result must reference an attached counterpart; the
    # schema refuses one that does not. Unmatched must reference nothing.
    transaction = None
    bank_row_id = None
    if status is not MatchStatus.UNMATCHED:
        bank_row_id = f"BNK-{number:04d}"
        transaction = BankTransaction(
            bank_row_id=bank_row_id,
            date=when,
            amount=Decimal(amount),
            description=f"PAYMENT {party}",
            source=Provenance(
                document_id="DOC-BNK-001", page=1, text_snippet=str(amount)
            ),
        )

    return ReviewItem(
        review_item_id=f"RI-{number:04d}",
        case_id="CASE-TEST",
        ledger_entry=LedgerEntry(
            ledger_row_id=ledger_row_id,
            date=when,
            amount=Decimal(amount),
            party_name=party,
            description=description,
            account_code=account_code,
            source=Provenance(document_id="DOC-LED-001", row_number=number + 1),
        ),
        bank_transaction=transaction,
        match=MatchResult(
            ledger_row_id=ledger_row_id,
            bank_row_id=bank_row_id,
            status=status,
            match_strength=MatchStrength.HIGH,
            reason="Test fixture.",
            rule_id="test",
        ),
        flags=flags or [],
        extraction_confidence=Confidence.HIGH,
        evidence=evidence or [],
        decision=decision,
        decided_by="user-1" if decided else None,
        decided_at=datetime.now(timezone.utc) if decided else None,
        rejection_reason="Wrong amount." if decision is ReviewDecision.REJECTED else None,
    )


def a_flag(
    flag_id: str,
    rule_id: str,
    severity: Severity,
    source_row_id: str,
    related: list[str] | None = None,
) -> Flag:
    return Flag(
        flag_id=flag_id,
        rule_id=rule_id,
        severity=severity,
        explanation=f"{rule_id} fired.",
        source_row_id=source_row_id,
        related_row_ids=related or [],
    )


def an_unreadable_field() -> ExtractedField:
    return ExtractedField(
        field="amount",
        value=None,
        extraction_confidence=Confidence.LOW,
        source=Provenance(document_id="DOC-INV-1", page=1, text_snippet="smudged"),
        unreadable=True,
    )


# --------------------------------------------------------------------------- #
# 1. Audit readiness
# --------------------------------------------------------------------------- #


def test_a_perfect_case_scores_100() -> None:
    items = [an_item(n) for n in range(1, 5)]
    readiness = audit_readiness(items)

    assert readiness.score == 100
    assert readiness.matched.percent == 100.0
    assert readiness.completeness.percent == 100.0
    # No flags at all means nothing outstanding, not zero credit.
    assert readiness.flags_reviewed == readiness.flags_reviewed.of(0, 0)
    assert readiness.flags_reviewed.percent == 100.0


def test_matched_percent_counts_only_confirmed_matches() -> None:
    """A partial match is not reconciled, and readiness should say so."""
    items = [
        an_item(1, status=MatchStatus.MATCHED),
        an_item(2, status=MatchStatus.MATCHED),
        an_item(3, status=MatchStatus.PARTIAL),
        an_item(4, status=MatchStatus.UNMATCHED),
    ]
    readiness = audit_readiness(items)

    assert readiness.matched.count == 2
    assert readiness.matched.total == 4
    assert readiness.matched.percent == 50.0


def test_flags_are_reviewed_when_their_item_is_decided() -> None:
    items = [
        an_item(1, decision=ReviewDecision.APPROVED,
                flags=[a_flag("F1", "round-number", Severity.LOW, "LED-0001")]),
        an_item(2, flags=[
            a_flag("F2", "structuring", Severity.HIGH, "LED-0002"),
            a_flag("F3", "near-limit", Severity.HIGH, "LED-0002"),
        ]),
    ]
    readiness = audit_readiness(items)

    assert readiness.flags_reviewed.count == 1
    assert readiness.flags_reviewed.total == 3
    assert readiness.flags_reviewed.percent == 33.3


def test_a_blank_ledger_field_makes_a_row_incomplete() -> None:
    items = [an_item(1), an_item(2, account_code=None), an_item(3, description="   ")]
    readiness = audit_readiness(items)

    assert readiness.completeness.count == 1
    assert readiness.completeness.total == 3


def test_an_unreadable_extraction_makes_a_row_incomplete() -> None:
    """A missing amount is missing whether the cell was empty or the scan was."""
    items = [an_item(1), an_item(2, evidence=[an_unreadable_field()])]
    readiness = audit_readiness(items)

    assert readiness.completeness.count == 1
    assert readiness.completeness.total == 2


def test_the_score_is_the_mean_of_the_three_components() -> None:
    items = [
        an_item(1, status=MatchStatus.MATCHED,
                flags=[a_flag("F1", "round-number", Severity.LOW, "LED-0001")]),
        an_item(2, status=MatchStatus.UNMATCHED, account_code=None),
    ]
    readiness = audit_readiness(items)

    assert readiness.matched.percent == 50.0
    assert readiness.flags_reviewed.percent == 0.0
    assert readiness.completeness.percent == 50.0
    assert readiness.score == round((50.0 + 0.0 + 50.0) / 3)


def test_an_empty_case_scores_zero_without_dividing_by_zero() -> None:
    readiness = audit_readiness([])
    assert readiness.score == 0
    assert readiness.matched.total == 0


def test_readiness_is_deterministic() -> None:
    items = [an_item(n, status=MatchStatus.PARTIAL if n % 2 else MatchStatus.MATCHED)
             for n in range(1, 8)]
    assert audit_readiness(items) == audit_readiness(list(reversed(items)))


def test_the_component_counts_are_shown_so_a_human_can_check_them() -> None:
    items = [an_item(1), an_item(2, status=MatchStatus.UNMATCHED)]
    matched = audit_readiness(items).matched
    assert (matched.count, matched.total, matched.percent) == (1, 2, 50.0)


def test_a_component_cannot_claim_a_percent_its_counts_do_not_support() -> None:
    """The schema refuses a hand-written breakdown that does not add up."""
    from app.shared.schemas import ReadinessComponent

    with pytest.raises(ValueError, match="does not follow from"):
        ReadinessComponent(percent=99.0, count=1, total=10)


# --------------------------------------------------------------------------- #
# 2. Data confidence
# --------------------------------------------------------------------------- #


def test_the_sentence_names_the_period_and_what_is_outstanding() -> None:
    items = [an_item(1)] + [an_item(n, status=MatchStatus.UNMATCHED) for n in (2, 3, 4)]
    sentence = data_confidence(items, date(2026, 6, 1), date(2026, 6, 30))
    assert sentence == "Based on 1 month of data, 3 unmatched items remain."


def test_one_outstanding_item_reads_as_singular() -> None:
    items = [an_item(1), an_item(2, status=MatchStatus.UNMATCHED)]
    sentence = data_confidence(items, date(2026, 6, 1), date(2026, 6, 30))
    assert sentence == "Based on 1 month of data, 1 unmatched item remains."


def test_a_clean_case_says_so_rather_than_reporting_zero() -> None:
    items = [an_item(1), an_item(2)]
    sentence = data_confidence(items, date(2026, 6, 1), date(2026, 6, 30))
    assert sentence == "Based on 1 month of data, every ledger row has supporting evidence."


def test_partial_matches_are_reported_alongside_unmatched() -> None:
    items = [
        an_item(1, status=MatchStatus.UNMATCHED),
        an_item(2, status=MatchStatus.PARTIAL),
    ]
    sentence = data_confidence(items, date(2026, 6, 1), date(2026, 6, 30))
    assert sentence == (
        "Based on 1 month of data, 1 unmatched item and 1 partial match remain."
    )


def test_several_partial_matches_are_pluralised_correctly() -> None:
    items = [an_item(n, status=MatchStatus.PARTIAL) for n in (1, 2)]
    sentence = data_confidence(items, date(2026, 6, 1), date(2026, 6, 30))
    assert sentence == "Based on 1 month of data, 2 partial matches remain."


@pytest.mark.parametrize(
    "start,end,expected",
    [
        (date(2026, 6, 1), date(2026, 6, 3), "3 days"),
        (date(2026, 6, 1), date(2026, 6, 1), "1 day"),
        (date(2026, 6, 1), date(2026, 6, 14), "2 weeks"),
        (date(2026, 6, 1), date(2026, 6, 30), "1 month"),
        (date(2026, 4, 1), date(2026, 6, 30), "3 months"),
    ],
)
def test_the_period_is_described_in_a_unit_a_person_would_use(
    start: date, end: date, expected: str
) -> None:
    sentence = data_confidence([an_item(1)], start, end)
    assert sentence.startswith(f"Based on {expected} of data,")


def test_without_a_period_it_falls_back_to_the_row_count() -> None:
    sentence = data_confidence([an_item(1), an_item(2)], None, None)
    assert sentence.startswith("Based on 2 ledger rows,")


def test_an_empty_case_says_what_to_do_next() -> None:
    assert data_confidence([]) == (
        "No data yet. Upload a bank statement, invoices, and a ledger to begin."
    )


def test_the_sentence_never_characterises_the_data_as_reliable() -> None:
    """It states what is there. The auditor draws the conclusion."""
    sentence = data_confidence([an_item(1)], date(2026, 6, 1), date(2026, 6, 30)).lower()
    for word in ("reliable", "unreliable", "trustworthy", "accurate", "confident"):
        assert word not in sentence


# --------------------------------------------------------------------------- #
# 3. Next best actions
# --------------------------------------------------------------------------- #


def test_actions_are_severity_ordered_high_first() -> None:
    items = [
        an_item(1, flags=[a_flag("F1", "round-number", Severity.LOW, "LED-0001")]),
        an_item(2, flags=[a_flag("F2", "weekend-entry", Severity.MEDIUM, "LED-0002")]),
        an_item(3, flags=[a_flag("F3", "structuring", Severity.HIGH, "LED-0003")]),
    ]
    actions = next_best_actions(items)
    assert [action.severity for action in actions] == [
        Severity.HIGH,
        Severity.MEDIUM,
        Severity.LOW,
    ]


def test_a_flag_is_reworded_as_something_to_go_and_do() -> None:
    items = [
        an_item(1, party="Hussain Brothers & Sons",
                flags=[a_flag("F1", "structuring", Severity.HIGH, "LED-0001")])
    ]
    action = next_best_actions(items)[0]

    assert action.action == "Review the structuring flag on Hussain Brothers & Sons"
    assert action.severity is Severity.HIGH
    assert action.rule_id == "structuring"
    assert action.party_name == "Hussain Brothers & Sons"
    # The action links to its row, so the UI can make it clickable.
    assert action.review_item_id == "RI-0001"


def test_an_unknown_rule_still_produces_a_readable_action() -> None:
    """`rules/` is owned by someone else and will grow rules this file has not met."""
    items = [an_item(1, party="Ravi Logistics",
                     flags=[a_flag("F1", "benford-outlier", Severity.HIGH, "LED-0001")])]
    action = next_best_actions(items)[0]
    assert action.action == "Review the benford outlier flag on Ravi Logistics"


def test_decided_items_do_not_appear_in_the_action_list() -> None:
    """An action telling you to review what you already approved is noise."""
    items = [
        an_item(1, decision=ReviewDecision.APPROVED,
                flags=[a_flag("F1", "structuring", Severity.HIGH, "LED-0001")]),
        an_item(2, decision=ReviewDecision.REJECTED,
                flags=[a_flag("F2", "near-limit", Severity.HIGH, "LED-0002")]),
        an_item(3, flags=[a_flag("F3", "round-number", Severity.LOW, "LED-0003")]),
    ]
    actions = next_best_actions(items)
    assert [action.rule_id for action in actions] == ["round-number"]


def test_a_flag_spanning_two_rows_produces_one_action_not_two() -> None:
    """Structuring fires once per row involved; one issue is one piece of work."""
    items = [
        an_item(1, party="Hussain Brothers & Sons", flags=[
            a_flag("F1", "structuring", Severity.HIGH, "LED-0001", ["LED-0002"])
        ]),
        an_item(2, party="Hussain Brothers & Sons", flags=[
            a_flag("F2", "structuring", Severity.HIGH, "LED-0002", ["LED-0001"])
        ]),
    ]
    actions = next_best_actions(items)
    assert len(actions) == 1
    assert actions[0].rule_id == "structuring"


def test_same_rule_on_unrelated_rows_stays_two_actions() -> None:
    items = [
        an_item(1, flags=[a_flag("F1", "near-limit", Severity.HIGH, "LED-0001")]),
        an_item(2, flags=[a_flag("F2", "near-limit", Severity.HIGH, "LED-0002")]),
    ]
    assert len(next_best_actions(items)) == 2


def test_equally_severe_flags_are_ordered_by_amount_largest_first() -> None:
    items = [
        an_item(1, amount="10000", party="Small Vendor",
                flags=[a_flag("F1", "near-limit", Severity.HIGH, "LED-0001")]),
        an_item(2, amount="900000", party="Large Vendor",
                flags=[a_flag("F2", "near-limit", Severity.HIGH, "LED-0002")]),
    ]
    actions = next_best_actions(items)
    assert [action.party_name for action in actions] == ["Large Vendor", "Small Vendor"]


def test_at_most_five_actions_are_returned() -> None:
    items = [
        an_item(n, amount=str(1000 * n),
                flags=[a_flag(f"F{n}", "near-limit", Severity.HIGH, f"LED-{n:04d}")])
        for n in range(1, 12)
    ]
    assert len(next_best_actions(items)) == 5


def test_the_limit_is_adjustable() -> None:
    items = [
        an_item(n, flags=[a_flag(f"F{n}", "near-limit", Severity.HIGH, f"LED-{n:04d}")])
        for n in range(1, 5)
    ]
    assert len(next_best_actions(items, limit=2)) == 2


def test_no_flags_means_no_actions() -> None:
    assert next_best_actions([an_item(1), an_item(2)]) == []


def test_actions_are_deterministic() -> None:
    items = [
        an_item(n, amount="50000",
                flags=[a_flag(f"F{n}", "near-limit", Severity.HIGH, f"LED-{n:04d}")])
        for n in range(1, 9)
    ]
    assert next_best_actions(items) == next_best_actions(items)


def test_no_metric_depends_on_an_ai_output() -> None:
    """Changing extraction confidence must not move any of the three figures."""
    base = [an_item(1), an_item(2, status=MatchStatus.UNMATCHED)]
    shifted = [
        item.model_copy(update={"extraction_confidence": Confidence.LOW}) for item in base
    ]

    assert audit_readiness(base) == audit_readiness(shifted)
    assert data_confidence(base) == data_confidence(shifted)
    assert next_best_actions(base) == next_best_actions(shifted)
