"""What goes into a report, as plain tables, before any file format.

One builder turns the case's persisted results into a `ReportContent`: a
title block, a summary, and a list of sections that are each a titled table
of strings. The PDF and Excel renderers both walk that structure, so the two
files can never disagree about a figure, and the tests can assert on the
content without parsing a PDF.

Nothing here recomputes or corrects a number. Every value is read off the
review items, flags, Benford result, and audit records exactly as the
deterministic modules produced them and the humans decided them.

Only items carrying an explicit human decision appear as findings. Pending
items are counted and named as pending, never listed as if decided.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from app.shared.schemas import (
    AuditRecord,
    BenfordResult,
    CaseRecord,
    ReviewDecision,
    ReviewItem,
)

__all__ = ["ReportContent", "ReportMeta", "TableSection", "build_report_content"]


@dataclass(frozen=True)
class ReportMeta:
    report_id: str
    client_name: str
    case_id: str
    period_start: date | None
    period_end: date | None
    generated_by: str
    generated_at: datetime


@dataclass(frozen=True)
class TableSection:
    """One titled table. `note` is printed under the title when present."""

    title: str
    columns: list[str]
    rows: list[list[str]]
    note: str | None = None
    #: Relative column widths for the PDF renderer; None means equal widths.
    widths: list[float] | None = None


@dataclass(frozen=True)
class ReportContent:
    meta: ReportMeta
    summary: list[tuple[str, str]]
    sections: list[TableSection]
    closing: str
    #: Counts the record keeps, so the history reads on its own.
    item_count: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    pending_count: int = 0
    flag_count: int = 0
    audit_record_count: int = 0
    excluded_pending_items: list[str] = field(default_factory=list)


CLOSING = (
    "The AI suggests, the human decides. Every match and every flag in this report "
    "was produced by deterministic code from the uploaded documents, and every "
    "verdict was recorded by a named person. Items still awaiting a decision are "
    "counted above and not reported as findings. The audit trail appended here is "
    "the complete, append-only record of the case at the time of generation."
)


def _money(amount: Decimal, currency: str) -> str:
    return f"{currency} {amount:,.2f}"


def _when(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M UTC")


def _period(items: list[ReviewItem], case: CaseRecord) -> tuple[date | None, date | None]:
    dates = [item.ledger_entry.date for item in items]
    if dates:
        return min(dates), max(dates)
    return case.period_start, case.period_end


def _provenance_rows(item: ReviewItem) -> list[list[str]]:
    rows: list[list[str]] = []
    ledger = item.ledger_entry
    rows.append(
        [
            item.review_item_id,
            "Ledger row",
            ledger.source.document_id,
            f"row {ledger.source.row_number}" if ledger.source.row_number else "",
            _money(ledger.amount, ledger.currency),
            "read by pandas, no AI",
        ]
    )
    if item.bank_transaction is not None:
        source = item.bank_transaction.source
        rows.append(
            [
                item.review_item_id,
                "Bank statement",
                source.document_id,
                f"page {source.page}" if source.page else "",
                _money(item.bank_transaction.amount, item.bank_transaction.currency),
                source.text_snippet or "",
            ]
        )
    if item.invoice is not None:
        source = item.invoice.source
        rows.append(
            [
                item.review_item_id,
                f"Invoice {item.invoice.invoice_number}",
                source.document_id,
                f"page {source.page}" if source.page else "",
                _money(item.invoice.amount, item.invoice.currency),
                source.text_snippet or "",
            ]
        )
    for reading in item.evidence:
        locator = (
            f"page {reading.source.page}"
            if reading.source.page
            else f"row {reading.source.row_number}"
            if reading.source.row_number
            else ""
        )
        rows.append(
            [
                item.review_item_id,
                f"AI reading: {reading.field}",
                reading.source.document_id,
                locator,
                "unreadable" if reading.unreadable else str(reading.value),
                f"{reading.source.text_snippet or ''} "
                f"(AI confidence: {reading.extraction_confidence.value})".strip(),
            ]
        )
    return rows


def build_report_content(
    case: CaseRecord,
    items: list[ReviewItem],
    audit: list[AuditRecord],
    benford: BenfordResult | None,
    *,
    report_id: str,
    generated_by: str,
    generated_at: datetime,
) -> ReportContent:
    """Assemble the report from persisted results. Pure; no I/O."""
    decided = [item for item in items if item.decision is not ReviewDecision.PENDING]
    pending = [item for item in items if item.decision is ReviewDecision.PENDING]
    approved = [item for item in decided if item.decision is ReviewDecision.APPROVED]
    rejected = [item for item in decided if item.decision is ReviewDecision.REJECTED]
    all_flags = [flag for item in items for flag in item.flags]
    decided_flags = [(item, flag) for item in decided for flag in item.flags]
    pending_flag_count = sum(len(item.flags) for item in pending)
    period_start, period_end = _period(items, case)

    meta = ReportMeta(
        report_id=report_id,
        client_name=case.client_name,
        case_id=case.case_id,
        period_start=period_start,
        period_end=period_end,
        generated_by=generated_by,
        generated_at=generated_at,
    )

    by_status = {"matched": 0, "partial": 0, "unmatched": 0}
    for item in items:
        by_status[item.match.status.value] += 1
    by_severity = {"high": 0, "medium": 0, "low": 0}
    for flag in all_flags:
        by_severity[flag.severity.value] += 1

    summary: list[tuple[str, str]] = [
        ("Client", case.client_name),
        ("Case", case.case_id),
        (
            "Period covered",
            f"{period_start.isoformat()} to {period_end.isoformat()}"
            if period_start and period_end
            else "not determined",
        ),
        ("Ledger rows reviewed", str(len(items))),
        (
            "Reconciliation",
            f"{by_status['matched']} matched, {by_status['partial']} partial, "
            f"{by_status['unmatched']} unmatched",
        ),
        (
            "Human decisions",
            f"{len(approved)} approved, {len(rejected)} rejected, "
            f"{len(pending)} still pending (not reported as findings)",
        ),
        (
            "Red flags raised",
            f"{len(all_flags)} ({by_severity['high']} high, {by_severity['medium']} "
            f"medium, {by_severity['low']} low); {len(decided_flags)} on decided items, "
            f"{pending_flag_count} on pending items",
        ),
        ("Audit trail entries", str(len(audit))),
        ("Generated by", generated_by),
        ("Generated at", _when(generated_at)),
        ("Report id", report_id),
    ]

    sections: list[TableSection] = []

    sections.append(
        TableSection(
            title="Decided items",
            note=(
                "Each row is one ledger entry with its deterministic match result and "
                "the human decision recorded against it."
                + (
                    f" {len(pending)} item(s) awaiting a decision are excluded: "
                    + ", ".join(item.review_item_id for item in pending) + "."
                    if pending
                    else ""
                )
            ),
            columns=[
                "Item", "Date", "Party", "Amount", "Match", "Strength",
                "Rule", "Decision", "Decided by", "Decided at", "Reason / note",
            ],
            widths=[1.2, 0.9, 1.6, 1.1, 0.8, 0.7, 1.4, 0.8, 1.2, 1.1, 2.2],
            rows=[
                [
                    item.review_item_id,
                    item.ledger_entry.date.isoformat(),
                    item.ledger_entry.party_name,
                    _money(item.ledger_entry.amount, item.ledger_entry.currency),
                    item.match.status.value,
                    item.match.match_strength.value,
                    item.match.rule_id,
                    item.decision.value,
                    item.decided_by or "",
                    _when(item.decided_at),
                    item.rejection_reason or item.match.reason,
                ]
                for item in decided
            ],
        )
    )

    sections.append(
        TableSection(
            title="Red flags on decided items",
            note=(
                "Every rule that fired on a decided item. A flag is a suggestion from "
                "deterministic code; the decision column of the item above is the verdict."
                if decided_flags
                else "No rule fired on any decided item."
            ),
            columns=["Flag", "Item", "Rule", "Severity", "Explanation", "Also involves"],
            widths=[0.9, 1.3, 1.3, 0.8, 4.0, 1.2],
            rows=[
                [
                    flag.flag_id,
                    item.review_item_id,
                    flag.rule_id,
                    flag.severity.value,
                    flag.explanation,
                    ", ".join(flag.related_row_ids),
                ]
                for item, flag in decided_flags
            ],
        )
    )

    sections.append(
        TableSection(
            title="Provenance",
            note=(
                "Where every figure behind a decided item was read from: the document, "
                "the page or spreadsheet row, and the characters as printed."
            ),
            columns=["Item", "Source", "Document", "Location", "Value", "As printed"],
            widths=[1.3, 1.4, 1.3, 0.9, 1.3, 2.6],
            rows=[row for item in decided for row in _provenance_rows(item)],
        )
    )

    if benford is not None and benford.sample_size > 0:
        sections.append(
            TableSection(
                title="Benford's law: first-digit distribution",
                note=(
                    f"Over {benford.sample_size} ledger amounts. Chi-square "
                    f"{benford.chi_square:.2f} on {benford.degrees_of_freedom} degrees of "
                    "freedom; "
                    + (
                        "the distribution deviates significantly from Benford's law."
                        if benford.deviates_significantly
                        else "no significant deviation from Benford's law"
                        + (
                            " (sample too small to conclude either way)."
                            if benford.sample_size < 25
                            else "."
                        )
                    )
                ),
                columns=["Digit", "Observed", "Observed %", "Expected %", "Deviation"],
                rows=[
                    [
                        str(digit.digit),
                        str(digit.observed_count),
                        f"{digit.observed_frequency * 100:.1f}%",
                        f"{digit.expected_frequency * 100:.1f}%",
                        f"{digit.deviation * 100:+.1f} pts",
                    ]
                    for digit in benford.digits
                ],
            )
        )

    sections.append(
        TableSection(
            title="Audit trail",
            note=(
                "Every recorded action on the case, oldest first, as held in the "
                "append-only trail. The generation of this report is recorded after "
                "this snapshot was taken."
            ),
            columns=["When", "Actor type", "Actor", "Action", "Item", "Detail"],
            widths=[1.3, 0.8, 1.6, 1.4, 1.4, 3.4],
            rows=[
                [
                    _when(record.occurred_at),
                    record.actor_type.value,
                    record.actor_id,
                    record.action.value,
                    record.item_id or "",
                    record.detail or "",
                ]
                for record in audit
            ],
        )
    )

    return ReportContent(
        meta=meta,
        summary=summary,
        sections=sections,
        closing=CLOSING,
        item_count=len(items),
        approved_count=len(approved),
        rejected_count=len(rejected),
        pending_count=len(pending),
        flag_count=len(all_flags),
        audit_record_count=len(audit),
        excluded_pending_items=[item.review_item_id for item in pending],
    )
