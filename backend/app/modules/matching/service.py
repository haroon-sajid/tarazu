"""Public interface of the matching module.

This is the only file other modules may import from `modules/matching/`.

Deterministic pandas logic only. This module must never import an AI client, and
never produce a nondeterministic result: the same three inputs always return the
same list of `MatchResult`. See the module README for the full constraints.

Implementation notes agreed with the team:

- Match each ledger row against the bank transactions and the invoices.
- Exact amount + exact date + party similarity >= 85 -> ``matched`` / ``high``.
- Exact amount + date within 3 days      -> ``matched`` / ``medium``.
- Amount within 1% + party similar       -> ``partial`` / ``low``.
- Nothing found                          -> ``unmatched`` / ``low``.
- Use ``rapidfuzz`` for party similarity, after normalising names with the
  shared ``normalise_party_name`` helper (lowercase, strip legal forms and
  punctuation, collapse extra whitespace).
- Every result carries ``rule_id`` (which rule fired) and ``reason`` (plain
  English, shown verbatim to the auditor).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from rapidfuzz import fuzz

from app.shared.schemas import (
    BankTransaction,
    Invoice,
    LedgerEntry,
    MatchResult,
    MatchStatus,
    MatchStrength,
)
from app.shared.text import normalise_party_name, normalise_reference

__all__ = ["party_similarity", "run_matching"]


#: How close two party names must be to count as "the same party".
_PARTY_SIMILARITY_THRESHOLD = 85

#: Amount tolerance for a partial match (1%).
_AMOUNT_TOLERANCE = Decimal("0.01")


# --------------------------------------------------------------------------- #
# Party name similarity
# --------------------------------------------------------------------------- #


def party_similarity(a: str | None, b: str | None) -> int:
    """Return a 0-100 fuzzy token-set ratio for two party names.

    Legal-form suffixes and extra bank narration words are ignored by the
    shared normaliser, so "Gulberg Traders (Pvt) Ltd" and
    "IBFT GULBERG TRADERS PVT LTD" both score 100.
    """
    if not a or not b:
        return 0
    return int(fuzz.token_set_ratio(normalise_party_name(a), normalise_party_name(b)))


# --------------------------------------------------------------------------- #
# Amount helpers
# --------------------------------------------------------------------------- #


def _same_amount(a: Decimal, b: Decimal) -> bool:
    """Exact decimal equality on absolute values.

    Bank statements may print debits with either sign depending on the template.
    """
    return abs(a) == abs(b)


def _within_tolerance(a: Decimal, b: Decimal, tolerance: Decimal = _AMOUNT_TOLERANCE) -> bool:
    """True when the absolute amounts are within ``tolerance`` of each other.

    Uses the larger absolute amount as the reference to avoid asymmetry and
    divide-by-zero on zero amounts.
    """
    a_abs, b_abs = abs(a), abs(b)
    if a_abs == 0 and b_abs == 0:
        return True
    reference = max(a_abs, b_abs)
    if reference == 0:
        return True
    return abs(a_abs - b_abs) / reference <= tolerance


def _difference_percent(ledger_amount: Decimal, other_amount: Decimal) -> Decimal:
    """Percent difference from the ledger amount, rounded to one decimal."""
    ledger_abs = abs(ledger_amount)
    if ledger_abs == 0:
        return Decimal("0")
    diff = abs(abs(ledger_amount) - abs(other_amount)) / ledger_abs * 100
    return Decimal(str(round(float(diff), 1)))


def _format_amount(value: Decimal) -> str:
    """Human-friendly amount string, always positive in reasons."""
    return f"{abs(value):,.2f}"


def _days_between(a: date, b: date) -> int:
    return abs((a - b).days)


def _is_digit_transposition(a: Decimal, b: Decimal) -> bool:
    """True when two non-equal amounts are made of the same digits.

    45,900 and 49,500 differ only by a transposition; 45,900 and 52,000 do not.
    """
    if a == b:
        return False
    a_digits = sorted(str(abs(a)).replace(".", "").lstrip("0"))
    b_digits = sorted(str(abs(b)).replace(".", "").lstrip("0"))
    return a_digits == b_digits and bool(a_digits)


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def _score_bank_candidate(
    ledger: LedgerEntry, bank: BankTransaction, date_tolerance_days: int
) -> tuple[int, str, str] | None:
    """Score a ledger/bank pair. Returns (score, rule_id, reason) or None.

    Higher score wins. The rule_id and reason describe the best match.
    """
    if ledger.currency != bank.currency:
        return None

    amount_same = _same_amount(ledger.amount, bank.amount)
    amount_close = _within_tolerance(ledger.amount, bank.amount)
    days = _days_between(ledger.date, bank.date)
    party_score = party_similarity(ledger.party_name, bank.description)
    party_match = party_score >= _PARTY_SIMILARITY_THRESHOLD

    # Rule 1: exact amount + exact date + party similar.
    if amount_same and days == 0 and party_match:
        reason = (
            f"Amount and date match exactly and the party name is a {party_score}% match."
        )
        return (100, "exact-amount-exact-date", reason)

    # Rule 2: exact amount + date within tolerance + party similar.
    if amount_same and days <= date_tolerance_days and party_match:
        day_word = "day" if days == 1 else "days"
        reason = f"Amount matches exactly; the bank cleared it {days} {day_word} after the ledger date."
        return (80, "exact-amount-date-within-3-days", reason)

    # Rule 3: amount within 1% + party similar + date within tolerance.
    if amount_close and party_match and days <= date_tolerance_days:
        diff = _difference_percent(ledger.amount, bank.amount)
        reason = (
            f"Party matches ({party_score}%) and the bank amount is within 1% of the "
            f"ledger amount ({diff}% difference)."
        )
        return (60, "amount-within-1pct-party-similar", reason)

    # Rule 4: same party + same date + amount mismatch (transposition/error).
    if party_match and days == 0 and not amount_close:
        ledger_fmt = _format_amount(ledger.amount)
        bank_fmt = _format_amount(bank.amount)
        reason = (
            f"Party and date match, but the ledger records {ledger_fmt} while the bank "
            f"shows {bank_fmt}."
        )
        if _is_digit_transposition(ledger.amount, bank.amount):
            reason += " The difference looks like a digit transposition."
        return (40, "same-party-same-date-amount-mismatch", reason)

    return None


def _score_invoice_candidate(
    ledger: LedgerEntry, invoice: Invoice, date_tolerance_days: int
) -> tuple[int, str, str] | None:
    """Score a ledger/invoice pair. Returns (score, rule_id, reason) or None."""
    if ledger.currency != invoice.currency:
        return None

    amount_same = _same_amount(ledger.amount, invoice.amount)
    amount_close = _within_tolerance(ledger.amount, invoice.amount)
    days = _days_between(ledger.date, invoice.date)
    party_score = party_similarity(ledger.party_name, invoice.party_name)
    party_match = party_score >= _PARTY_SIMILARITY_THRESHOLD

    if days > date_tolerance_days:
        return None

    # Invoice numbers cited in the ledger description are strong evidence.
    ledger_desc_ref = normalise_reference(ledger.description or "")
    invoice_ref = normalise_reference(invoice.invoice_number)
    cites_invoice = invoice_ref and invoice_ref in ledger_desc_ref

    if cites_invoice and amount_same:
        return (
            100,
            "invoice-number-match",
            f"Ledger references invoice {invoice.invoice_number} and the amount matches.",
        )

    if amount_same and party_match:
        return (
            80,
            "exact-amount-party-date-window",
            f"Invoice {invoice.invoice_number} from {invoice.party_name} matches amount and date window.",
        )

    if amount_close and party_match:
        return (
            50,
            "amount-tolerance-invoice-party",
            f"Invoice {invoice.invoice_number} party matches ({party_score}%) and amount is close.",
        )

    return None


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #


def run_matching(
    ledger: list[LedgerEntry],
    bank: list[BankTransaction],
    invoices: list[Invoice],
    date_tolerance_days: int = 3,
) -> list[MatchResult]:
    """Reconcile every ledger row against the bank statement and the invoices.

    Args:
        ledger: Ledger rows, read from Excel or CSV by pandas. No AI involved.
        bank: Bank-statement transactions extracted from the statement PDF.
        invoices: Invoices extracted from PDFs and images.
        date_tolerance_days: How many days apart a bank clearing or invoice may
            be while still counting as the same date window. Must be >= 0.

    Returns:
        One `MatchResult` per ledger row, in the order the ledger rows were
        given. Results are suggestions pending human approval, never verdicts.
    """
    if date_tolerance_days < 0:
        raise ValueError("date_tolerance_days must be non-negative")

    # Track which bank rows have been consumed. Invoices may match multiple
    # ledger rows (duplicate-payment scenario).
    used_bank_ids: set[str] = set()

    results: list[MatchResult] = []
    for entry in ledger:
        best_bank: tuple[int, BankTransaction, str, str] | None = None
        for transaction in bank:
            if transaction.bank_row_id in used_bank_ids:
                continue
            scored = _score_bank_candidate(entry, transaction, date_tolerance_days)
            if scored is None:
                continue
            score, rule_id, reason = scored
            if best_bank is None:
                best_bank = (score, transaction, rule_id, reason)
            elif score > best_bank[0]:
                best_bank = (score, transaction, rule_id, reason)
            elif score == best_bank[0] and transaction.bank_row_id < best_bank[1].bank_row_id:
                best_bank = (score, transaction, rule_id, reason)

        best_invoice: tuple[int, Invoice, str, str] | None = None
        for invoice in invoices:
            scored = _score_invoice_candidate(entry, invoice, date_tolerance_days)
            if scored is None:
                continue
            score, rule_id, reason = scored
            if best_invoice is None or score > best_invoice[0]:
                best_invoice = (score, invoice, rule_id, reason)

        bank_txn = best_bank[1] if best_bank else None
        invoice = best_invoice[1] if best_invoice else None

        if bank_txn is not None:
            # A strong bank match can pull in an invoice even when the invoice
            # date is outside the normal window, as long as amount and party
            # line up. Invoice-only matches still respect the date window.
            if invoice is None:
                for candidate in invoices:
                    if (
                        _same_amount(entry.amount, candidate.amount)
                        and party_similarity(entry.party_name, candidate.party_name)
                        >= _PARTY_SIMILARITY_THRESHOLD
                    ):
                        invoice = candidate
                        break
            used_bank_ids.add(bank_txn.bank_row_id)
            _score, _transaction, bank_rule, bank_reason = best_bank

            status, strength = _status_and_strength(bank_rule)

            # If an invoice also lines up, the wording reflects that all three
            # sources agree — but the strength stays with the bank match.
            if invoice is not None and bank_rule in {
                "exact-amount-exact-date",
                "exact-amount-date-within-3-days",
            } and _same_amount(entry.amount, invoice.amount):
                reason = (
                    f"Ledger, invoice {invoice.invoice_number}, and the bank payment "
                    f"all agree on {_format_amount(entry.amount)}."
                )
            else:
                reason = bank_reason

            results.append(
                MatchResult(
                    ledger_row_id=entry.ledger_row_id,
                    bank_row_id=bank_txn.bank_row_id,
                    invoice_id=invoice.invoice_id if invoice else None,
                    status=status,
                    match_strength=strength,
                    reason=reason,
                    rule_id=bank_rule,
                )
            )
            continue

        # No bank match, but an invoice match counts as partial evidence.
        if invoice is not None:
            results.append(
                MatchResult(
                    ledger_row_id=entry.ledger_row_id,
                    bank_row_id=None,
                    invoice_id=invoice.invoice_id,
                    status=MatchStatus.PARTIAL,
                    match_strength=MatchStrength.MEDIUM,
                    reason=f"Invoice {invoice.invoice_number} matches, but no bank payment was found.",
                    rule_id="invoice-only-no-bank-payment",
                )
            )
            continue

        # Nothing found.
        results.append(
            MatchResult(
                ledger_row_id=entry.ledger_row_id,
                bank_row_id=None,
                invoice_id=None,
                status=MatchStatus.UNMATCHED,
                match_strength=MatchStrength.LOW,
                reason="No bank payment and no invoice found for this ledger entry.",
                rule_id="no-candidate-found",
            )
        )

    return results


def _status_and_strength(rule_id: str) -> tuple[MatchStatus, MatchStrength]:
    if rule_id == "exact-amount-exact-date":
        return MatchStatus.MATCHED, MatchStrength.HIGH
    if rule_id == "exact-amount-date-within-3-days":
        return MatchStatus.MATCHED, MatchStrength.MEDIUM
    return MatchStatus.PARTIAL, MatchStrength.LOW
