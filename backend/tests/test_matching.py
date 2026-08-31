"""The deterministic matcher: tiers, one-to-one bank assignment, shared invoices.

Every test builds its rows by hand and asserts exact statuses, strengths, and
rule ids. Nothing is mocked — there is nothing to mock, which is the point.
"""

from __future__ import annotations

import ast
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.matching import service as matching
from app.modules.matching.service import party_similarity, run_matching
from app.shared.schemas import (
    BankTransaction,
    Invoice,
    LedgerEntry,
    MatchStatus,
    MatchStrength,
    Provenance,
)
from app.shared.text import normalise_party_name, normalise_reference


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def ledger(
    row_id: str,
    amount: str,
    party: str,
    when: date = date(2026, 6, 2),
    description: str | None = None,
    currency: str = "PKR",
) -> LedgerEntry:
    return LedgerEntry(
        ledger_row_id=row_id,
        date=when,
        amount=Decimal(amount),
        party_name=party,
        description=description,
        currency=currency,
        source=Provenance(document_id="DOC-LED-001", row_number=int(row_id[-2:]) + 1),
    )


def bank(
    row_id: str,
    amount: str,
    description: str,
    when: date = date(2026, 6, 2),
    currency: str = "PKR",
) -> BankTransaction:
    return BankTransaction(
        bank_row_id=row_id,
        date=when,
        amount=Decimal(amount),
        description=description,
        currency=currency,
        source=Provenance(document_id="DOC-BNK-001", page=1, text_snippet=amount),
    )


def invoice(
    invoice_id: str,
    number: str,
    amount: str,
    party: str,
    when: date = date(2026, 6, 1),
) -> Invoice:
    return Invoice(
        invoice_id=invoice_id,
        invoice_number=number,
        date=when,
        amount=Decimal(amount),
        party_name=party,
        source=Provenance(document_id=invoice_id, page=1, text_snippet=amount),
    )


# --------------------------------------------------------------------------- #
# Name normalisation and similarity
# --------------------------------------------------------------------------- #


def test_legal_suffixes_and_punctuation_do_not_count() -> None:
    assert normalise_party_name("Gulberg Traders (Pvt) Ltd") == "gulberg traders"
    assert normalise_party_name("Karachi Packaging Co.") == "karachi packaging"
    assert normalise_party_name("Hussain Brothers & Sons") == "hussain brothers sons"


def test_a_bank_narration_scores_as_the_same_party() -> None:
    assert party_similarity("Gulberg Traders (Pvt) Ltd", "IBFT GULBERG TRADERS PVT LTD") == 100
    assert party_similarity("Hussain Brothers & Sons", "IBFT HUSSAIN BROTHERS AND SONS") == 100
    assert party_similarity("Al-Habib Stationers", "CHQ 004418 AL HABIB STATIONERS") >= 85


def test_different_businesses_do_not_score_as_the_same() -> None:
    assert party_similarity("Ravi Logistics Pvt Ltd", "Shalimar Trading Co") < 50


def test_empty_names_are_not_evidence() -> None:
    assert party_similarity("", "") == 0
    assert party_similarity("Anything", None) == 0


def test_invoice_references_compare_without_separators() -> None:
    assert normalise_reference("INV-2026-0087") == "INV20260087"
    assert normalise_reference("inv 2026/0087") == "INV20260087"


# --------------------------------------------------------------------------- #
# Tiers
# --------------------------------------------------------------------------- #


def test_exact_amount_and_date_with_the_same_party_is_a_high_match() -> None:
    [result] = run_matching(
        [ledger("LED-01", "284000", "Gulberg Traders (Pvt) Ltd")],
        [bank("BNK-01", "284000", "IBFT GULBERG TRADERS PVT LTD")],
        [],
    )
    assert result.status is MatchStatus.MATCHED
    assert result.match_strength is MatchStrength.HIGH
    assert result.rule_id == "exact-amount-exact-date"
    assert result.bank_row_id == "BNK-01"
    assert "100% match" in result.reason


def test_exact_amount_within_the_date_window_is_a_medium_match() -> None:
    [result] = run_matching(
        [ledger("LED-01", "63750", "Ravi Logistics Pvt Ltd", date(2026, 6, 8))],
        [bank("BNK-01", "63750", "ONLINE TFR RAVI LOGISTICS", date(2026, 6, 10))],
        [],
    )
    assert result.status is MatchStatus.MATCHED
    assert result.match_strength is MatchStrength.MEDIUM
    assert result.rule_id == "exact-amount-date-within-3-days"
    assert "2 days after the ledger date" in result.reason


def test_outside_the_date_window_is_not_a_match() -> None:
    [result] = run_matching(
        [ledger("LED-01", "63750", "Ravi Logistics", date(2026, 6, 8))],
        [bank("BNK-01", "63750", "RAVI LOGISTICS", date(2026, 6, 20))],
        [],
    )
    assert result.status is MatchStatus.UNMATCHED
    assert result.rule_id == "no-candidate-found"


def test_the_date_window_is_adjustable() -> None:
    rows = [ledger("LED-01", "63750", "Ravi Logistics", date(2026, 6, 8))]
    lines = [bank("BNK-01", "63750", "RAVI LOGISTICS", date(2026, 6, 20))]
    assert run_matching(rows, lines, [], date_tolerance_days=14)[0].status is MatchStatus.MATCHED
    with pytest.raises(ValueError):
        run_matching(rows, lines, [], date_tolerance_days=-1)


def test_an_amount_within_one_percent_is_partial() -> None:
    [result] = run_matching(
        [ledger("LED-01", "100000", "Sialkot Metal Works")],
        [bank("BNK-01", "99500", "IBFT SIALKOT METAL WORKS")],
        [],
    )
    assert result.status is MatchStatus.PARTIAL
    assert result.match_strength is MatchStrength.LOW
    assert result.rule_id == "amount-within-1pct-party-similar"
    assert "0.5% difference" in result.reason


def test_same_party_same_date_different_amount_is_partial_and_names_a_transposition() -> None:
    [result] = run_matching(
        [ledger("LED-01", "45900", "Al-Habib Stationers", date(2026, 6, 10))],
        [bank("BNK-01", "49500", "CHQ 004418 AL HABIB STATIONERS", date(2026, 6, 10))],
        [],
    )
    assert result.status is MatchStatus.PARTIAL
    assert result.rule_id == "same-party-same-date-amount-mismatch"
    assert "45,900.00" in result.reason and "49,500.00" in result.reason
    assert "digit transposition" in result.reason


def test_a_mismatch_that_is_not_a_transposition_says_only_that_it_differs() -> None:
    [result] = run_matching(
        [ledger("LED-01", "45900", "Al-Habib Stationers")],
        [bank("BNK-01", "52000", "AL HABIB STATIONERS")],
        [],
    )
    assert result.rule_id == "same-party-same-date-amount-mismatch"
    assert "transposition" not in result.reason


def test_nothing_found_is_unmatched_with_no_counterpart() -> None:
    [result] = run_matching(
        [ledger("LED-01", "187500", "Shalimar Trading Co")],
        [bank("BNK-01", "96400", "KARACHI PACKAGING")],
        [invoice("DOC-INV-1", "INV-1", "96400", "Karachi Packaging Co.")],
    )
    assert result.status is MatchStatus.UNMATCHED
    assert result.match_strength is MatchStrength.LOW
    assert result.bank_row_id is None and result.invoice_id is None
    assert "No bank payment and no invoice" in result.reason


def test_bank_amounts_are_compared_on_absolute_value() -> None:
    """Statements print debits with whatever sign the template uses."""
    [result] = run_matching(
        [ledger("LED-01", "284000", "Gulberg Traders")],
        [bank("BNK-01", "-284000", "GULBERG TRADERS")],
        [],
    )
    assert result.status is MatchStatus.MATCHED


def test_a_different_currency_never_matches() -> None:
    [result] = run_matching(
        [ledger("LED-01", "1000", "Gulberg Traders", currency="USD")],
        [bank("BNK-01", "1000", "GULBERG TRADERS", currency="PKR")],
        [],
    )
    assert result.status is MatchStatus.UNMATCHED


# --------------------------------------------------------------------------- #
# Invoices
# --------------------------------------------------------------------------- #


def test_all_three_documents_agreeing_is_worded_as_such() -> None:
    [result] = run_matching(
        [ledger("LED-01", "96400", "Karachi Packaging Co.", date(2026, 6, 5),
                "Carton supply against INV-2026-0087")],
        [bank("BNK-01", "96400", "CHQ 004412 KARACHI PACKAGING CO", date(2026, 6, 5))],
        [invoice("DOC-INV-0087", "INV-2026-0087", "96400", "Karachi Packaging Co.",
                 date(2026, 6, 3))],
    )
    assert result.status is MatchStatus.MATCHED
    assert result.match_strength is MatchStrength.HIGH
    assert result.invoice_id == "DOC-INV-0087"
    assert result.reason == (
        "Ledger, invoice INV-2026-0087, and the bank payment all agree on 96,400.00."
    )


def test_an_invoice_without_a_bank_payment_is_partial_evidence() -> None:
    [result] = run_matching(
        [ledger("LED-01", "96400", "Karachi Packaging Co.", date(2026, 6, 5))],
        [],
        [invoice("DOC-INV-0087", "INV-2026-0087", "96400", "Karachi Packaging Co.",
                 date(2026, 6, 3))],
    )
    assert result.status is MatchStatus.PARTIAL
    assert result.match_strength is MatchStrength.MEDIUM
    assert result.rule_id == "invoice-only-no-bank-payment"
    assert result.invoice_id == "DOC-INV-0087"
    assert result.bank_row_id is None


def test_an_invoice_is_found_by_its_number_in_the_ledger_description() -> None:
    """The party name is garbled, but the description names the invoice."""
    [result] = run_matching(
        [ledger("LED-01", "96400", "KPC", date(2026, 6, 5), "Payment ref INV-2026-0087")],
        [],
        [invoice("DOC-INV-0087", "INV-2026-0087", "96400", "Karachi Packaging Co.",
                 date(2026, 6, 3))],
    )
    assert result.invoice_id == "DOC-INV-0087"


def test_two_ledger_rows_may_share_one_invoice() -> None:
    """A duplicate payment is two rows pointing at one invoice; rules/ flags it."""
    results = run_matching(
        [
            ledger("LED-01", "96400", "Karachi Packaging Co.", date(2026, 6, 5)),
            ledger("LED-02", "96400", "Karachi Packaging Co.", date(2026, 6, 16)),
        ],
        [
            bank("BNK-01", "96400", "CHQ 004412 KARACHI PACKAGING CO", date(2026, 6, 5)),
            bank("BNK-02", "96400", "CHQ 004431 KARACHI PACKAGING CO", date(2026, 6, 16)),
        ],
        [invoice("DOC-INV-0087", "INV-2026-0087", "96400", "Karachi Packaging Co.",
                 date(2026, 6, 3))],
    )
    assert [r.invoice_id for r in results] == ["DOC-INV-0087", "DOC-INV-0087"]
    assert [r.bank_row_id for r in results] == ["BNK-01", "BNK-02"]


def test_an_invoice_dated_long_after_the_payment_is_not_its_invoice() -> None:
    [result] = run_matching(
        [ledger("LED-01", "96400", "Karachi Packaging Co.", date(2026, 6, 5))],
        [],
        [invoice("DOC-INV-9", "INV-9", "96400", "Karachi Packaging Co.", date(2026, 7, 30))],
    )
    assert result.invoice_id is None


# --------------------------------------------------------------------------- #
# One-to-one bank assignment
# --------------------------------------------------------------------------- #


def test_a_statement_line_explains_at_most_one_ledger_row() -> None:
    results = run_matching(
        [
            ledger("LED-01", "49500", "Hussain Brothers & Sons", date(2026, 6, 11)),
            ledger("LED-02", "49500", "Hussain Brothers & Sons", date(2026, 6, 11)),
            ledger("LED-03", "49500", "Hussain Brothers & Sons", date(2026, 6, 11)),
        ],
        [
            bank("BNK-01", "49500", "IBFT HUSSAIN BROTHERS AND SONS", date(2026, 6, 11)),
            bank("BNK-02", "49500", "IBFT HUSSAIN BROTHERS AND SONS", date(2026, 6, 11)),
        ],
        [],
    )
    assigned = [r.bank_row_id for r in results]
    assert assigned[:2] == ["BNK-01", "BNK-02"]
    assert results[2].status is MatchStatus.UNMATCHED
    assert len({row for row in assigned if row}) == 2


def test_the_stronger_pair_wins_the_line_whatever_the_file_order() -> None:
    """Row 1 could take the line on date alone; row 2 is the exact match."""
    results = run_matching(
        [
            ledger("LED-01", "50000", "Somebody Else", date(2026, 6, 3)),
            ledger("LED-02", "50000", "Gulberg Traders", date(2026, 6, 2)),
        ],
        [bank("BNK-01", "50000", "IBFT GULBERG TRADERS", date(2026, 6, 2))],
        [],
    )
    assert results[1].bank_row_id == "BNK-01"
    assert results[1].rule_id == "exact-amount-exact-date"
    assert results[0].status is MatchStatus.UNMATCHED


# --------------------------------------------------------------------------- #
# Determinism and the sample case
# --------------------------------------------------------------------------- #


def sample_case() -> tuple[list[LedgerEntry], list[BankTransaction], list[Invoice]]:
    """The Haroon Textiles ledger with its planted errors, as typed rows."""
    rows = [
        ledger("LED-03", "284000", "Gulberg Traders (Pvt) Ltd", date(2026, 6, 2)),
        ledger("LED-07", "96400", "Karachi Packaging Co.", date(2026, 6, 5),
               "Carton supply against INV-2026-0087"),
        ledger("LED-09", "63750", "Ravi Logistics Pvt Ltd", date(2026, 6, 8)),
        ledger("LED-12", "45900", "Al-Habib Stationers", date(2026, 6, 10)),
        ledger("LED-14", "49500", "Hussain Brothers & Sons", date(2026, 6, 11)),
        ledger("LED-15", "49500", "Hussain Brothers & Sons", date(2026, 6, 11)),
        ledger("LED-19", "1500000", "Indus Power Solutions", date(2026, 6, 14)),
        ledger("LED-23", "96400", "Karachi Packaging Co.", date(2026, 6, 16),
               "Carton supply against INV-2026-0087"),
        ledger("LED-27", "312880", "Sialkot Metal Works", date(2026, 6, 17)),
        ledger("LED-31", "187500", "Shalimar Trading Co", date(2026, 6, 18)),
    ]
    lines = [
        bank("BNK-12", "284000", "IBFT GULBERG TRADERS PVT LTD", date(2026, 6, 2)),
        bank("BNK-31", "96400", "CHQ 004412 KARACHI PACKAGING CO", date(2026, 6, 5)),
        bank("BNK-38", "63750", "ONLINE TFR RAVI LOGISTICS", date(2026, 6, 10)),
        bank("BNK-44", "49500", "CHQ 004418 AL HABIB STATIONERS", date(2026, 6, 10)),
        bank("BNK-51", "49500", "IBFT HUSSAIN BROTHERS AND SONS", date(2026, 6, 11)),
        bank("BNK-52", "49500", "IBFT HUSSAIN BROTHERS AND SONS", date(2026, 6, 11)),
        bank("BNK-63", "1500000", "RTGS INDUS POWER SOLUTIONS", date(2026, 6, 14)),
        bank("BNK-71", "96400", "CHQ 004431 KARACHI PACKAGING CO", date(2026, 6, 16)),
        bank("BNK-79", "312880", "IBFT SIALKOT METAL WORKS", date(2026, 6, 19)),
    ]
    invoices = [
        invoice("DOC-INV-0087", "INV-2026-0087", "96400", "Karachi Packaging Co.",
                date(2026, 6, 3)),
        invoice("DOC-INV-0431", "SMW/2026/0431", "312880", "Sialkot Metal Works",
                date(2026, 6, 15)),
    ]
    return rows, lines, invoices


def test_the_sample_case_reproduces_its_planted_errors() -> None:
    rows, lines, invoices = sample_case()
    by_row = {r.ledger_row_id: r for r in run_matching(rows, lines, invoices)}

    assert by_row["LED-03"].rule_id == "exact-amount-exact-date"
    assert by_row["LED-07"].invoice_id == "DOC-INV-0087"
    assert by_row["LED-23"].invoice_id == "DOC-INV-0087"      # paid twice
    assert by_row["LED-09"].rule_id == "exact-amount-date-within-3-days"
    assert by_row["LED-12"].rule_id == "same-party-same-date-amount-mismatch"
    assert by_row["LED-14"].bank_row_id != by_row["LED-15"].bank_row_id
    assert by_row["LED-27"].invoice_id == "DOC-INV-0431"
    assert by_row["LED-27"].match_strength is MatchStrength.MEDIUM
    assert by_row["LED-31"].status is MatchStatus.UNMATCHED   # fictitious vendor


def test_results_come_back_in_ledger_order() -> None:
    rows, lines, invoices = sample_case()
    assert [r.ledger_row_id for r in run_matching(rows, lines, invoices)] == [
        r.ledger_row_id for r in rows
    ]


def test_the_matcher_is_deterministic_under_input_shuffling() -> None:
    rows, lines, invoices = sample_case()
    baseline = {r.ledger_row_id: r for r in run_matching(rows, lines, invoices)}
    for seed in range(5):
        rng = random.Random(seed)
        shuffled_lines = list(lines)
        shuffled_invoices = list(invoices)
        rng.shuffle(shuffled_lines)
        rng.shuffle(shuffled_invoices)
        again = {
            r.ledger_row_id: r for r in run_matching(rows, shuffled_lines, shuffled_invoices)
        }
        assert again == baseline


def test_a_large_case_stays_fast_and_consistent() -> None:
    day = date(2026, 6, 1)
    rows = [
        ledger(f"LED-{n:02d}", str(10_000 + 37 * n), f"Vendor {n} Pvt Ltd", day + timedelta(days=n % 28))
        for n in range(400)
    ]
    lines = [
        bank(f"BNK-{n:02d}", str(10_000 + 37 * n), f"IBFT VENDOR {n} PVT LTD", day + timedelta(days=n % 28))
        for n in range(400)
    ]
    results = run_matching(rows, lines, [])
    assert all(r.status is MatchStatus.MATCHED for r in results)
    assert len({r.bank_row_id for r in results}) == 400


# --------------------------------------------------------------------------- #
# The boundary
# --------------------------------------------------------------------------- #


def test_the_matching_module_imports_no_ai_client() -> None:
    """Reliability rule 2, checked against the source rather than trusted."""
    forbidden = {"httpx", "openai", "dashscope", "anthropic", "requests"}
    package = Path(matching.__file__).parent
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
                assert not name.startswith("app.modules.extraction"), (
                    f"{path.name} reaches into extraction/: {name}"
                )
                assert not name.startswith("app.modules.assistant"), (
                    f"{path.name} reaches into assistant/: {name}"
                )
