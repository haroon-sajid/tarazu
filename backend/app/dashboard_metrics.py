"""Derived dashboard figures: readiness, a plain-English summary, and next actions.

All three are **pure functions of already-persisted review items**. They compute
no match, apply no rule, and change no number — they roll up what `matching/`
and `rules/` already decided into something an auditor can read at a glance.
That is why they sit at the app layer beside `pipeline.py` rather than inside a
module: they produce presentation, not audit findings. See
[ADR 0001](../../docs/decisions/0001-http-routers-live-in-app-api.md).

**No AI, and no route to one.** This module imports pandas and the shared
schemas. Every number here is counted, and the same input always produces the
same output — which is what makes these safe to put in front of a human who is
about to sign something.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.shared.schemas import (
    AuditReadiness,
    MatchStatus,
    NextBestAction,
    ReadinessComponent,
    ReviewDecision,
    ReviewItem,
    Severity,
)

__all__ = [
    "COMPLETENESS_FIELDS",
    "READINESS_WEIGHTS",
    "audit_readiness",
    "data_confidence",
    "next_best_actions",
]

#: Equal thirds. Named rather than inlined so the weighting is arguable in
#: review instead of buried in an expression.
READINESS_WEIGHTS = {"matched": 1 / 3, "flags_reviewed": 1 / 3, "completeness": 1 / 3}

#: The ledger fields a row needs before it counts as complete. `date`, `amount`,
#: and `party_name` are structurally required by the schema and so can never be
#: blank; they are listed anyway, because a field that stops being required
#: should start being checked, not silently drop out of the score.
COMPLETENESS_FIELDS = ("date", "amount", "party_name", "description", "account_code")

_SEVERITY_RANK = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}


# --------------------------------------------------------------------------- #
# 1. Audit readiness
# --------------------------------------------------------------------------- #


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_complete(item: ReviewItem) -> bool:
    """A row is complete when nothing about it is missing or unreadable.

    Two ways to fail: a blank ledger field, or an extraction behind the row that
    the model could not read. The second matters as much as the first — a
    missing amount is missing whether the cell was empty or the scan was.
    """
    entry = item.ledger_entry
    if any(_is_blank(getattr(entry, name, None)) for name in COMPLETENESS_FIELDS):
        return False
    return not any(field.unreadable for field in item.evidence)


def _frame(items: list[ReviewItem]) -> pd.DataFrame:
    """One row per review item, with everything the score needs."""
    return pd.DataFrame(
        [
            {
                "review_item_id": item.review_item_id,
                "match_status": item.match.status.value,
                "decided": item.decision is not ReviewDecision.PENDING,
                "flag_count": len(item.flags),
                "complete": _is_complete(item),
            }
            for item in items
        ],
        columns=["review_item_id", "match_status", "decided", "flag_count", "complete"],
    )


def audit_readiness(items: list[ReviewItem]) -> AuditReadiness:
    """Score this case out of 100, and show the three parts it came from.

    - **matched** — ledger rows with a confirmed counterpart. A `partial` match
      does not count: an amount that disagrees with the bank is not reconciled,
      and readiness should say so.
    - **flags_reviewed** — flags sitting on an item a human has decided. A case
      with no flags scores 100 here; there is nothing outstanding.
    - **completeness** — rows with no blank field and no unreadable extraction.

    Args:
        items: The persisted review queue for one case.

    Returns:
        The weighted score plus each component with its own counts, so the
        frontend can show a breakdown and the auditor can see what is dragging.
    """
    frame = _frame(items)
    total = len(frame)

    if total == 0:
        empty = ReadinessComponent.of(0, 0)
        return AuditReadiness(
            score=0, matched=empty, flags_reviewed=empty, completeness=empty
        )

    matched = ReadinessComponent.of(
        int((frame["match_status"] == MatchStatus.MATCHED.value).sum()), total
    )
    flags_total = int(frame["flag_count"].sum())
    flags_reviewed = ReadinessComponent.of(
        int(frame.loc[frame["decided"], "flag_count"].sum()), flags_total
    )
    completeness = ReadinessComponent.of(int(frame["complete"].sum()), total)

    score = (
        matched.percent * READINESS_WEIGHTS["matched"]
        + flags_reviewed.percent * READINESS_WEIGHTS["flags_reviewed"]
        + completeness.percent * READINESS_WEIGHTS["completeness"]
    )
    return AuditReadiness(
        score=round(score),
        matched=matched,
        flags_reviewed=flags_reviewed,
        completeness=completeness,
    )


# --------------------------------------------------------------------------- #
# 2. Data confidence
# --------------------------------------------------------------------------- #


def _describe_period(period_start: date | None, period_end: date | None) -> str | None:
    """Say how much data this is, in the unit a person would use."""
    if period_start is None or period_end is None or period_end < period_start:
        return None
    days = (period_end - period_start).days + 1  # inclusive
    if days >= 25:
        months = max(1, round(days / 30.44))
        return f"{months} month" + ("s" if months > 1 else "")
    if days >= 11:
        weeks = max(1, round(days / 7))
        return f"{weeks} week" + ("s" if weeks > 1 else "")
    return f"{days} day" + ("s" if days > 1 else "")


def data_confidence(
    items: list[ReviewItem],
    period_start: date | None = None,
    period_end: date | None = None,
) -> str:
    """One sentence saying what this case amounts to so far.

    Built entirely from counts. It never characterises the data as reliable or
    unreliable — it states what is there and what is outstanding, and lets the
    auditor draw the conclusion.

    Examples::

        "Based on 1 month of data, 3 unmatched items remain."
        "Based on 2 weeks of data, every ledger row has supporting evidence."
        "No data yet. Upload a bank statement, invoices, and a ledger to begin."
    """
    if not items:
        return "No data yet. Upload a bank statement, invoices, and a ledger to begin."

    unmatched = sum(1 for item in items if item.match.status is MatchStatus.UNMATCHED)
    partial = sum(1 for item in items if item.match.status is MatchStatus.PARTIAL)
    period = _describe_period(period_start, period_end)
    opening = f"Based on {period} of data" if period else f"Based on {len(items)} ledger rows"

    if unmatched == 0 and partial == 0:
        return f"{opening}, every ledger row has supporting evidence."

    outstanding: list[str] = []
    if unmatched:
        outstanding.append(f"{unmatched} unmatched item" + ("s" if unmatched > 1 else ""))
    if partial:
        outstanding.append(
            f"{partial} partial match" + ("es" if partial > 1 else "")
        )
    verb = "remain" if _is_plural(unmatched, partial) else "remains"
    return f"{opening}, {' and '.join(outstanding)} {verb}."


def _is_plural(unmatched: int, partial: int) -> bool:
    """Two clauses always take a plural verb; one clause follows its own count."""
    if unmatched and partial:
        return True
    return max(unmatched, partial) > 1


# --------------------------------------------------------------------------- #
# 3. Next best actions
# --------------------------------------------------------------------------- #

#: One phrasing per rule. Unknown rules fall back to a generic wording rather
#: than being dropped, because `rules/` is owned by someone else and will grow
#: rules this file has not heard of.
_ACTION_TEMPLATES: dict[str, str] = {
    "structuring": "Review the structuring flag on {party}",
    "duplicate-invoice": "Check the duplicate payment to {party}",
    "near-limit": "Confirm the near-limit payment to {party}",
    "weekend-entry": "Confirm the weekend entry for {party}",
    "round-number": "Sanity-check the round payment to {party}",
    "invoice-sequence-gap": "Explain the invoice sequence gap for {party}",
    "midnight-entry": "Confirm the after-hours entry for {party}",
}


def _phrase(rule_id: str, party_name: str) -> str:
    template = _ACTION_TEMPLATES.get(rule_id)
    if template is None:
        readable = rule_id.replace("-", " ").replace("_", " ")
        template = f"Review the {readable} flag on {{party}}"
    return template.format(party=party_name)


def next_best_actions(items: list[ReviewItem], limit: int = 5) -> list[NextBestAction]:
    """The most severe outstanding flags, reworded as work to do.

    Three decisions worth knowing about:

    - **Decided items are excluded.** An action list that tells an auditor to
      review something they already approved is noise, not a queue.
    - **Flags spanning rows are collapsed.** Structuring and duplicate-payment
      rules fire once per row involved, so one issue would otherwise eat two of
      the five slots. Flags naming the same rule and the same set of rows count
      as one action.
    - **Ties break on amount, largest first.** Among equally severe flags, the
      bigger number is the one to look at first.

    Args:
        items: The persisted review queue.
        limit: How many actions to return. Five by default.

    Returns:
        At most `limit` actions, most severe first, each linked to its item.
    """
    by_ledger_row = {item.ledger_entry.ledger_row_id: item for item in items}

    seen: set[tuple[str, tuple[str, ...]]] = set()
    candidates: list[tuple[int, float, str, NextBestAction]] = []

    for item in items:
        if item.decision is not ReviewDecision.PENDING:
            continue
        for flag in item.flags:
            involved = tuple(sorted({flag.source_row_id, *flag.related_row_ids}))
            key = (flag.rule_id, involved)
            if key in seen:
                continue
            seen.add(key)

            source = by_ledger_row.get(flag.source_row_id, item)
            party = source.ledger_entry.party_name
            candidates.append(
                (
                    _SEVERITY_RANK[flag.severity],
                    -float(source.ledger_entry.amount),
                    item.review_item_id,
                    NextBestAction(
                        action=_phrase(flag.rule_id, party),
                        severity=flag.severity,
                        rule_id=flag.rule_id,
                        review_item_id=item.review_item_id,
                        party_name=party,
                    ),
                )
            )

    candidates.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
    return [action for *_, action in candidates[:limit]]
