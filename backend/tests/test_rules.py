"""The red-flag rules and the Benford analysis.

Each rule gets a row that should fire it, a row that should not, and a check on
the wording an auditor will read. The Benford test reproduces the sample
dashboard's digit counts from the same ten amounts.
"""

from __future__ import annotations

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.api import fixtures
from app.modules.rules import service as rules
from app.modules.rules.service import (
    BENFORD_MIN_SAMPLE,
    DEFAULT_CONFIG,
    RULE_IDS,
    benford_analysis,
    default_config,
    evaluate_flags,
)
from app.shared.schemas import (
    Invoice,
    LedgerEntry,
    MatchResult,
    MatchStatus,
    MatchStrength,
    Provenance,
    Severity,
)


def ledger(
    row_id: str, amount: str, party: str, when: date = date(2026, 6, 2)
) -> LedgerEntry:
    return LedgerEntry(
        ledger_row_id=row_id,
        date=when,
        amount=Decimal(amount),
        party_name=party,
        source=Provenance(document_id="DOC-LED-001", row_number=int(row_id[-2:]) + 1),
    )


def matched(entry: LedgerEntry, invoice_id: str | None = None) -> MatchResult:
    return MatchResult(
        ledger_row_id=entry.ledger_row_id,
        bank_row_id=f"BNK-{entry.ledger_row_id[-2:]}",
        invoice_id=invoice_id,
        status=MatchStatus.MATCHED,
        match_strength=MatchStrength.HIGH,
        reason="Test.",
        rule_id="exact-amount-exact-date",
    )


def invoice(invoice_id: str, number: str, amount: str, party: str) -> Invoice:
    return Invoice(
        invoice_id=invoice_id,
        invoice_number=number,
        date=date(2026, 6, 1),
        amount=Decimal(amount),
        party_name=party,
        source=Provenance(document_id=invoice_id, page=1, text_snippet=number),
    )


def fired(flags, rule_id: str):
    return [flag for flag in flags if flag.rule_id == rule_id]


# --------------------------------------------------------------------------- #
# Individual rules
# --------------------------------------------------------------------------- #


def test_a_large_round_amount_is_a_low_severity_flag() -> None:
    rows = [
        ledger("LED-01", "1500000", "Indus Power Solutions"),
        ledger("LED-02", "1500001", "Indus Power Solutions"),
        ledger("LED-03", "5000", "Small Vendor"),   # below the floor
        ledger("LED-04", "49500", "Hussain Brothers"),
    ]
    flags = fired(evaluate_flags(rows, [], DEFAULT_CONFIG), "round-number")
    assert [flag.source_row_id for flag in flags] == ["LED-01"]
    assert flags[0].severity is Severity.LOW
    assert flags[0].explanation.startswith("1,500,000.00 is an exactly round figure.")


def test_a_weekend_posting_is_a_medium_severity_flag() -> None:
    rows = [
        ledger("LED-01", "12345", "Vendor", date(2026, 6, 14)),  # Sunday
        ledger("LED-02", "12345", "Vendor", date(2026, 6, 13)),  # Saturday
        ledger("LED-03", "12345", "Vendor", date(2026, 6, 15)),  # Monday
    ]
    flags = fired(evaluate_flags(rows, [], DEFAULT_CONFIG), "weekend-entry")
    assert [flag.source_row_id for flag in flags] == ["LED-01", "LED-02"]
    assert flags[0].severity is Severity.MEDIUM
    assert flags[0].explanation.startswith("Posted on Sunday 2026-06-14.")


def test_one_invoice_matched_twice_is_a_duplicate_invoice_on_both_rows() -> None:
    rows = [
        ledger("LED-07", "96400", "Karachi Packaging Co.", date(2026, 6, 5)),
        ledger("LED-23", "96400", "Karachi Packaging Co.", date(2026, 6, 16)),
    ]
    matches = [matched(rows[0], "DOC-INV-0087"), matched(rows[1], "DOC-INV-0087")]
    invoices = [invoice("DOC-INV-0087", "INV-2026-0087", "96400", "Karachi Packaging Co.")]

    flags = fired(evaluate_flags(rows, matches, DEFAULT_CONFIG, invoices=invoices),
                  "duplicate-invoice")
    assert {flag.source_row_id for flag in flags} == {"LED-07", "LED-23"}
    assert flags[0].related_row_ids == ["LED-23"]
    assert flags[0].severity is Severity.HIGH
    assert flags[0].explanation == (
        "Invoice INV-2026-0087 is paid 2 times: once on 2026-06-05 and again on "
        "2026-06-16, 11 days apart."
    )
    # The evidence points at the invoice itself.
    assert flags[0].source is not None and flags[0].source.document_id == "DOC-INV-0087"


def test_the_same_party_and_amount_within_the_window_is_a_duplicate_payment() -> None:
    rows = [
        ledger("LED-01", "25000", "Ravi Logistics", date(2026, 6, 8)),
        ledger("LED-02", "25000", "RAVI LOGISTICS PVT LTD", date(2026, 6, 10)),
        ledger("LED-03", "25000", "Ravi Logistics", date(2026, 6, 25)),  # too far apart
    ]
    flags = fired(evaluate_flags(rows, [], DEFAULT_CONFIG), "duplicate-payment")
    assert {flag.source_row_id for flag in flags} == {"LED-01", "LED-02"}
    assert all(flag.severity is Severity.HIGH for flag in flags)
    assert "25,000.00" in flags[0].explanation and "LED-02" in flags[0].explanation


def test_an_amount_just_under_an_approval_limit_is_near_limit() -> None:
    rows = [
        ledger("LED-01", "49500", "Hussain Brothers"),   # 1% under 50,000
        ledger("LED-02", "48000", "Hussain Brothers"),   # 4% under: not near
        ledger("LED-03", "50000", "Hussain Brothers"),   # at the limit, not under
        ledger("LED-04", "99000", "Big Vendor"),         # 1% under 100,000
    ]
    flags = fired(evaluate_flags(rows, [], DEFAULT_CONFIG), "near-limit")
    assert [flag.source_row_id for flag in flags] == ["LED-01", "LED-04"]
    assert flags[0].explanation == "49,500.00 sits 1.0% below the 50,000 approval limit."
    assert flags[1].explanation == "99,000.00 sits 1.0% below the 100,000 approval limit."


def test_splitting_a_payment_under_a_limit_is_structuring_on_every_row() -> None:
    rows = [
        ledger("LED-14", "49500", "Hussain Brothers & Sons", date(2026, 6, 11)),
        ledger("LED-15", "49500", "Hussain Brothers & Sons", date(2026, 6, 11)),
        ledger("LED-16", "20000", "Hussain Brothers & Sons", date(2026, 6, 12)),
    ]
    flags = fired(evaluate_flags(rows, [], DEFAULT_CONFIG), "structuring")
    assert {flag.source_row_id for flag in flags} == {"LED-14", "LED-15"}
    assert flags[0].related_row_ids == ["LED-15"]
    assert flags[0].explanation == (
        "2 payments to Hussain Brothers & Sons on 2026-06-11, each below the 50,000 "
        "approval limit, total 99,000.00. Splitting a payment to stay under an "
        "approval limit is a structuring pattern."
    )


def test_two_small_payments_that_stay_under_every_limit_are_not_structuring() -> None:
    rows = [
        ledger("LED-01", "10000", "Vendor", date(2026, 6, 11)),
        ledger("LED-02", "12000", "Vendor", date(2026, 6, 11)),
    ]
    assert fired(evaluate_flags(rows, [], DEFAULT_CONFIG), "structuring") == []


def test_a_gap_in_a_vendors_invoice_numbers_is_flagged_once() -> None:
    rows = [
        ledger("LED-01", "1000", "Sialkot Metal Works", date(2026, 6, 5)),
        ledger("LED-02", "2000", "Sialkot Metal Works", date(2026, 6, 20)),
    ]
    matches = [matched(rows[0], "DOC-INV-0431"), matched(rows[1], "DOC-INV-0435")]
    invoices = [
        invoice("DOC-INV-0431", "SMW/2026/0431", "1000", "Sialkot Metal Works"),
        invoice("DOC-INV-0435", "SMW/2026/0435", "2000", "Sialkot Metal Works"),
    ]
    flags = fired(evaluate_flags(rows, matches, DEFAULT_CONFIG, invoices=invoices),
                  "invoice-sequence-gap")
    assert len(flags) == 1
    assert flags[0].source_row_id == "LED-01"
    assert flags[0].related_row_ids == ["LED-02"]
    assert flags[0].severity is Severity.MEDIUM
    assert "jump from SMW/2026/0431 to SMW/2026/0435: 3 numbers" in flags[0].explanation


def test_consecutive_invoice_numbers_are_not_a_gap() -> None:
    rows = [ledger("LED-01", "1000", "V"), ledger("LED-02", "2000", "V")]
    matches = [matched(rows[0], "I-1"), matched(rows[1], "I-2")]
    invoices = [invoice("I-1", "V-100", "1000", "V"), invoice("I-2", "V-101", "2000", "V")]
    assert fired(evaluate_flags(rows, matches, DEFAULT_CONFIG, invoices=invoices),
                 "invoice-sequence-gap") == []


# --------------------------------------------------------------------------- #
# Whole-set properties
# --------------------------------------------------------------------------- #


def test_flag_ids_are_numbered_in_emission_order_and_unique() -> None:
    rows = [
        ledger("LED-01", "1500000", "Indus Power", date(2026, 6, 14)),
        ledger("LED-02", "49500", "Hussain Brothers", date(2026, 6, 11)),
        ledger("LED-03", "49500", "Hussain Brothers", date(2026, 6, 11)),
    ]
    flags = evaluate_flags(rows, [], DEFAULT_CONFIG)
    ids = [flag.flag_id for flag in flags]
    assert ids == [f"FLG-{n:04d}" for n in range(1, len(ids) + 1)]
    assert {flag.rule_id for flag in flags} <= set(RULE_IDS)


def test_every_flag_carries_provenance_a_human_can_open() -> None:
    rows = [ledger("LED-01", "1500000", "Indus Power", date(2026, 6, 14))]
    for flag in evaluate_flags(rows, [], DEFAULT_CONFIG):
        assert flag.source is not None
        assert flag.source.document_id == "DOC-LED-001"
        assert flag.source.row_number == 2


def test_rules_are_deterministic_under_input_reordering() -> None:
    rows = [
        ledger("LED-01", "1500000", "Indus Power", date(2026, 6, 14)),
        ledger("LED-02", "49500", "Hussain Brothers", date(2026, 6, 11)),
        ledger("LED-03", "49500", "Hussain Brothers", date(2026, 6, 11)),
        ledger("LED-04", "25000", "Ravi", date(2026, 6, 8)),
        ledger("LED-05", "25000", "Ravi", date(2026, 6, 9)),
    ]
    forward = {(f.rule_id, f.source_row_id, tuple(f.related_row_ids), f.explanation)
               for f in evaluate_flags(rows, [], DEFAULT_CONFIG)}
    backward = {(f.rule_id, f.source_row_id, tuple(f.related_row_ids), f.explanation)
                for f in evaluate_flags(list(reversed(rows)), [], DEFAULT_CONFIG)}
    assert forward == backward


def test_an_omitted_config_key_falls_back_to_the_default() -> None:
    rows = [ledger("LED-01", "49500", "Hussain Brothers")]
    assert fired(evaluate_flags(rows, [], {"round_number_floor": 1}), "near-limit")
    assert fired(evaluate_flags(rows, [], None), "near-limit")


def test_the_environment_can_override_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RULES_APPROVAL_LIMITS", "25000, 75000")
    monkeypatch.setenv("RULES_NEAR_LIMIT_THRESHOLD", "0.05")
    monkeypatch.setenv("RULES_DUPLICATE_WINDOW_DAYS", "not-a-number")
    config = default_config()
    assert config["approval_limits"] == [25000, 75000]
    assert config["near_limit_tolerance"] == 0.05
    assert config["duplicate_window_days"] == DEFAULT_CONFIG["duplicate_window_days"]


def test_rules_never_decide_anything() -> None:
    """Flags are suggestions: there is no decision field to set, and the ledger
    rows come back untouched."""
    rows = [ledger("LED-01", "1500000", "Indus Power", date(2026, 6, 14))]
    before = [row.model_copy(deep=True) for row in rows]
    flags = evaluate_flags(rows, [], DEFAULT_CONFIG)
    assert rows == before
    assert not any(hasattr(flag, "decision") for flag in flags)


# --------------------------------------------------------------------------- #
# Benford
# --------------------------------------------------------------------------- #


def test_benford_reproduces_the_sample_dashboards_digit_counts() -> None:
    items = fixtures.review_items().items
    expected = fixtures.dashboard().benford
    assert expected is not None

    result = benford_analysis([item.ledger_entry for item in items])

    assert result.sample_size == expected.sample_size
    assert [d.observed_count for d in result.digits] == [
        d.observed_count for d in expected.digits
    ]
    assert result.digits[0].expected_frequency == pytest.approx(0.301, abs=0.001)
    assert result.digits[0].deviation == pytest.approx(-0.101, abs=0.001)
    assert result.deviates_significantly is False


def test_benford_expected_frequencies_follow_the_law() -> None:
    result = benford_analysis([ledger("LED-01", "123", "V")])
    assert [d.expected_frequency for d in result.digits] == [
        0.301, 0.176, 0.125, 0.097, 0.079, 0.067, 0.058, 0.051, 0.046
    ]


def test_benford_over_an_empty_ledger_is_all_zeros() -> None:
    result = benford_analysis([])
    assert result.sample_size == 0
    assert result.chi_square == 0.0
    assert result.deviates_significantly is False


def test_benford_ignores_zero_amounts_and_signs() -> None:
    result = benford_analysis([
        ledger("LED-01", "0", "V"),
        ledger("LED-02", "-284000", "V"),
        ledger("LED-03", "0.045", "V"),
    ])
    assert result.sample_size == 2
    assert result.digits[1].observed_count == 1   # digit 2
    assert result.digits[3].observed_count == 1   # digit 4


def test_benford_never_calls_a_small_sample_significant() -> None:
    """Twenty rows all starting with 9 is lopsided, but too few to conclude on."""
    result = benford_analysis([ledger(f"LED-{n:02d}", "90000", "V") for n in range(20)])
    assert result.chi_square > rules.BENFORD_CHI_SQUARE_CRITICAL
    assert result.deviates_significantly is False

    bigger = benford_analysis(
        [ledger(f"LED-{n:02d}", "90000", "V") for n in range(BENFORD_MIN_SAMPLE)]
    )
    assert bigger.deviates_significantly is True


# --------------------------------------------------------------------------- #
# The boundary
# --------------------------------------------------------------------------- #


def test_the_rules_module_imports_no_ai_client() -> None:
    forbidden = {"httpx", "openai", "dashscope", "anthropic", "requests"}
    package = Path(rules.__file__).parent
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] not in forbidden, f"{path.name} imports {name}"
                assert not name.startswith("app.modules.extraction")
                assert not name.startswith("app.modules.assistant")
                assert not name.startswith("app.modules.matching")
