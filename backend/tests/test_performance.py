"""Budgets for the deterministic steps at the size of a real monthly case.

A textile mill's month is a few thousand ledger rows against a few thousand
bank lines. Matching compares pairs, so it is where a slow path hides: before
the cheap date and amount checks ran ahead of the fuzzy name compare, a
3,000 × 3,000 case meant nine million fuzzy comparisons and minutes of wall
clock. These tests hold each step under a budget generous enough for a slow
CI box and far below what a person would call hung.

The data is synthetic and seeded, so the numbers are stable run to run.
"""

from __future__ import annotations

import csv
import io
import random
import time
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.modules.extraction.bank_reader import read_bank_statement
from app.modules.extraction.ledger_reader import read_ledger
from app.modules.matching import service as matching
from app.modules.rules import service as rules
from app.pipeline import build_review_items
from app.shared.schemas import BankTransaction, LedgerEntry, Provenance

PARTIES = [
    "Gulberg Traders (Pvt) Ltd", "Al-Habib Stationers", "Ravi Logistics Pvt Ltd",
    "Indus Power Solutions", "Karachi Packaging Co.", "Hussain Brothers & Sons",
    "Shalimar Trading Co", "Sialkot Metal Works", "Lahore Dyeing Mills", "Multan Cotton Ginners",
] + [f"Vendor {n} Enterprises" for n in range(190)]


def _synthetic(rows: int, seed: int = 3) -> tuple[list[LedgerEntry], list[BankTransaction]]:
    rng = random.Random(seed)
    start = date(2026, 6, 1)
    ledger: list[LedgerEntry] = []
    bank: list[BankTransaction] = []
    for row in range(2, rows + 2):
        party = rng.choice(PARTIES)
        amount = Decimal(rng.randint(1, 2_000)) * 100
        when = start + timedelta(days=rng.randint(0, 29))
        ledger.append(
            LedgerEntry(
                ledger_row_id=f"LED-{row:05d}", date=when, amount=amount, party_name=party,
                description=f"Payment {row}",
                source=Provenance(document_id="DOC-LED-001", row_number=row),
            )
        )
        # Most rows clear a day or two later; some never appear on the statement.
        if rng.random() < 0.9:
            bank.append(
                BankTransaction(
                    bank_row_id=f"BNK-{row:05d}",
                    date=when + timedelta(days=rng.randint(0, 3)),
                    amount=-amount if rng.random() < 0.97 else -(amount + 100),
                    description=f"IBFT {party.upper()} {rng.randint(1000, 9999)}",
                    source=Provenance(document_id="DOC-BNK-001", row_number=row),
                )
            )
    return ledger, bank


def _timed(label: str, budget_seconds: float, work):
    started = time.perf_counter()
    result = work()
    elapsed = time.perf_counter() - started
    assert elapsed < budget_seconds, f"{label} took {elapsed:.1f}s; budget {budget_seconds}s"
    return result


@pytest.mark.slow
def test_matching_a_monthly_case_stays_within_budget() -> None:
    ledger, bank = _synthetic(3_000)
    results = _timed("matching 3,000 × 2,700", 30.0, lambda: matching.run_matching(ledger, bank, []))
    assert len(results) == len(ledger)
    matched = sum(1 for result in results if result.bank_row_id is not None)
    # Most rows clear against the statement; the rest are honestly unmatched.
    assert matched > len(ledger) * 0.6


@pytest.mark.slow
def test_rules_benford_and_assembly_over_five_thousand_rows_stay_within_budget() -> None:
    ledger, bank = _synthetic(5_000, seed=5)
    matches = matching.run_matching(ledger[:200], bank[:200], [])
    flags = _timed("rules over 5,000", 10.0, lambda: rules.evaluate_flags(ledger, matches, None, bank=bank))
    assert len({flag.flag_id for flag in flags}) == len(flags)
    benford = _timed("benford over 5,000", 5.0, lambda: rules.benford_analysis(ledger))
    assert benford.sample_size == 5_000
    items = _timed(
        "assembly of 200 items", 5.0,
        lambda: build_review_items("CASE-PERF", ledger[:200], bank[:200], [], matches, flags, []),
    )
    assert len(items) == 200


@pytest.mark.slow
def test_reading_twenty_thousand_rows_stays_within_budget() -> None:
    rng = random.Random(9)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Date", "Description", "Reference", "Debit (PKR)", "Credit (PKR)", "Balance (PKR)"])
    for row in range(20_000):
        when = date(2026, 6, 1) + timedelta(days=row % 30)
        debit = f"{rng.randint(1, 900) * 100:,}.00" if row % 3 else ""
        credit = "" if debit else f"{rng.randint(1, 900) * 100:,}.00"
        writer.writerow([when.strftime("%d/%m/%Y"), f"Payment to {rng.choice(PARTIES)}", f"CHQ-{row}", debit, credit, "1,000.00"])
    data = buffer.getvalue().encode("utf-8")

    entries = _timed("ledger of 20,000 rows", 20.0, lambda: read_ledger("DOC", "ledger.csv", data))
    assert len(entries) == 20_000
    transactions = _timed(
        "statement of 20,000 rows", 20.0, lambda: read_bank_statement("DOC", "statement.csv", data)
    )
    assert len(transactions) == 20_000
