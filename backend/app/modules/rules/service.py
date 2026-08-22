"""Public interface of the rules module.

This is the only file other modules may import from `modules/rules/`.

**Owned by Dev-D. Not implemented here — this file is the agreed signature.**

Deterministic red-flag rules only. This module must never import an AI client
and must never auto-approve or suppress anything. See the module README.

The agreed initial rule set:

- ``round-number``      amount has >= 3 trailing zeros and is above a floor. Severity low.
- ``weekend-entry``     the date falls on a Saturday or a Sunday. Severity medium.
- ``duplicate-invoice`` the same invoice number appears more than once, or the
                        same party and amount within 3 days. Severity high.
- ``near-limit``        amount is within 2% below any configured approval limit.
                        Severity high.
- ``structuring``       two or more payments to one party on one date, each
                        under a limit but summing to over it. Severity high.
- ``invoice-sequence-gap`` a vendor's invoice numbering skips values. Severity medium.
"""

from __future__ import annotations

from typing import Any

from app.shared.schemas import Flag, LedgerEntry, MatchResult

__all__ = ["evaluate_flags"]


def evaluate_flags(
    ledger: list[LedgerEntry],
    matches: list[MatchResult],
    config: dict[str, Any],
) -> list[Flag]:
    """Apply every red-flag rule and return what fired.

    Args:
        ledger: Ledger rows to test.
        matches: Match results for those rows, so rules can take matching into
            account without recomputing it.
        config: Rule configuration, for example
            ``{"approval_limits": [50000, 100000, 500000], "round_number_floor": 10000}``.

    Returns:
        Every flag that fired, each naming its `rule_id`, a `severity`, a plain
        English `explanation`, and the row it came from. Flags are suggestions
        for human review; nothing here decides anything.
    """
    raise NotImplementedError("rules/ is owned by Dev-D and is not implemented yet")
