"""Public interface of the rules module.

This is the only file other modules may import from `modules/rules/`.

Deterministic red-flag rules only. This module must never import an AI client
and must never auto-approve or suppress anything. See the module README.

The agreed initial rule set:

- ``round-number``      amount has >= 3 trailing zeros and is above a floor. Severity low.
- ``weekend-entry``     the date falls on a Saturday or a Sunday. Severity medium.
- ``duplicate-invoice`` the same invoice is matched to more than one ledger row.
                        Severity high.
- ``duplicate-payment`` the same party and amount within the duplicate window.
                        Severity high.
- ``near-limit``        amount is within 2% below any configured approval limit.
                        Severity high.
- ``structuring``       two or more payments to one party on one date, each
                        under a limit but summing to over it. Severity high.
- ``invoice-sequence-gap`` a vendor's invoice numbering skips values. Severity medium.
"""

from __future__ import annotations

import math
import os
import re
from calendar import day_name
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.shared.schemas import (
    BenfordDigit,
    BenfordResult,
    Flag,
    Invoice,
    LedgerEntry,
    MatchResult,
    MatchStatus,
    Provenance,
    Severity,
)
from app.shared.text import normalise_party_name

__all__ = [
    "BENFORD_CHI_SQUARE_CRITICAL",
    "BENFORD_MIN_SAMPLE",
    "DEFAULT_CONFIG",
    "RULE_IDS",
    "benford_analysis",
    "default_config",
    "evaluate_flags",
]


#: Minimum sample size before a Benford deviation is called significant.
BENFORD_MIN_SAMPLE = 50

#: Critical value for chi-square with 8 degrees of freedom at p=0.05.
BENFORD_CHI_SQUARE_CRITICAL = 15.51

#: Rule ids emitted by this module, in the order they are evaluated.
RULE_IDS = [
    "round-number",
    "weekend-entry",
    "duplicate-invoice",
    "duplicate-payment",
    "near-limit",
    "structuring",
    "invoice-sequence-gap",
]

#: Default configuration used when no environment overrides are present.
DEFAULT_CONFIG = {
    "approval_limits": [50_000, 100_000, 500_000],
    "round_number_floor": 10_000,
    "date_tolerance_days": 3,
    "duplicate_window_days": 3,
    "near_limit_tolerance": 0.02,
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _format_amount(value: Decimal) -> str:
    """Human-friendly amount string."""
    return f"{value:,.2f}"


def _format_limit(value: float) -> str:
    """Approval limit formatted as a whole number."""
    return f"{value:,.0f}"


def _trailing_zeros(value: Decimal) -> int:
    """Count trailing zeros in the integer part of a Decimal.

    >>> _trailing_zeros(Decimal("1500000"))
    5
    >>> _trailing_zeros(Decimal("10000"))
    4
    >>> _trailing_zeros(Decimal("49500"))
    2
    """
    s = str(value)
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    stripped = s.rstrip("0")
    return len(s) - len(stripped)


def _is_weekend(value: date) -> bool:
    """Return True for Saturday (5) or Sunday (6)."""
    return value.weekday() >= 5


def _ledger_lookup(ledger: list[LedgerEntry]) -> dict[str, LedgerEntry]:
    return {entry.ledger_row_id: entry for entry in ledger}


def _invoice_lookup(invoices: list[Invoice]) -> dict[str, Invoice]:
    return {invoice.invoice_id: invoice for invoice in invoices}


# --------------------------------------------------------------------------- #
# Individual rules
# --------------------------------------------------------------------------- #


def _round_number_flags(
    ledger: list[LedgerEntry], floor: Decimal
) -> list[Flag]:
    """Flag round figures above a floor as informational."""
    flags: list[Flag] = []
    for entry in ledger:
        if entry.amount <= floor:
            continue
        if _trailing_zeros(entry.amount) >= 3:
            flags.append(
                Flag(
                    flag_id="FLG-TEMP",
                    rule_id="round-number",
                    severity=Severity.LOW,
                    explanation=(
                        f"{_format_amount(entry.amount)} is an exactly round figure. "
                        "Informational only - round amounts are common for advances."
                    ),
                    source_row_id=entry.ledger_row_id,
                    source=entry.source,
                )
            )
    return flags


def _weekend_flags(ledger: list[LedgerEntry]) -> list[Flag]:
    """Flag ledger entries posted on weekends."""
    flags: list[Flag] = []
    for entry in ledger:
        if _is_weekend(entry.date):
            day = day_name[entry.date.weekday()]
            flags.append(
                Flag(
                    flag_id="FLG-TEMP",
                    rule_id="weekend-entry",
                    severity=Severity.MEDIUM,
                    explanation=f"Posted on {day} {entry.date}.",
                    source_row_id=entry.ledger_row_id,
                    source=entry.source,
                )
            )
    return flags


def _duplicate_invoice_flags(
    ledger: list[LedgerEntry],
    matches: list[MatchResult],
    invoices: list[Invoice],
) -> list[Flag]:
    """Flag invoices that are matched to more than one ledger row."""
    flags: list[Flag] = []
    ledger_by_id = _ledger_lookup(ledger)
    invoice_by_id = _invoice_lookup(invoices)

    invoice_to_rows: dict[str, list[str]] = {}
    for match in matches:
        if match.invoice_id:
            invoice_to_rows.setdefault(match.invoice_id, []).append(match.ledger_row_id)

    for invoice_id, row_ids in invoice_to_rows.items():
        if len(row_ids) < 2 or invoice_id not in invoice_by_id:
            continue
        entries = [
            ledger_by_id[row_id]
            for row_id in row_ids
            if row_id in ledger_by_id
        ]
        if len(entries) < 2:
            continue
        entries.sort(key=lambda e: (e.date, e.ledger_row_id))
        first, last = entries[0], entries[-1]
        days = (last.date - first.date).days
        count = len(entries)
        invoice = invoice_by_id[invoice_id]

        if count == 2:
            explanation = (
                f"Invoice {invoice.invoice_number} is paid 2 times: once on {first.date} "
                f"and again on {last.date}, {days} days apart."
            )
        else:
            dates = ", ".join(str(e.date) for e in entries)
            explanation = (
                f"Invoice {invoice.invoice_number} is paid {count} times on {dates}, "
                f"{days} days apart."
            )

        for entry in entries:
            flags.append(
                Flag(
                    flag_id="FLG-TEMP",
                    rule_id="duplicate-invoice",
                    severity=Severity.HIGH,
                    explanation=explanation,
                    source_row_id=entry.ledger_row_id,
                    related_row_ids=[
                        other.ledger_row_id
                        for other in entries
                        if other.ledger_row_id != entry.ledger_row_id
                    ],
                    source=invoice.source,
                )
            )

    return flags


def _duplicate_payment_flags(
    ledger: list[LedgerEntry],
    window_days: int,
) -> list[Flag]:
    """Flag the same party and amount paid more than once within a window."""
    flags: list[Flag] = []

    groups: dict[tuple[str, Decimal], list[LedgerEntry]] = {}
    for entry in ledger:
        key = (normalise_party_name(entry.party_name), entry.amount)
        groups.setdefault(key, []).append(entry)

    for (_party, amount), entries in groups.items():
        if len(entries) < 2:
            continue
        sorted_entries = sorted(entries, key=lambda e: (e.date, e.ledger_row_id))
        for i in range(len(sorted_entries)):
            for j in range(i + 1, len(sorted_entries)):
                first, second = sorted_entries[i], sorted_entries[j]
                days = (second.date - first.date).days
                if days <= window_days:
                    explanation = (
                        f"Duplicate payment of {_format_amount(amount)} to {first.party_name} "
                        f"within {window_days} days: {first.ledger_row_id} on {first.date} "
                        f"and {second.ledger_row_id} on {second.date}."
                    )
                    flags.append(
                        Flag(
                            flag_id="FLG-TEMP",
                            rule_id="duplicate-payment",
                            severity=Severity.HIGH,
                            explanation=explanation,
                            source_row_id=first.ledger_row_id,
                            related_row_ids=[second.ledger_row_id],
                            source=first.source,
                        )
                    )
                    flags.append(
                        Flag(
                            flag_id="FLG-TEMP",
                            rule_id="duplicate-payment",
                            severity=Severity.HIGH,
                            explanation=explanation,
                            source_row_id=second.ledger_row_id,
                            related_row_ids=[first.ledger_row_id],
                            source=second.source,
                        )
                    )
                    break
    return flags


def _near_limit_flags(
    ledger: list[LedgerEntry],
    approval_limits: list[float],
    tolerance: float,
) -> list[Flag]:
    """Flag amounts that sit just below an approval limit."""
    flags: list[Flag] = []
    for entry in ledger:
        amount = float(entry.amount)
        for limit in sorted(approval_limits):
            if limit <= 0 or amount >= limit:
                continue
            gap = limit - amount
            if gap / limit <= tolerance:
                percent = round(gap / limit * 100, 1)
                flags.append(
                    Flag(
                        flag_id="FLG-TEMP",
                        rule_id="near-limit",
                        severity=Severity.HIGH,
                        explanation=(
                            f"{_format_amount(entry.amount)} sits {percent}% below the "
                            f"{_format_limit(limit)} approval limit."
                        ),
                        source_row_id=entry.ledger_row_id,
                        source=entry.source,
                    )
                )
                break  # Only flag the nearest limit.
    return flags


def _structuring_flags(
    ledger: list[LedgerEntry],
    approval_limits: list[float],
) -> list[Flag]:
    """Flag multiple payments to the same party on the same day that split a limit."""
    flags: list[Flag] = []

    groups: dict[tuple[str, date], list[LedgerEntry]] = {}
    for entry in ledger:
        key = (normalise_party_name(entry.party_name), entry.date)
        groups.setdefault(key, []).append(entry)

    for (party, when), entries in groups.items():
        if len(entries) < 2:
            continue
        for limit in sorted(approval_limits):
            if limit <= 0:
                continue
            under_limit = [e for e in entries if float(e.amount) < limit]
            if len(under_limit) < 2:
                continue
            total = sum(float(e.amount) for e in under_limit)
            if total > limit:
                sorted_entries = sorted(
                    under_limit, key=lambda e: (e.amount, e.ledger_row_id)
                )
                explanation = (
                    f"{len(sorted_entries)} payments to {sorted_entries[0].party_name} on {when}, "
                    f"each below the {_format_limit(limit)} approval limit, total "
                    f"{_format_amount(Decimal(str(total)))}. Splitting a payment to stay "
                    "under an approval limit is a structuring pattern."
                )
                for entry in sorted_entries:
                    flags.append(
                        Flag(
                            flag_id="FLG-TEMP",
                            rule_id="structuring",
                            severity=Severity.HIGH,
                            explanation=explanation,
                            source_row_id=entry.ledger_row_id,
                            related_row_ids=[
                                other.ledger_row_id
                                for other in sorted_entries
                                if other.ledger_row_id != entry.ledger_row_id
                            ],
                            source=entry.source,
                        )
                    )
                break  # Only flag the first limit that triggers.

    return flags


# --------------------------------------------------------------------------- #
# Invoice sequence gaps
# --------------------------------------------------------------------------- #


def _extract_numeric_sequence(value: str) -> tuple[str, int] | None:
    """Extract a trailing numeric sequence from an invoice number.

    >>> _extract_numeric_sequence("INV-2026-0087")
    ('INV-2026-', 87)
    >>> _extract_numeric_sequence("SMW/2026/0431")
    ('SMW/2026/', 431)
    """
    match = re.search(r"^(.*?)(\d+)$", value.strip())
    if not match:
        return None
    prefix, number = match.groups()
    return (prefix, int(number))


def _invoice_sequence_gap_flags(
    ledger: list[LedgerEntry],
    matches: list[MatchResult],
    invoices: list[Invoice],
) -> list[Flag]:
    """Flag missing numbers in a vendor's invoice sequence."""
    flags: list[Flag] = []
    ledger_by_id = _ledger_lookup(ledger)
    invoice_to_row: dict[str, str] = {}
    for match in matches:
        if match.invoice_id and match.ledger_row_id in ledger_by_id:
            invoice_to_row[match.invoice_id] = match.ledger_row_id

    by_party: dict[str, list[Invoice]] = {}
    for invoice in invoices:
        by_party.setdefault(normalise_party_name(invoice.party_name), []).append(invoice)

    for _party, party_invoices in by_party.items():
        sequences: dict[str, list[tuple[int, Invoice]]] = {}
        for invoice in party_invoices:
            parsed = _extract_numeric_sequence(invoice.invoice_number)
            if parsed is None:
                continue
            prefix, number = parsed
            sequences.setdefault(prefix, []).append((number, invoice))

        for prefix, items in sequences.items():
            if len(items) < 2:
                continue
            items.sort(key=lambda item: item[0])
            for i in range(len(items) - 1):
                current_num, current_invoice = items[i]
                next_num, next_invoice = items[i + 1]
                gap = next_num - current_num
                if gap > 1:
                    current_row_id = invoice_to_row.get(current_invoice.invoice_id)
                    next_row_id = invoice_to_row.get(next_invoice.invoice_id)
                    if current_row_id is None or next_row_id is None:
                        continue
                    source_entry = ledger_by_id[current_row_id]
                    flags.append(
                        Flag(
                            flag_id="FLG-TEMP",
                            rule_id="invoice-sequence-gap",
                            severity=Severity.MEDIUM,
                            explanation=(
                                f"Invoice sequence for {prefix.strip()} jump from "
                                f"{current_invoice.invoice_number} to "
                                f"{next_invoice.invoice_number}: {gap - 1} numbers"
                            ),
                            source_row_id=current_row_id,
                            related_row_ids=[next_row_id],
                            source=source_entry.source,
                        )
                    )

    return flags


# --------------------------------------------------------------------------- #
# Default configuration
# --------------------------------------------------------------------------- #


def _parse_int_list(value: str) -> list[int] | None:
    try:
        return [int(part.strip()) for part in value.split(",")]
    except ValueError:
        return None


def _parse_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def default_config() -> dict[str, Any]:
    """Return the default rule configuration with environment overrides applied.

    The pipeline imports this at module load time, so the configuration is
    visible to callers without reaching into the module's internals.
    """
    config = {
        "approval_limits": list(DEFAULT_CONFIG["approval_limits"]),
        "round_number_floor": DEFAULT_CONFIG["round_number_floor"],
        "date_tolerance_days": DEFAULT_CONFIG["date_tolerance_days"],
        "duplicate_window_days": DEFAULT_CONFIG["duplicate_window_days"],
        "near_limit_tolerance": DEFAULT_CONFIG["near_limit_tolerance"],
    }

    if approval_limits := os.getenv("RULES_APPROVAL_LIMITS"):
        parsed = _parse_int_list(approval_limits)
        if parsed is not None:
            config["approval_limits"] = parsed

    if near_limit := os.getenv("RULES_NEAR_LIMIT_THRESHOLD"):
        parsed = _parse_float(near_limit)
        if parsed is not None:
            config["near_limit_tolerance"] = parsed

    if duplicate_window := os.getenv("RULES_DUPLICATE_WINDOW_DAYS"):
        parsed = _parse_int(duplicate_window)
        if parsed is not None:
            config["duplicate_window_days"] = parsed

    return config


# --------------------------------------------------------------------------- #
# Benford's Law
# --------------------------------------------------------------------------- #


def _leading_digit(amount: float) -> int | None:
    digits = str(amount).replace(".", "").lstrip("0")
    if not digits:
        return None
    leading = int(digits[0])
    return leading if 1 <= leading <= 9 else None


def benford_analysis(ledger: list[LedgerEntry]) -> BenfordResult:
    """Run a Benford's Law first-digit test on the ledger amounts.

    Benford's Law states that in many naturally occurring datasets, the leading
    digit ``d`` appears with probability log10(1 + 1/d). Significant deviation may
    indicate manipulated or fabricated numbers, but small samples are never
    called significant because the test is under-powered.
    """
    amounts = [abs(float(entry.amount)) for entry in ledger if entry.amount != 0]
    sample_size = len(amounts)

    if sample_size == 0:
        digits = [
            BenfordDigit(
                digit=d,
                observed_count=0,
                observed_frequency=0.0,
                expected_frequency=round(math.log10(1 + 1 / d), 3),
                deviation=0.0,
            )
            for d in range(1, 10)
        ]
        return BenfordResult(
            sample_size=0,
            digits=digits,
            chi_square=0.0,
            degrees_of_freedom=8,
            deviates_significantly=False,
        )

    observed_counts: dict[int, int] = {d: 0 for d in range(1, 10)}
    for amount in amounts:
        leading = _leading_digit(amount)
        if leading is not None:
            observed_counts[leading] += 1

    digits: list[BenfordDigit] = []
    chi_square = 0.0
    for d in range(1, 10):
        expected_freq = round(math.log10(1 + 1 / d), 3)
        observed_count = observed_counts[d]
        observed_freq = round(observed_count / sample_size, 3)
        deviation = round(observed_freq - expected_freq, 3)
        digits.append(
            BenfordDigit(
                digit=d,
                observed_count=observed_count,
                observed_frequency=observed_freq,
                expected_frequency=expected_freq,
                deviation=deviation,
            )
        )
        expected_count = sample_size * expected_freq
        if expected_count > 0:
            chi_square += (observed_count - expected_count) ** 2 / expected_count

    deviates_significantly = (
        sample_size >= BENFORD_MIN_SAMPLE and chi_square > BENFORD_CHI_SQUARE_CRITICAL
    )

    return BenfordResult(
        sample_size=sample_size,
        digits=digits,
        chi_square=round(chi_square, 4),
        degrees_of_freedom=8,
        deviates_significantly=deviates_significantly,
    )


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #


def evaluate_flags(
    ledger: list[LedgerEntry],
    matches: list[MatchResult],
    config: dict[str, Any] | None,
    invoices: list[Invoice] | None = None,
    bank: list[Any] | None = None,
) -> list[Flag]:
    """Apply every red-flag rule and return what fired.

    Args:
        ledger: Ledger rows to test.
        matches: Match results for those rows, so rules can take matching into
            account without recomputing it.
        config: Rule configuration. Missing keys fall back to ``DEFAULT_CONFIG``;
            ``None`` uses the defaults.
        invoices: Invoices extracted from the uploaded documents, used for
            sequence-gap checks.
        bank: Bank transactions extracted from the statement PDF. Reserved for
            future rules; currently unused.

    Returns:
        Every flag that fired, each naming its ``rule_id``, a ``severity``, a plain
        English ``explanation``, and the row it came from. Flags are suggestions
        for human review; nothing here decides anything.
    """
    base = DEFAULT_CONFIG.copy()
    if config:
        base.update(config)

    approval_limits = [float(limit) for limit in base.get("approval_limits", [])]
    round_floor = Decimal(str(base.get("round_number_floor", 10_000)))
    duplicate_window = base.get("duplicate_window_days", 3)
    near_limit_tolerance = base.get("near_limit_tolerance", 0.02)

    flags: list[Flag] = []
    flags.extend(_round_number_flags(ledger, round_floor))
    flags.extend(_weekend_flags(ledger))
    flags.extend(_duplicate_invoice_flags(ledger, matches, invoices or []))
    flags.extend(_duplicate_payment_flags(ledger, duplicate_window))
    flags.extend(_near_limit_flags(ledger, approval_limits, near_limit_tolerance))
    flags.extend(_structuring_flags(ledger, approval_limits))
    flags.extend(_invoice_sequence_gap_flags(ledger, matches, invoices or []))

    # Number flags deterministically in emission order.
    for position, flag in enumerate(flags, start=1):
        flag.flag_id = f"FLG-{position:04d}"

    return flags
