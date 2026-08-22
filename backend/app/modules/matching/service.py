"""Public interface of the matching module.

This is the only file other modules may import from `modules/matching/`.

**Owned by Dev-D. Not implemented here — this file is the agreed signature.**

Deterministic pandas logic only. This module must never import an AI client, and
never produce a nondeterministic result: the same three inputs always return the
same list of `MatchResult`. See the module README for the full constraints.

Implementation notes agreed with the team:

- Match each ledger row against the bank transactions and the invoices.
- Exact amount + exact date + party similarity >= 85 -> ``matched`` / ``high``.
- Exact amount + date within 3 days      -> ``matched`` / ``medium``.
- Amount within 1% + party similar       -> ``partial`` / ``low``.
- Nothing found                          -> ``unmatched`` / ``low``.
- Use ``rapidfuzz`` for party similarity, after normalising names (lowercase,
  strip ``pvt``, ``(pvt)``, ``ltd``, ``limited``, ``&``/``and``, punctuation,
  and extra whitespace).
- Every result carries ``rule_id`` (which rule fired) and ``reason`` (plain
  English, shown verbatim to the auditor).
"""

from __future__ import annotations

from app.shared.schemas import BankTransaction, Invoice, LedgerEntry, MatchResult

__all__ = ["run_matching"]


def run_matching(
    ledger: list[LedgerEntry],
    bank: list[BankTransaction],
    invoices: list[Invoice],
) -> list[MatchResult]:
    """Reconcile every ledger row against the bank statement and the invoices.

    Args:
        ledger: Ledger rows, read from Excel or CSV by pandas. No AI involved.
        bank: Bank-statement transactions extracted from the statement PDF.
        invoices: Invoices extracted from PDFs and images.

    Returns:
        One `MatchResult` per ledger row, in the order the ledger rows were
        given. Results are suggestions pending human approval, never verdicts.
    """
    raise NotImplementedError("matching/ is owned by Dev-D and is not implemented yet")
