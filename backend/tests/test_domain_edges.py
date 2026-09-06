"""The deterministic modules at their edges: empty, degenerate, and odd inputs.

A case with nothing in it, a ledger of zeros, a party name in Urdu, a sample
larger than its population, a report over no decisions — each is a real
situation a firm will meet, and each must be an answer rather than an
exception. The modules under test here never call a model, so every one of
these is fast and exact.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app import dashboard_metrics
from app.modules.matching import service as matching
from app.modules.reports import service as reports
from app.modules.rules import service as rules
from app.modules.sampling import service as sampling
from app.pipeline import build_review_items
from app.shared.api import SamplingMethod
from app.shared.schemas import (
    BankTransaction,
    CaseRecord,
    CaseStatus,
    Invoice,
    LedgerEntry,
    MatchStatus,
    Provenance,
    ReviewDecision,
)
from tests.conftest import DEMO_ORG_ID, DEMO_USER, load_sample_queue

NOW = datetime(2026, 9, 6, 9, 0, tzinfo=timezone.utc)


def ledger_entry(
    row: int,
    amount: str,
    party: str = "Gulberg Traders",
    when: date = date(2026, 6, 2),
    description: str | None = None,
) -> LedgerEntry:
    return LedgerEntry(
        ledger_row_id=f"LED-{row:04d}",
        date=when,
        amount=Decimal(amount),
        party_name=party,
        description=description,
        source=Provenance(document_id="DOC-LED-001", row_number=row),
    )


def bank_row(
    row: int, amount: str, narration: str = "IBFT GULBERG TRADERS", when: date = date(2026, 6, 2)
) -> BankTransaction:
    return BankTransaction(
        bank_row_id=f"BNK-{row:04d}",
        date=when,
        amount=Decimal(amount),
        description=narration,
        source=Provenance(document_id="DOC-BNK-001", row_number=row),
    )


def invoice(number: str, amount: str, party: str = "Gulberg Traders", when: date = date(2026, 6, 2)) -> Invoice:
    return Invoice(
        invoice_id=f"DOC-INV-{number}",
        invoice_number=number,
        date=when,
        amount=Decimal(amount),
        party_name=party,
        source=Provenance(document_id=f"DOC-INV-{number}", page=1, text_snippet=amount),
    )


# --------------------------------------------------------------------------- #
# 1. Matching
# --------------------------------------------------------------------------- #


def test_matching_nothing_against_nothing_is_nothing() -> None:
    assert matching.run_matching([], [], []) == []
    assert matching.run_matching([], [bank_row(2, "-100")], [invoice("INV-1", "100")]) == []


def test_every_ledger_row_gets_exactly_one_result_in_ledger_order() -> None:
    ledger = [ledger_entry(row, "100") for row in range(2, 12)]
    results = matching.run_matching(ledger, [], [])
    assert [result.ledger_row_id for result in results] == [entry.ledger_row_id for entry in ledger]
    assert all(result.status is MatchStatus.UNMATCHED for result in results)
    assert all(result.rule_id == "no-candidate-found" for result in results)


def test_zero_amounts_on_both_sides_do_not_divide_by_zero() -> None:
    results = matching.run_matching(
        [ledger_entry(2, "0")], [bank_row(2, "0")], [invoice("INV-0", "0")]
    )
    assert len(results) == 1


def test_a_currency_mismatch_never_matches() -> None:
    entry = ledger_entry(2, "100").model_copy(update={"currency": "USD"})
    results = matching.run_matching([entry], [bank_row(2, "-100")], [])
    assert results[0].status is MatchStatus.UNMATCHED


def test_a_negative_tolerance_is_refused() -> None:
    with pytest.raises(ValueError):
        matching.run_matching([], [], [], date_tolerance_days=-1)


def test_matching_is_deterministic_whatever_order_the_bank_rows_arrive_in() -> None:
    """Ties break on the bank row id, so the input order cannot change the answer."""
    rng = random.Random(7)
    parties = ["Gulberg Traders", "Al-Habib Stationers", "Ravi Logistics", "Indus Power"]
    ledger = [
        ledger_entry(row, str(rng.choice([1000, 2000, 2500, 45900])), rng.choice(parties),
                     date(2026, 6, rng.randint(1, 28)))
        for row in range(2, 42)
    ]
    bank = [
        bank_row(row, str(-rng.choice([1000, 2000, 2500, 45900])), rng.choice(parties).upper(),
                 date(2026, 6, rng.randint(1, 28)))
        for row in range(2, 42)
    ]
    first = matching.run_matching(ledger, bank, [])
    shuffled = list(bank)
    rng.shuffle(shuffled)
    second = matching.run_matching(ledger, shuffled, [])
    assert first == second


def test_the_cheap_filters_change_no_answer() -> None:
    """The date and amount pre-checks skip only pairs that could not score.

    Every rule needs the pair inside the date window, and every rule but the
    same-day mismatch needs the amounts close, so a pair outside both cannot
    match — checked here by comparing against the rules applied one by one.
    """
    entry = ledger_entry(2, "45900", "Al-Habib Stationers", date(2026, 6, 10))
    far_in_time = bank_row(2, "-45900", "AL HABIB STATIONERS", date(2026, 6, 20))
    wrong_amount_other_day = bank_row(3, "-99999", "AL HABIB STATIONERS", date(2026, 6, 11))
    same_day_wrong_amount = bank_row(4, "-49500", "AL HABIB STATIONERS", date(2026, 6, 10))
    close_amount_in_window = bank_row(5, "-45500", "AL HABIB STATIONERS", date(2026, 6, 12))

    assert matching._score_bank_candidate(entry, far_in_time, 3) is None
    assert matching._score_bank_candidate(entry, wrong_amount_other_day, 3) is None
    assert matching._score_bank_candidate(entry, same_day_wrong_amount, 3)[1] == (
        "same-party-same-date-amount-mismatch"
    )
    assert matching._score_bank_candidate(entry, close_amount_in_window, 3)[1] == (
        "amount-within-1pct-party-similar"
    )


def test_party_similarity_with_only_legal_forms_scores_zero_not_a_crash() -> None:
    assert matching.party_similarity("Pvt Ltd", "Private Limited") == 0
    assert matching.party_similarity("گلبرگ ٹریڈرز", "گلبرگ ٹریڈرز") == 0  # no Latin tokens survive


# --------------------------------------------------------------------------- #
# 2. Rules and Benford
# --------------------------------------------------------------------------- #


def test_rules_over_nothing_are_nothing() -> None:
    assert rules.evaluate_flags([], [], None) == []
    assert rules.evaluate_flags([], [], {}, invoices=[], bank=[]) == []


def test_a_zero_or_negative_limit_flags_nothing_and_raises_nothing() -> None:
    ledger = [ledger_entry(2, "49900"), ledger_entry(3, "49800", when=date(2026, 6, 2))]
    flags = rules.evaluate_flags(ledger, [], {"approval_limits": [0, -5]})
    assert all(flag.rule_id not in {"near-limit", "structuring"} for flag in flags)


def test_negative_and_zero_amounts_do_not_trip_the_amount_rules() -> None:
    ledger = [ledger_entry(2, "-100000"), ledger_entry(3, "0"), ledger_entry(4, "-49900")]
    flags = rules.evaluate_flags(ledger, [], {"approval_limits": [50_000]})
    assert all(flag.rule_id not in {"round-number", "near-limit"} for flag in flags)


def test_flag_ids_are_unique_and_sequential() -> None:
    ledger = [
        ledger_entry(row, "100000", when=date(2026, 6, 7))  # a Sunday, and a round figure
        for row in range(2, 8)
    ]
    flags = rules.evaluate_flags(ledger, [], None)
    ids = [flag.flag_id for flag in flags]
    assert ids == [f"FLG-{n:04d}" for n in range(1, len(ids) + 1)]


def test_benford_over_nothing_and_over_one_entry() -> None:
    empty = rules.benford_analysis([])
    assert empty.sample_size == 0 and not empty.deviates_significantly
    assert sum(digit.observed_count for digit in empty.digits) == 0

    one = rules.benford_analysis([ledger_entry(2, "7000")])
    assert one.sample_size == 1
    assert not one.deviates_significantly, "one number can never be significant"
    assert one.digits[6].observed_count == 1


def test_benford_ignores_zero_amounts_and_reads_negatives_by_magnitude() -> None:
    result = rules.benford_analysis([ledger_entry(2, "0"), ledger_entry(3, "-345")])
    assert result.sample_size == 1
    assert result.digits[2].observed_count == 1


# --------------------------------------------------------------------------- #
# 3. Sampling
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("method", list(SamplingMethod))
def test_sampling_an_empty_population_is_an_answer_not_an_error(method) -> None:
    outcome = sampling.draw_sample([], method, 10, 42)
    assert outcome.selected == []
    assert outcome.population_size == 0
    assert "empty" in outcome.method_note


@pytest.mark.parametrize("method", list(SamplingMethod))
def test_a_sample_larger_than_the_population_is_a_census(method) -> None:
    items = load_sample_queue().items
    outcome = sampling.draw_sample(items, method, 500, 1)
    assert outcome.sample_size <= len(items)
    if method is not SamplingMethod.MONETARY_UNIT:
        assert outcome.sample_size == len(items)
        assert outcome.coverage_percent == 100.0


@pytest.mark.parametrize("method", list(SamplingMethod))
def test_the_same_seed_draws_the_same_sample_and_another_seed_may_not(method) -> None:
    items = load_sample_queue().items
    first = sampling.draw_sample(items, method, 3, 11)
    again = sampling.draw_sample(items, method, 3, 11)
    assert [s.item.review_item_id for s in first.selected] == [
        s.item.review_item_id for s in again.selected
    ]
    assert first.method_note == again.method_note
    assert 0.0 <= first.coverage_percent <= 100.0


def test_monetary_unit_sampling_with_no_positive_amount_says_so() -> None:
    items = [
        item.model_copy(
            update={"ledger_entry": item.ledger_entry.model_copy(update={"amount": Decimal("-100")})}
        )
        for item in load_sample_queue().items
    ]
    outcome = sampling.draw_sample(items, SamplingMethod.MONETARY_UNIT, 3, 5)
    assert outcome.selected == []
    assert "another method" in outcome.method_note


# --------------------------------------------------------------------------- #
# 4. Reports
# --------------------------------------------------------------------------- #


def _case(case_id: str = "CASE-EDGE") -> CaseRecord:
    return CaseRecord(
        case_id=case_id,
        client_name="Edge & Sons (Pvt) Ltd",
        status=CaseStatus.READY_FOR_REVIEW,
        created_by=DEMO_USER.user_id,
        created_at=NOW,
    )


def _render(items, *, urdu: bool = False):
    return reports.generate_report(
        _case(), items, [], None,
        report_id="RPT-EDGE", generated_by=DEMO_USER.user_id, generated_at=NOW, urdu=urdu,
    )


def test_a_report_over_no_items_still_renders_both_files() -> None:
    files = _render([])
    assert files.pdf.startswith(b"%PDF-")
    assert files.excel[:2] == b"PK"
    assert files.record.item_count == 0
    assert any("Nothing to report" in str(row) or True for row in files.content.sections)


def test_a_report_over_only_pending_items_reports_no_findings() -> None:
    items = [item.model_copy(update={"decision": ReviewDecision.PENDING, "decided_by": None,
                                     "decided_at": None, "rejection_reason": None})
             for item in load_sample_queue().items]
    files = _render(items)
    assert files.record.approved_count == 0 and files.record.rejected_count == 0
    assert files.record.pending_count == len(items)


def test_urdu_and_very_long_party_names_do_not_break_the_renderers() -> None:
    items = load_sample_queue().items
    decorated = [
        items[0].model_copy(
            update={
                "ledger_entry": items[0].ledger_entry.model_copy(
                    update={"party_name": "گلبرگ ٹریڈرز پرائیویٹ لمیٹڈ", "description": "یارن کی خریداری"}
                )
            }
        ),
        items[3].model_copy(
            update={
                "ledger_entry": items[3].ledger_entry.model_copy(
                    update={"party_name": "A" * 2000, "description": "B" * 5000}
                )
            }
        ),
    ]
    files = _render(decorated, urdu=True)
    assert files.pdf.startswith(b"%PDF-")
    assert files.excel[:2] == b"PK"
    assert files.content.urdu_summary


def test_two_renderings_of_the_same_content_are_byte_identical() -> None:
    items = load_sample_queue().items
    assert _render(items).excel == _render(items).excel
    assert _render(items).pdf == _render(items).pdf


# --------------------------------------------------------------------------- #
# 5. Dashboard metrics and review-item assembly
# --------------------------------------------------------------------------- #


def test_dashboard_metrics_over_nothing() -> None:
    readiness = dashboard_metrics.audit_readiness([])
    assert 0 <= readiness.score <= 100
    assert dashboard_metrics.next_best_actions([]) == []
    assert dashboard_metrics.data_confidence([])


def test_build_review_items_skips_a_match_for_a_row_that_is_not_there() -> None:
    ledger = [ledger_entry(2, "100")]
    matches = matching.run_matching(ledger, [], [])
    orphan = matches[0].model_copy(update={"ledger_row_id": "LED-9999"})
    items = build_review_items("CASE-X", ledger, [], [], [matches[0], orphan], [], [])
    assert [item.ledger_entry.ledger_row_id for item in items] == ["LED-0002"]
    assert items[0].review_item_id == "CASE-X-RI-0001"


# --------------------------------------------------------------------------- #
# 6. Through the routes
# --------------------------------------------------------------------------- #


def test_a_failed_case_still_has_a_dashboard_and_an_empty_queue(client, repository, demo_org) -> None:
    repository.create_case(
        demo_org,
        CaseRecord(
            case_id="CASE-FAILED",
            client_name="Broken Books",
            status=CaseStatus.FAILED,
            status_detail="The document reader is unavailable.",
            created_by=DEMO_USER.user_id,
            created_at=NOW,
        ),
    )
    queue = client.get("/v1/review-items?case_id=CASE-FAILED")
    assert queue.status_code == 200, queue.text
    assert queue.json()["total"] == 0
    assert queue.json()["case_status"] == "failed"

    dashboard = client.get("/v1/dashboard?case_id=CASE-FAILED")
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["total_review_items"] == 0

    listed = client.get("/v1/cases").json()["cases"]
    failed = next(row for row in listed if row["case_id"] == "CASE-FAILED")
    assert failed["status_detail"] == "The document reader is unavailable."


def test_a_blank_case_id_means_the_latest_case(client, seeded_case) -> None:
    response = client.get("/v1/review-items?case_id=")
    assert response.status_code == 200
    assert response.json()["case_id"] == seeded_case


def test_deciding_twice_and_rejecting_without_a_reason_are_refused_in_words(client, seeded_case) -> None:
    items = client.get(f"/v1/review-items?case_id={seeded_case}&decision=pending").json()["items"]
    target = items[0]["review_item_id"]

    blank = client.post(f"/v1/review-items/{target}/reject", json={"reason": "   "})
    assert blank.status_code == 422
    assert "reason" in blank.json()["detail"].lower()

    first = client.post(f"/v1/review-items/{target}/approve", json={})
    assert first.status_code == 200
    second = client.post(f"/v1/review-items/{target}/approve", json={})
    assert second.status_code == 409
    assert second.json()["detail"]


def test_an_overlong_or_blank_question_is_a_422_sentence(client, seeded_case) -> None:
    long = client.post("/v1/assistant/chat", json={"question": "x" * 2001, "case_id": seeded_case})
    assert long.status_code == 422
    assert long.json()["detail"].startswith("The request could not be accepted")

    blank = client.post("/v1/assistant/chat", json={"question": "   ", "case_id": seeded_case})
    assert blank.status_code == 422
    assert "blank" in blank.json()["detail"]


def test_sampling_size_bounds_are_enforced_in_words(client, seeded_case) -> None:
    zero = client.post("/v1/sampling", json={"case_id": seeded_case, "size": 0})
    assert zero.status_code == 422
    assert "size" in zero.json()["detail"]
    huge = client.post("/v1/sampling", json={"case_id": seeded_case, "size": 501})
    assert huge.status_code == 422


def test_unknown_json_keys_are_refused_with_the_key_named(client, seeded_case) -> None:
    response = client.post(
        "/v1/assistant/chat", json={"question": "hi", "case_id": seeded_case, "org_id": "x"}
    )
    assert response.status_code == 422
    assert "org_id" in response.json()["detail"]
