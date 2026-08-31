"""Steps 2 and 3 of the Ask Tarazu pipeline: plan the query, run it in code.

Every function here takes the persisted review items (and the stored Benford
result) and returns a `QueryResult`: the structured values the composer will
word, the `AssistantFact`s a reader can check the prose against, and the
items and flags involved, from which citations are drawn.

All arithmetic is Python `Decimal` over figures the deterministic modules
already produced — counting items, summing ledger amounts, grouping by month
or party. No model is involved anywhere in this file, and nothing here is
influenced by an extraction confidence.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Sequence

from app.modules.assistant.concepts import CONCEPTS
from app.modules.assistant.planner import Plan
from app.shared.api import UploadedDocument
from app.shared.schemas import (
    AssistantCitation,
    AssistantFact,
    AssistantIntent,
    AuditRecord,
    BenfordResult,
    CaseRecord,
    Confidence,
    DocumentType,
    ExtractionResult,
    Flag,
    MatchStatus,
    Provenance,
    ReportRecord,
    ReviewDecision,
    ReviewItem,
    Severity,
)
from app.shared.text import normalise_party_name, normalise_reference

__all__ = ["CaseOverview", "QueryResult", "RULE_DESCRIPTIONS", "WorkspaceContext", "execute", "money"]

#: How many rows a listing answer prints before saying "and N more". The
#: counts and totals above the list always cover every row.
LIST_CAP = 25


@dataclass
class QueryResult:
    grounded: bool = True
    answer_confidence: Confidence = Confidence.HIGH
    data: dict[str, Any] = field(default_factory=dict)
    facts: list[AssistantFact] = field(default_factory=list)
    items: list[ReviewItem] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    #: Citations the query built itself, for answers that rest on a document
    #: region rather than on a review item's ledger row (what the vision model
    #: read, for instance). Empty for every query that lets `service` build
    #: citations from `items` and `flags`.
    citations: list[AssistantCitation] = field(default_factory=list)

    def fact(self, label: str, value: object) -> None:
        self.facts.append(AssistantFact(label=label, value=str(value)))


@dataclass(frozen=True)
class CaseOverview:
    """One engagement of this organization, with the counts that describe it.

    Built by the route from org-scoped repository reads: every number here was
    counted from that case's own persisted review items.
    """

    case: CaseRecord
    total_items: int
    pending: int
    approved: int
    rejected: int
    flags: int


@dataclass(frozen=True)
class WorkspaceContext:
    """The rest of the engagement's persisted record, read-only.

    The review queue and the Benford result travel as their own arguments —
    they were the assistant's whole world once. Everything else it may now be
    asked about arrives here: the uploaded documents, what the vision model
    read from them, the decisions already taken, the generated reports, the
    case's audit trail, and one overview row per engagement in the
    organization. All of it org-scoped before it reached this object, and
    none of it a document's bytes — the extractions *are* the read of the
    documents, with the provenance to check it.
    """

    documents: Sequence[UploadedDocument] = ()
    extractions: Sequence[ExtractionResult] = ()
    reports: Sequence[ReportRecord] = ()
    trail: Sequence[AuditRecord] = ()
    cases: Sequence[CaseOverview] = ()
    #: Which of `cases` the workspace is in, so an org-wide answer can say so.
    active_case_id: str | None = None


#: What each rule means, in one sentence, for the explanation intents. Plain
#: text kept beside the data it describes, not generated.
RULE_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "structuring": {
        "en": "Structuring means splitting one payment into several, each under an approval limit but together over it, so no single payment needs the sign-off the whole would.",
        "ur": "سٹرکچرنگ کا مطلب ہے ایک ادائیگی کو کئی حصوں میں بانٹنا، ہر حصہ منظوری کی حد سے نیچے مگر مجموعی طور پر حد سے اوپر، تاکہ کسی ایک ادائیگی کو وہ منظوری نہ لینی پڑے جو پوری رقم کو لینی پڑتی۔",
    },
    "weekend-entry": {
        "en": "A weekend entry is a payment dated on a Saturday or Sunday, which is unusual for a regular payment cycle and worth confirming with the bank date.",
        "ur": "ویک اینڈ انٹری وہ ادائیگی ہے جس کی تاریخ ہفتہ یا اتوار کی ہے، جو معمول کے ادائیگی کے چکر میں غیر معمولی ہے اور بینک کی تاریخ سے تصدیق کے لائق ہے۔",
    },
    "round-number": {
        "en": "A round-number flag marks an amount that is an exact multiple of 1,000. On its own it is a weak signal - advances and rent are often round - so it is informational.",
        "ur": "راؤنڈ نمبر کا نشان ایسی رقم پر لگتا ہے جو 1,000 کا پورا ضرب ہو۔ اکیلے یہ کمزور اشارہ ہے، کیونکہ ایڈوانس اور کرایہ اکثر گول رقم میں ہوتے ہیں، اس لیے یہ صرف معلوماتی ہے۔",
    },
    "near-limit": {
        "en": "A near-limit flag marks an amount sitting within 2% below an approval limit - the pattern of a payment sized to avoid a second signature.",
        "ur": "حد کے قریب کا نشان ایسی رقم پر لگتا ہے جو منظوری کی حد سے 2% کے اندر نیچے ہو، جو دوسری دستخط سے بچنے کے لیے رقم طے کرنے کا نمونہ ہو سکتا ہے۔",
    },
    "duplicate-invoice": {
        "en": "A duplicate-invoice flag means one invoice is matched to two or more ledger payments - the same bill settled more than once.",
        "ur": "ڈپلیکیٹ انوائس کا نشان اس وقت لگتا ہے جب ایک ہی انوائس دو یا زیادہ لیجر ادائیگیوں سے ملتی ہو، یعنی ایک ہی بل ایک سے زیادہ بار ادا ہوا۔",
    },
    "duplicate-payment": {
        "en": "A duplicate-payment flag means the same party received the same amount within a few days - a double-posted entry or a repeated payment.",
        "ur": "ڈپلیکیٹ ادائیگی کا نشان اس وقت لگتا ہے جب ایک ہی فریق کو چند دنوں کے اندر ایک ہی رقم ملی ہو، یعنی دوہری اندراج یا دہرائی گئی ادائیگی۔",
    },
    "invoice-sequence-gap": {
        "en": "An invoice-sequence-gap flag means a vendor's invoice numbers skip values among the uploaded documents. The missing numbers may be invoices to other customers, or invoices the client did not provide.",
        "ur": "انوائس نمبروں میں خلا کا نشان اس وقت لگتا ہے جب کسی وینڈر کے انوائس نمبر اپ لوڈ شدہ دستاویزات میں ترتیب چھوڑ جائیں۔ غائب نمبر دوسرے گاہکوں کی انوائسز بھی ہو سکتے ہیں یا وہ جو کلائنٹ نے فراہم نہیں کیں۔",
    },
}

_SEVERITY_RANK = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}


def money(amount: Decimal, currency: str = "PKR") -> str:
    return f"{currency} {amount:,.2f}"


def _currency(items: list[ReviewItem]) -> str:
    return items[0].ledger_entry.currency if items else "PKR"


def _row(item: ReviewItem) -> dict[str, Any]:
    return {
        "review_item_id": item.review_item_id,
        "party": item.ledger_entry.party_name,
        "amount": item.ledger_entry.amount,
        "currency": item.ledger_entry.currency,
        "date": item.ledger_entry.date,
        "status": item.match.status.value,
        "strength": item.match.match_strength.value,
        "reason": item.match.reason,
        "decision": item.decision.value,
        "flags": [flag.rule_id for flag in item.flags],
    }


# --------------------------------------------------------------------------- #
# The queries
# --------------------------------------------------------------------------- #


def _summary(items: list[ReviewItem], benford: BenfordResult | None) -> QueryResult:
    result = QueryResult()
    by_status = {status: 0 for status in MatchStatus}
    by_decision = {decision: 0 for decision in ReviewDecision}
    by_severity = {severity: 0 for severity in Severity}
    for item in items:
        by_status[item.match.status] += 1
        by_decision[item.decision] += 1
        for flag in item.flags:
            by_severity[flag.severity] += 1
    flagged = [item for item in items if item.flags]
    total = sum((item.ledger_entry.amount for item in items), Decimal(0))
    result.data = {
        "total_items": len(items),
        "matched": by_status[MatchStatus.MATCHED],
        "partial": by_status[MatchStatus.PARTIAL],
        "unmatched": by_status[MatchStatus.UNMATCHED],
        "approved": by_decision[ReviewDecision.APPROVED],
        "rejected": by_decision[ReviewDecision.REJECTED],
        "pending": by_decision[ReviewDecision.PENDING],
        "flagged_items": len(flagged),
        "total_flags": sum(by_severity.values()),
        "high": by_severity[Severity.HIGH],
        "medium": by_severity[Severity.MEDIUM],
        "low": by_severity[Severity.LOW],
        "total_amount": total,
        "currency": _currency(items),
        "benford_available": benford is not None and benford.sample_size > 0,
    }
    result.fact("Ledger rows reviewed", len(items))
    result.fact("Matched / partial / unmatched", f"{result.data['matched']} / {result.data['partial']} / {result.data['unmatched']}")
    result.fact("Approved / rejected / pending", f"{result.data['approved']} / {result.data['rejected']} / {result.data['pending']}")
    result.fact("Flags (high / medium / low)", f"{result.data['total_flags']} ({result.data['high']} / {result.data['medium']} / {result.data['low']})")
    result.fact("Total of ledger rows", money(total, result.data["currency"]))
    result.items = flagged[:5]
    result.flags = [flag for item in flagged for flag in item.flags][:5]
    return result


def _unmatched(items: list[ReviewItem]) -> QueryResult:
    result = QueryResult()
    unmatched = [item for item in items if item.match.status is MatchStatus.UNMATCHED]
    total = sum((item.ledger_entry.amount for item in unmatched), Decimal(0))
    result.data = {"rows": [_row(item) for item in unmatched], "total": total, "currency": _currency(items)}
    result.fact("Unmatched items", len(unmatched))
    result.fact("Total of unmatched items", money(total, result.data["currency"]))
    for item in unmatched:
        result.fact(item.ledger_entry.party_name, f"{money(item.ledger_entry.amount, item.ledger_entry.currency)} on {item.ledger_entry.date.isoformat()} ({item.review_item_id})")
    result.items = unmatched
    return result


def _missing_evidence(items: list[ReviewItem]) -> QueryResult:
    """Rows with nothing independent behind them, and rows with an unreadable reading."""
    result = QueryResult()
    no_counterpart = [item for item in items if item.match.status is MatchStatus.UNMATCHED]
    invoice_only = [item for item in items if item.match.rule_id.startswith("invoice-only")]
    unreadable = [item for item in items if any(field.unreadable for field in item.evidence)]
    rows = []
    seen: set[str] = set()
    for group, label in ((no_counterpart, "no bank payment and no invoice"), (invoice_only, "invoice but no bank payment"), (unreadable, "an unreadable value in the source")):
        for item in group:
            if item.review_item_id in seen:
                continue
            seen.add(item.review_item_id)
            rows.append({**_row(item), "gap": label})
    result.data = {"rows": rows, "no_counterpart": len(no_counterpart), "invoice_only": len(invoice_only), "unreadable": len(unreadable)}
    result.fact("Rows with no bank payment and no invoice", len(no_counterpart))
    result.fact("Rows with an invoice but no bank payment", len(invoice_only))
    result.fact("Rows with an unreadable source value", len(unreadable))
    result.items = [item for item in items if item.review_item_id in seen]
    return result


def _flags(items: list[ReviewItem]) -> QueryResult:
    result = QueryResult()
    flagged = [item for item in items if item.flags]
    all_flags = [(item, flag) for item in flagged for flag in item.flags]
    by_severity = {severity: 0 for severity in Severity}
    by_rule: dict[str, int] = defaultdict(int)
    for _item, flag in all_flags:
        by_severity[flag.severity] += 1
        by_rule[flag.rule_id] += 1
    ordered = sorted(all_flags, key=lambda pair: (_SEVERITY_RANK[pair[1].severity], -pair[0].ledger_entry.amount, pair[0].review_item_id))
    result.data = {
        "total_flags": len(all_flags),
        "flagged_items": len(flagged),
        "high": by_severity[Severity.HIGH],
        "medium": by_severity[Severity.MEDIUM],
        "low": by_severity[Severity.LOW],
        "rules": dict(sorted(by_rule.items(), key=lambda kv: (-kv[1], kv[0]))),
        "top": [{**_row(item), "rule_id": flag.rule_id, "severity": flag.severity.value, "explanation": flag.explanation} for item, flag in ordered[:5]],
    }
    result.fact("Flags raised", len(all_flags))
    result.fact("Items flagged", len(flagged))
    result.fact("By severity (high / medium / low)", f"{by_severity[Severity.HIGH]} / {by_severity[Severity.MEDIUM]} / {by_severity[Severity.LOW]}")
    for rule_id, count in result.data["rules"].items():
        result.fact(f"Rule {rule_id}", count)
    result.items = [item for item, _flag in ordered[:5]]
    result.flags = [flag for _item, flag in ordered[:5]]
    return result


def _rule(items: list[ReviewItem], rule_id: str) -> QueryResult:
    result = QueryResult()
    pairs = [(item, flag) for item in items for flag in item.flags if flag.rule_id == rule_id]
    # A flag spanning rows fires once per row; word the shared explanation once.
    seen_explanations: set[str] = set()
    rows = []
    for item, flag in pairs:
        rows.append({**_row(item), "explanation": flag.explanation, "severity": flag.severity.value, "first": flag.explanation not in seen_explanations})
        seen_explanations.add(flag.explanation)
    result.data = {"rule_id": rule_id, "rows": rows, "count": len(pairs)}
    result.fact(f"Items flagged by {rule_id}", len(pairs))
    for item, flag in pairs:
        result.fact(item.ledger_entry.party_name, f"{money(item.ledger_entry.amount, item.ledger_entry.currency)} ({item.review_item_id}): {flag.explanation}")
    result.items = [item for item, _flag in pairs]
    result.flags = [flag for _item, flag in pairs]
    return result


def _duplicates(items: list[ReviewItem]) -> QueryResult:
    result = QueryResult()
    pairs = [(item, flag) for item in items for flag in item.flags if flag.rule_id in ("duplicate-invoice", "duplicate-payment")]
    rows = [{**_row(item), "rule_id": flag.rule_id, "explanation": flag.explanation} for item, flag in pairs]
    result.data = {"rows": rows, "count": len(pairs)}
    result.fact("Duplicate flags", len(pairs))
    for item, flag in pairs:
        result.fact(item.ledger_entry.party_name, f"{money(item.ledger_entry.amount, item.ledger_entry.currency)} ({item.review_item_id}): {flag.explanation}")
    result.items = [item for item, _flag in pairs]
    result.flags = [flag for _item, flag in pairs]
    return result


def _party(items: list[ReviewItem], party: str) -> QueryResult:
    result = QueryResult(answer_confidence=Confidence.HIGH)
    key = normalise_party_name(party)
    matched = [item for item in items if normalise_party_name(item.ledger_entry.party_name) == key]
    total = sum((item.ledger_entry.amount for item in matched), Decimal(0))
    result.data = {"party": party, "rows": [_row(item) for item in matched], "count": len(matched), "total": total, "currency": _currency(matched or items)}
    result.fact(f"Payments to {party}", len(matched))
    result.fact(f"Total paid to {party}", money(total, result.data["currency"]))
    for item in matched:
        result.fact(item.review_item_id, f"{money(item.ledger_entry.amount, item.ledger_entry.currency)} on {item.ledger_entry.date.isoformat()}, {item.match.status.value}, decision {item.decision.value}")
    result.items = matched
    result.flags = [flag for item in matched for flag in item.flags]
    return result


def _totals(items: list[ReviewItem]) -> QueryResult:
    result = QueryResult()
    currency = _currency(items)
    total = sum((item.ledger_entry.amount for item in items), Decimal(0))
    by_status = {status: Decimal(0) for status in MatchStatus}
    for item in items:
        by_status[item.match.status] += item.ledger_entry.amount
    dates = [item.ledger_entry.date for item in items]
    largest = max(items, key=lambda item: (item.ledger_entry.amount, item.review_item_id), default=None)
    result.data = {
        "total": total, "count": len(items), "currency": currency,
        "matched_total": by_status[MatchStatus.MATCHED],
        "partial_total": by_status[MatchStatus.PARTIAL],
        "unmatched_total": by_status[MatchStatus.UNMATCHED],
        "period_start": min(dates) if dates else None,
        "period_end": max(dates) if dates else None,
        "largest": _row(largest) if largest else None,
    }
    result.fact("Total of all ledger rows", money(total, currency))
    result.fact("Rows", len(items))
    result.fact("Total of matched rows", money(by_status[MatchStatus.MATCHED], currency))
    result.fact("Total of partial rows", money(by_status[MatchStatus.PARTIAL], currency))
    result.fact("Total of unmatched rows", money(by_status[MatchStatus.UNMATCHED], currency))
    if largest:
        result.fact("Largest single row", f"{money(largest.ledger_entry.amount, currency)} to {largest.ledger_entry.party_name} ({largest.review_item_id})")
    result.items = [largest] if largest else []
    return result


def _top_vendors(items: list[ReviewItem], limit: int) -> QueryResult:
    result = QueryResult()
    totals: dict[str, Decimal] = defaultdict(Decimal)
    counts: dict[str, int] = defaultdict(int)
    names: dict[str, str] = {}
    for item in items:
        key = normalise_party_name(item.ledger_entry.party_name)
        totals[key] += item.ledger_entry.amount
        counts[key] += 1
        names.setdefault(key, item.ledger_entry.party_name)
    grand = sum(totals.values(), Decimal(0))
    ranked = sorted(totals, key=lambda key: (-totals[key], key))[:limit]
    rows = [
        {"party": names[key], "total": totals[key], "count": counts[key],
         "share": (totals[key] / grand * 100) if grand else Decimal(0)}
        for key in ranked
    ]
    result.data = {"rows": rows, "grand_total": grand, "currency": _currency(items), "vendors": len(totals)}
    result.fact("Distinct parties", len(totals))
    for row in rows:
        result.fact(row["party"], f"{money(row['total'], result.data['currency'])} over {row['count']} payment(s), {row['share']:.1f}% of the total")
    top_keys = set(ranked)
    result.items = [item for item in items if normalise_party_name(item.ledger_entry.party_name) in top_keys][:8]
    return result


def _largest(items: list[ReviewItem], limit: int) -> QueryResult:
    result = QueryResult()
    ranked = sorted(items, key=lambda item: (-item.ledger_entry.amount, item.review_item_id))[:limit]
    result.data = {"rows": [_row(item) for item in ranked], "currency": _currency(items)}
    for item in ranked:
        result.fact(item.ledger_entry.party_name, f"{money(item.ledger_entry.amount, item.ledger_entry.currency)} on {item.ledger_entry.date.isoformat()} ({item.review_item_id}), {item.match.status.value}")
    result.items = ranked
    return result


def _compare_months(items: list[ReviewItem]) -> QueryResult:
    result = QueryResult()
    totals: dict[str, Decimal] = defaultdict(Decimal)
    counts: dict[str, int] = defaultdict(int)
    unmatched: dict[str, int] = defaultdict(int)
    flagged: dict[str, int] = defaultdict(int)
    for item in items:
        key = item.ledger_entry.date.strftime("%Y-%m")
        totals[key] += item.ledger_entry.amount
        counts[key] += 1
        if item.match.status is MatchStatus.UNMATCHED:
            unmatched[key] += 1
        if item.flags:
            flagged[key] += 1
    months = sorted(totals)
    rows = []
    previous: Decimal | None = None
    for key in months:
        change = None if previous is None else totals[key] - previous
        rows.append({"month": key, "total": totals[key], "count": counts[key], "unmatched": unmatched[key], "flagged": flagged[key], "change": change})
        previous = totals[key]
    result.data = {"rows": rows, "currency": _currency(items)}
    result.answer_confidence = Confidence.HIGH if len(months) > 1 else Confidence.MEDIUM
    for row in rows:
        change = "" if row["change"] is None else f", {'+' if row['change'] >= 0 else '-'}{money(abs(row['change']), result.data['currency'])} on the month before"
        result.fact(row["month"], f"{money(row['total'], result.data['currency'])} over {row['count']} row(s), {row['unmatched']} unmatched, {row['flagged']} flagged{change}")
    return result


def _search_amount(items: list[ReviewItem], amount: Decimal) -> QueryResult:
    result = QueryResult()
    exact = [item for item in items if abs(item.ledger_entry.amount) == amount]
    near = [
        item for item in items
        if item not in exact and abs(abs(item.ledger_entry.amount) - amount) <= amount * Decimal("0.01")
    ]
    bank_side = [
        item for item in items
        if item.bank_transaction is not None and abs(item.bank_transaction.amount) == amount and item not in exact
    ]
    result.data = {"amount": amount, "exact": [_row(item) for item in exact], "near": [_row(item) for item in near], "bank": [_row(item) for item in bank_side], "currency": _currency(items)}
    result.fact(f"Ledger rows of exactly {money(amount, result.data['currency'])}", len(exact))
    result.fact("Ledger rows within 1%", len(near))
    result.fact("Bank lines of that amount on other rows", len(bank_side))
    for item in exact + near + bank_side:
        result.fact(item.ledger_entry.party_name, f"{money(item.ledger_entry.amount, item.ledger_entry.currency)} on {item.ledger_entry.date.isoformat()} ({item.review_item_id}), {item.match.status.value}")
    result.items = exact + near + bank_side
    return result


def _benford(benford: BenfordResult | None) -> QueryResult:
    result = QueryResult(answer_confidence=Confidence.MEDIUM)
    if benford is None or benford.sample_size == 0:
        result.data = {"available": False}
        result.fact("Benford analysis", "not computed for this case")
        return result
    worst = max(benford.digits, key=lambda digit: (abs(digit.deviation), -digit.digit))
    result.data = {
        "available": True,
        "sample_size": benford.sample_size,
        "chi_square": benford.chi_square,
        "degrees_of_freedom": benford.degrees_of_freedom,
        "deviates": benford.deviates_significantly,
        "worst_digit": worst.digit,
        "worst_observed": worst.observed_frequency,
        "worst_expected": worst.expected_frequency,
        "small_sample": benford.sample_size < 25,
    }
    result.fact("Amounts analysed", benford.sample_size)
    result.fact("Chi-square", f"{benford.chi_square:.2f} on {benford.degrees_of_freedom} degrees of freedom")
    result.fact("Deviates significantly", "yes" if benford.deviates_significantly else "no")
    result.fact(f"Digit furthest from expectation: {worst.digit}", f"observed {worst.observed_frequency * 100:.1f}% vs expected {worst.expected_frequency * 100:.1f}%")
    return result


# --------------------------------------------------------------------------- #
# The results row by row, and the evidence behind them
#
# The queries above answer *about* the case; these answer *from* it: how each
# row reconciled, one row by its identifier, the invoices and bank lines the
# rows rest on, every row listed, a day or month, and how confidently the
# evidence was read. Still counting and formatting over persisted rows — no
# model, no document bytes.
# --------------------------------------------------------------------------- #

_CONFIDENCE_RANK = {Confidence.HIGH: 0, Confidence.MEDIUM: 1, Confidence.LOW: 2}


def _suffix_number(identifier: str) -> int | None:
    digits = re.search(r"(\d+)$", identifier)
    return int(digits.group(1)) if digits else None


def _cite(source: Provenance, review_item_id: str | None) -> AssistantCitation:
    return AssistantCitation(
        document_id=source.document_id, page=source.page, row_number=source.row_number,
        text_snippet=source.text_snippet, review_item_id=review_item_id,
    )


def _bank_dict(item: ReviewItem) -> dict[str, Any] | None:
    bank = item.bank_transaction
    if bank is None:
        return None
    return {
        "bank_row_id": bank.bank_row_id, "date": bank.date, "amount": bank.amount,
        "currency": bank.currency, "description": bank.description, "balance": bank.balance,
        "page": bank.source.page, "document_id": bank.source.document_id,
    }


def _invoice_dict(item: ReviewItem) -> dict[str, Any] | None:
    invoice = item.invoice
    if invoice is None:
        return None
    return {
        "invoice_id": invoice.invoice_id, "number": invoice.invoice_number, "date": invoice.date,
        "amount": invoice.amount, "currency": invoice.currency, "party": invoice.party_name,
        "page": invoice.source.page, "document_id": invoice.source.document_id,
        "snippet": invoice.source.text_snippet,
    }


def _weakest_reading(item: ReviewItem) -> dict[str, Any] | None:
    """The evidence reading that set the item's rolled-up confidence."""
    weakest = min(
        item.evidence,
        key=lambda reading: (0 if reading.unreadable else 1, -_CONFIDENCE_RANK[reading.extraction_confidence]),
        default=None,
    )
    if weakest is None:
        return None
    return {
        "field": weakest.field, "value": None if weakest.unreadable else weakest.value,
        "unreadable": weakest.unreadable, "confidence": weakest.extraction_confidence.value,
        "document_id": weakest.source.document_id, "page": weakest.source.page,
        "row_number": weakest.source.row_number,
    }


def _detail(item: ReviewItem) -> dict[str, Any]:
    """Everything the review screen knows about one row, for the item answer."""
    ledger = item.ledger_entry
    return {
        **_row(item),
        "ledger_row_id": ledger.ledger_row_id,
        "row_number": ledger.source.row_number,
        "document_id": ledger.source.document_id,
        "description": ledger.description,
        "account": ledger.account_code,
        "rule_id": item.match.rule_id,
        "bank": _bank_dict(item),
        "invoice": _invoice_dict(item),
        "flag_rows": [
            {"rule_id": flag.rule_id, "severity": flag.severity.value, "explanation": flag.explanation}
            for flag in item.flags
        ],
        "confidence": item.extraction_confidence.value,
        "readings": len(item.evidence),
        "unreadable": sum(1 for reading in item.evidence if reading.unreadable),
        "weakest": _weakest_reading(item),
        "decided_by": item.decided_by,
        "decided_at": item.decided_at.strftime("%Y-%m-%d %H:%M") if item.decided_at else None,
        "rejection_reason": item.rejection_reason,
    }


def _item_citations(items: Sequence[ReviewItem]) -> list[AssistantCitation]:
    """The ledger row, the bank line, the invoice, and the flags behind each item."""
    citations: list[AssistantCitation] = []
    for item in items:
        citations.append(_cite(item.ledger_entry.source, item.review_item_id))
        if item.bank_transaction is not None:
            citations.append(_cite(item.bank_transaction.source, item.review_item_id))
        if item.invoice is not None:
            citations.append(_cite(item.invoice.source, item.review_item_id))
        for flag in item.flags:
            if flag.source is not None:
                citations.append(_cite(flag.source, item.review_item_id))
    return citations


def _counterpart(item: ReviewItem) -> str:
    parts = []
    if item.bank_transaction is not None:
        bank = item.bank_transaction
        page = f", p.{bank.source.page}" if bank.source.page else ""
        parts.append(f"bank line {bank.bank_row_id} ({bank.date.isoformat()}{page})")
    if item.invoice is not None:
        parts.append(f"invoice {item.invoice.invoice_number}")
    return "; ".join(parts) if parts else "no bank line and no invoice"


def _matches(items: list[ReviewItem], status: MatchStatus | None) -> QueryResult:
    result = QueryResult()
    chosen = [item for item in items if status is None or item.match.status is status]
    by_status = Counter(item.match.status for item in items)
    by_strength = Counter(item.match.match_strength.value for item in chosen)
    total = sum((item.ledger_entry.amount for item in chosen), Decimal(0))
    ordered = sorted(chosen, key=lambda item: (item.ledger_entry.date, item.review_item_id))
    rows = [
        {**_row(item), "rule_id": item.match.rule_id, "bank": _bank_dict(item),
         "invoice": _invoice_dict(item), "counterpart": _counterpart(item)}
        for item in ordered
    ]
    result.data = {
        "status": status.value if status else None,
        "rows": rows[:LIST_CAP], "count": len(chosen), "more": max(0, len(chosen) - LIST_CAP),
        "total": total, "currency": _currency(items), "total_items": len(items),
        "matched": by_status[MatchStatus.MATCHED], "partial": by_status[MatchStatus.PARTIAL],
        "unmatched": by_status[MatchStatus.UNMATCHED],
        "high": by_strength["high"], "medium": by_strength["medium"], "low": by_strength["low"],
    }
    result.fact("Match results (matched / partial / unmatched)", f"{by_status[MatchStatus.MATCHED]} / {by_status[MatchStatus.PARTIAL]} / {by_status[MatchStatus.UNMATCHED]}")
    result.fact("Rows in this answer", len(chosen))
    result.fact("Total of those rows", money(total, result.data["currency"]))
    result.fact("Match strength (high / medium / low)", f"{by_strength['high']} / {by_strength['medium']} / {by_strength['low']}")
    for item in ordered[:LIST_CAP]:
        result.fact(
            item.review_item_id,
            f"{item.ledger_entry.party_name}, {money(item.ledger_entry.amount, item.ledger_entry.currency)} on "
            f"{item.ledger_entry.date.isoformat()}: {item.match.status.value} ({item.match.match_strength.value}) "
            f"by {item.match.rule_id} — {_counterpart(item)}",
        )
    result.items = ordered[:LIST_CAP]
    result.citations = _item_citations(ordered[:8])
    return result


def _reference_label(reference: str) -> str:
    if ":" in reference:
        kind, digits = reference.split(":", 1)
        return {"ITEM": f"item {digits}", "ROW": f"row {digits}", "INVOICE": f"invoice {digits}",
                "FLAG": f"flag {digits}"}.get(kind, reference)
    return reference


def _find_items(items: list[ReviewItem], reference: str) -> list[ReviewItem]:
    """The rows an identifier names. Exact on any id the row carries; by
    number for "item 5", "row 16" (sheet row or ledger row), "invoice 0087"
    (an invoice number ending in those digits), "flag 9"."""
    if ":" in reference:
        kind, digits = reference.split(":", 1)
        number = int(digits) if digits.isdigit() else None
        hits = []
        for item in items:
            if kind == "ITEM" and _suffix_number(item.review_item_id) == number:
                hits.append(item)
            elif kind == "ROW" and number is not None and (
                item.ledger_entry.source.row_number == number
                or _suffix_number(item.ledger_entry.ledger_row_id) == number
            ):
                hits.append(item)
            elif kind == "INVOICE" and item.invoice is not None and (
                normalise_reference(item.invoice.invoice_number).endswith(digits)
                or normalise_reference(item.invoice.invoice_id).endswith(digits)
            ):
                hits.append(item)
            elif kind == "FLAG" and any(_suffix_number(flag.flag_id) == number for flag in item.flags):
                hits.append(item)
        return hits
    wanted = normalise_reference(reference)
    if not wanted:
        return []
    hits = []
    for item in items:
        identifiers = {item.review_item_id, item.ledger_entry.ledger_row_id, item.ledger_entry.source.document_id}
        if item.bank_transaction is not None:
            identifiers |= {item.bank_transaction.bank_row_id, item.bank_transaction.source.document_id}
        if item.invoice is not None:
            identifiers |= {item.invoice.invoice_id, item.invoice.invoice_number, item.invoice.source.document_id}
        identifiers |= {flag.flag_id for flag in item.flags}
        if wanted in {normalise_reference(identifier) for identifier in identifiers}:
            hits.append(item)
    return hits


def _item(items: list[ReviewItem], reference: str) -> QueryResult:
    result = QueryResult()
    hits = _find_items(items, reference)
    label = _reference_label(reference)
    result.data = {"reference": reference, "label": label, "hits": [_detail(item) for item in hits], "count": len(hits)}
    result.fact("Looked up", label)
    result.fact("Items found", len(hits))
    for item in hits:
        detail = _detail(item)
        rid = item.review_item_id
        result.fact(rid, f"{detail['party']}, {money(detail['amount'], detail['currency'])} on {detail['date'].isoformat()} — {detail['status']} ({detail['strength']}), decision {detail['decision']}")
        result.fact(f"{rid} ledger row", f"{detail['ledger_row_id']}, sheet row {detail['row_number'] or '-'}, account {detail['account'] or '-'}: {detail['description'] or '-'}")
        bank = detail["bank"]
        result.fact(f"{rid} bank line", "none" if bank is None else f"{bank['bank_row_id']} on {bank['date'].isoformat()}, {money(bank['amount'], bank['currency'])}, {bank['description']} (page {bank['page'] or '-'})")
        invoice = detail["invoice"]
        result.fact(f"{rid} invoice", "none" if invoice is None else f"{invoice['number']} dated {invoice['date'].isoformat()}, {money(invoice['amount'], invoice['currency'])}, {invoice['party']} (page {invoice['page'] or '-'})")
        result.fact(f"{rid} match rule", f"{detail['rule_id']} — {detail['reason']}")
        result.fact(f"{rid} flags", "; ".join(f"{f['rule_id']} ({f['severity']})" for f in detail["flag_rows"]) or "none")
        result.fact(f"{rid} extraction confidence", f"{detail['confidence']} over {detail['readings']} reading(s), {detail['unreadable']} unreadable")
        if detail["decision"] == "pending":
            result.fact(f"{rid} decision", "pending")
        else:
            result.fact(f"{rid} decision", f"{detail['decision']} by {detail['decided_by']} at {detail['decided_at']}" + (f" — {detail['rejection_reason']}" if detail["rejection_reason"] else ""))
    result.items = hits
    result.flags = [flag for item in hits for flag in item.flags]
    result.citations = _item_citations(hits[:8])
    return result


def _invoices(items: list[ReviewItem]) -> QueryResult:
    result = QueryResult()
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        invoice = item.invoice
        if invoice is None:
            continue
        entry = by_id.setdefault(invoice.invoice_id, {**_invoice_dict(item), "paid_by": [], "rules": []})  # type: ignore[arg-type]
        entry["paid_by"].append({
            "review_item_id": item.review_item_id, "date": item.ledger_entry.date,
            "amount": item.ledger_entry.amount, "status": item.match.status.value,
            "decision": item.decision.value,
        })
        for flag in item.flags:
            if flag.rule_id not in entry["rules"]:
                entry["rules"].append(flag.rule_id)
    rows = sorted(by_id.values(), key=lambda row: (row["date"], row["number"]))
    without = [item for item in items if item.invoice is None]
    total = sum((row["amount"] for row in rows), Decimal(0))
    with_invoice = [item for item in items if item.invoice is not None]
    result.data = {
        "rows": rows[:LIST_CAP], "count": len(rows), "more": max(0, len(rows) - LIST_CAP),
        "total": total, "currency": _currency(items), "without": len(without),
        "without_ids": [item.review_item_id for item in without][:LIST_CAP],
        "paid_more_than_once": sum(1 for row in rows if len(row["paid_by"]) > 1),
    }
    result.fact("Invoices in the evidence", len(rows))
    result.fact("Total invoiced", money(total, result.data["currency"]))
    result.fact("Ledger rows with no invoice", len(without))
    for row in rows[:LIST_CAP]:
        settled = ", ".join(f"{p['review_item_id']} on {p['date'].isoformat()} ({p['status']}, {p['decision']})" for p in row["paid_by"])
        result.fact(row["number"], f"{row['party']}, {money(row['amount'], row['currency'])}, dated {row['date'].isoformat()}; settled by {len(row['paid_by'])} ledger row(s): {settled}")
    result.items = with_invoice
    result.flags = [flag for item in with_invoice for flag in item.flags if flag.rule_id.startswith("duplicate-invoice")]
    seen: set[str] = set()
    for item in with_invoice:
        if item.invoice is not None and item.invoice.invoice_id not in seen:
            seen.add(item.invoice.invoice_id)
            result.citations.append(_cite(item.invoice.source, item.review_item_id))
    return result


def _bank(items: list[ReviewItem], context: WorkspaceContext | None) -> QueryResult:
    result = QueryResult()
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        bank = item.bank_transaction
        if bank is None:
            continue
        entry = by_id.setdefault(bank.bank_row_id, {**_bank_dict(item), "pays": []})  # type: ignore[arg-type]
        entry["pays"].append({"review_item_id": item.review_item_id, "party": item.ledger_entry.party_name})
    rows = sorted(by_id.values(), key=lambda row: (row["date"], row["bank_row_id"]))
    without = [item for item in items if item.bank_transaction is None]
    total = sum((row["amount"] for row in rows), Decimal(0))
    pages = sorted({row["page"] for row in rows if row["page"]})
    lines_read = None
    if context is not None:
        statement_rows = [
            len(extraction.rows) for extraction in context.extractions
            if extraction.document_type is DocumentType.BANK_STATEMENT
        ]
        lines_read = sum(statement_rows) if statement_rows else None
    result.data = {
        "rows": rows[:LIST_CAP], "count": len(rows), "more": max(0, len(rows) - LIST_CAP),
        "total": total, "currency": _currency(items), "pages": pages,
        "without": len(without), "without_ids": [item.review_item_id for item in without][:LIST_CAP],
        "lines_read": lines_read,
    }
    result.fact("Bank statement lines matched to ledger rows", len(rows))
    result.fact("Total of those lines", money(total, result.data["currency"]))
    if lines_read is not None:
        result.fact("Statement lines read by the vision model", lines_read)
    result.fact("Ledger rows with no bank line", len(without))
    for row in rows[:LIST_CAP]:
        pays = ", ".join(f"{p['review_item_id']} {p['party']}" for p in row["pays"])
        result.fact(row["bank_row_id"], f"{row['date'].isoformat()}, {money(row['amount'], row['currency'])}, {row['description']} (page {row['page'] or '-'}) → {pays}")
    with_bank = [item for item in items if item.bank_transaction is not None]
    result.items = with_bank
    seen: set[str] = set()
    for item in with_bank:
        if item.bank_transaction is not None and item.bank_transaction.bank_row_id not in seen:
            seen.add(item.bank_transaction.bank_row_id)
            result.citations.append(_cite(item.bank_transaction.source, item.review_item_id))
    return result


def _ledger(items: list[ReviewItem]) -> QueryResult:
    result = QueryResult()
    ordered = sorted(items, key=lambda item: (item.ledger_entry.date, item.review_item_id))
    rows = [
        {**_row(item), "ledger_row_id": item.ledger_entry.ledger_row_id,
         "row_number": item.ledger_entry.source.row_number, "description": item.ledger_entry.description,
         "account": item.ledger_entry.account_code, "flag_count": len(item.flags)}
        for item in ordered
    ]
    total = sum((item.ledger_entry.amount for item in items), Decimal(0))
    dates = [item.ledger_entry.date for item in items]
    result.data = {
        "rows": rows[:LIST_CAP], "count": len(rows), "more": max(0, len(rows) - LIST_CAP),
        "total": total, "currency": _currency(items),
        "period_start": min(dates) if dates else None, "period_end": max(dates) if dates else None,
        "parties": len({normalise_party_name(item.ledger_entry.party_name) for item in items}),
    }
    result.fact("Ledger rows", len(rows))
    result.fact("Total of all rows", money(total, result.data["currency"]))
    if dates:
        result.fact("Dated", f"{min(dates).isoformat()} to {max(dates).isoformat()}")
    for row in rows[:LIST_CAP]:
        result.fact(row["review_item_id"], f"{row['date'].isoformat()}, {row['party']}, {money(row['amount'], row['currency'])}: {row['status']}, decision {row['decision']}, {row['flag_count']} flag(s)")
    result.items = ordered[:LIST_CAP]
    return result


def _search_date(items: list[ReviewItem], day: date, granularity: str) -> QueryResult:
    result = QueryResult()

    def hit(when: date) -> bool:
        if granularity == "month":
            return (when.year, when.month) == (day.year, day.month)
        return when == day

    ledger = [item for item in items if hit(item.ledger_entry.date)]
    bank = [item for item in items if item.bank_transaction is not None and hit(item.bank_transaction.date)]
    # One invoice settled by two rows is one invoice dated that day, not two.
    invoices: list[ReviewItem] = []
    seen_invoices: set[str] = set()
    for item in items:
        if item.invoice is not None and hit(item.invoice.date) and item.invoice.invoice_id not in seen_invoices:
            seen_invoices.add(item.invoice.invoice_id)
            invoices.append(item)
    decided = [item for item in items if item.decided_at is not None and hit(item.decided_at.date())]
    total = sum((item.ledger_entry.amount for item in ledger), Decimal(0))
    dates = [item.ledger_entry.date for item in items]
    label = day.isoformat() if granularity == "day" else day.strftime("%Y-%m")
    result.data = {
        "day": day, "granularity": granularity, "label": label,
        "ledger": [_row(item) for item in ledger],
        "bank": [{**_row(item), "bank": _bank_dict(item)} for item in bank],
        "invoices": [{**_row(item), "invoice": _invoice_dict(item)} for item in invoices],
        "decided": [_detail(item) for item in decided],
        "total": total, "currency": _currency(items),
        "period_start": min(dates) if dates else None, "period_end": max(dates) if dates else None,
    }
    result.fact("Looked up", label)
    result.fact("Ledger rows dated then", len(ledger))
    result.fact("Total of those rows", money(total, result.data["currency"]))
    result.fact("Bank lines dated then", len(bank))
    result.fact("Invoices dated then", len(invoices))
    result.fact("Decisions taken then", len(decided))
    for item in ledger:
        result.fact(item.review_item_id, f"{item.ledger_entry.party_name}, {money(item.ledger_entry.amount, item.ledger_entry.currency)} on {item.ledger_entry.date.isoformat()}, {item.match.status.value}")
    for item in bank:
        assert item.bank_transaction is not None
        result.fact(item.bank_transaction.bank_row_id, f"{money(item.bank_transaction.amount, item.bank_transaction.currency)}, {item.bank_transaction.description} — pays {item.review_item_id}")
    seen: set[str] = set()
    involved = []
    for item in ledger + bank + invoices + decided:
        if item.review_item_id not in seen:
            seen.add(item.review_item_id)
            involved.append(item)
    result.items = involved
    result.flags = [flag for item in ledger for flag in item.flags]
    return result


def _confidence(items: list[ReviewItem]) -> QueryResult:
    result = QueryResult()
    by_level = Counter(item.extraction_confidence for item in items)
    weak = sorted(
        (item for item in items if item.extraction_confidence is not Confidence.HIGH),
        key=lambda item: (-_CONFIDENCE_RANK[item.extraction_confidence], item.review_item_id),
    )
    unreadable = sum(1 for item in items for reading in item.evidence if reading.unreadable)
    rows = [{**_row(item), "confidence": item.extraction_confidence.value, "weakest": _weakest_reading(item)} for item in weak]
    result.data = {
        "total": len(items), "high": by_level[Confidence.HIGH], "medium": by_level[Confidence.MEDIUM],
        "low": by_level[Confidence.LOW], "unreadable": unreadable, "rows": rows[:LIST_CAP],
        "more": max(0, len(rows) - LIST_CAP), "currency": _currency(items),
    }
    result.fact("Items by extraction confidence (high / medium / low)", f"{by_level[Confidence.HIGH]} / {by_level[Confidence.MEDIUM]} / {by_level[Confidence.LOW]}")
    result.fact("Source values unreadable", unreadable)
    for row in rows[:LIST_CAP]:
        weakest = row["weakest"]
        reading = "no reading" if weakest is None else (
            f"{weakest['field']} unreadable" if weakest["unreadable"]
            else f"{weakest['field']} = {weakest['value']} ({weakest['confidence']}) from {weakest['document_id']}"
            + (f" page {weakest['page']}" if weakest["page"] else "")
        )
        result.fact(row["review_item_id"], f"{row['party']}, {money(row['amount'], row['currency'])}: {row['confidence']} confidence — {reading}")
    result.items = weak[:LIST_CAP]
    return result


# --------------------------------------------------------------------------- #
# The rest of the engagement's record
#
# Each takes the WorkspaceContext the route loaded. All counting happens here
# in code over persisted rows; nothing in this section touches a document's
# bytes, and none of it can reach outside the organization the context was
# scoped to.
# --------------------------------------------------------------------------- #


def _size(size_bytes: int) -> str:
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.1f} MB"
    return f"{max(1, round(size_bytes / 1000))} KB"


def _no_context() -> QueryResult:
    """For a caller that loaded no workspace: refuse rather than guess."""
    return QueryResult(grounded=False, answer_confidence=Confidence.LOW)


def _cases(context: WorkspaceContext | None) -> QueryResult:
    if context is None:
        return _no_context()
    result = QueryResult()
    rows = []
    for overview in context.cases[:20]:
        case = overview.case
        rows.append({
            "case_id": case.case_id,
            "client": case.client_name,
            "status": case.status.value,
            "created": case.created_at.date().isoformat(),
            "items": overview.total_items,
            "pending": overview.pending,
            "approved": overview.approved,
            "rejected": overview.rejected,
            "flags": overview.flags,
            "active": case.case_id == context.active_case_id,
        })
    result.data = {"rows": rows, "count": len(context.cases), "shown": len(rows), "active_case_id": context.active_case_id}
    result.fact("Engagements in this organization", len(context.cases))
    for row in rows:
        result.fact(
            f"{row['client']} ({row['case_id']})",
            f"{row['items']} items, {row['pending']} pending, {row['flags']} flags, status {row['status']}, created {row['created']}",
        )
    if len(context.cases) > len(rows):
        result.fact("Engagements listed", f"{len(rows)} of {len(context.cases)} (most recent first)")
    return result


def _documents(context: WorkspaceContext | None) -> QueryResult:
    if context is None:
        return _no_context()
    result = QueryResult()
    read: dict[str, ExtractionResult] = {e.document_id: e for e in context.extractions}
    rows = []
    for document in context.documents:
        extraction = read.get(document.document_id)
        values = 0
        if extraction is not None:
            values = len(extraction.fields) + sum(len(row.fields) for row in extraction.rows)
        rows.append({
            "document_id": document.document_id,
            "filename": document.filename,
            "type": document.document_type.value,
            "size": _size(document.size_bytes),
            "extracted": extraction is not None,
            "pages": extraction.page_count if extraction is not None else None,
            "model": extraction.model if extraction is not None else None,
            "values": values,
            "needs_human_review": extraction.needs_human_review if extraction is not None else False,
        })
    result.data = {"rows": rows, "count": len(rows), "extracted": sum(1 for row in rows if row["extracted"])}
    result.fact("Documents in this case", len(rows))
    result.fact("Read by the extraction pipeline", sum(1 for row in rows if row["extracted"]))
    for row in rows:
        if row["extracted"]:
            result.fact(row["filename"], f"{row['type']}, {row['size']}, {row['pages']} page(s), {row['values']} values read by {row['model']}")
        else:
            result.fact(row["filename"], f"{row['type']}, {row['size']}, not extracted yet")
    return result


def _extractions(context: WorkspaceContext | None) -> QueryResult:
    if context is None:
        return _no_context()
    result = QueryResult()
    rows = []
    citations: list[AssistantCitation] = []
    for extraction in context.extractions:
        fields = list(extraction.fields)
        for extracted_row in extraction.rows:
            fields.extend(extracted_row.fields)
        by_confidence = {Confidence.HIGH: 0, Confidence.MEDIUM: 0, Confidence.LOW: 0}
        unreadable = 0
        for extracted in fields:
            if extracted.unreadable:
                unreadable += 1
            else:
                by_confidence[extracted.extraction_confidence] += 1
        # What a checker wants shown first: the readings worth a second look.
        notable = sorted(
            (f for f in fields if f.unreadable or f.extraction_confidence is not Confidence.HIGH),
            key=lambda f: (not f.unreadable, f.field),
        )[:6]
        notable_rows = []
        for extracted in notable:
            notable_rows.append({
                "field": extracted.field,
                "value": None if extracted.unreadable else extracted.value,
                "unreadable": extracted.unreadable,
                "confidence": extracted.extraction_confidence.value,
                "page": extracted.source.page,
                "snippet": extracted.source.text_snippet,
            })
            if len(citations) < 6:
                citations.append(AssistantCitation(
                    document_id=extracted.source.document_id,
                    page=extracted.source.page,
                    row_number=extracted.source.row_number,
                    text_snippet=extracted.source.text_snippet,
                    review_item_id=None,
                ))
        rows.append({
            "filename": extraction.filename,
            "document_id": extraction.document_id,
            "type": extraction.document_type.value,
            "model": extraction.model,
            "pages": extraction.page_count,
            "values": len(fields),
            "high": by_confidence[Confidence.HIGH],
            "medium": by_confidence[Confidence.MEDIUM],
            "low": by_confidence[Confidence.LOW],
            "unreadable": unreadable,
            "second_opinion": (
                None if extraction.second_opinion is None
                else ("agrees" if extraction.second_opinion.agrees else "disagrees")
            ),
            "needs_human_review": extraction.needs_human_review,
            "notable": notable_rows,
        })
    result.data = {"rows": rows, "count": len(rows)}
    result.citations = citations
    result.fact("Documents read by the vision model", len(rows))
    for row in rows:
        result.fact(
            row["filename"],
            f"{row['values']} values over {row['pages']} page(s): {row['high']} high, {row['medium']} medium, "
            f"{row['low']} low confidence, {row['unreadable']} unreadable; read by {row['model']}",
        )
    return result


def _decisions(items: list[ReviewItem]) -> QueryResult:
    result = QueryResult()
    decided = [item for item in items if item.decision is not ReviewDecision.PENDING]
    approved = sum(1 for item in items if item.decision is ReviewDecision.APPROVED)
    rejected = sum(1 for item in items if item.decision is ReviewDecision.REJECTED)
    ordered = sorted(decided, key=lambda item: (item.decided_at or item.review_item_id, item.review_item_id))
    rows = [{
        **_row(item),
        "decided_by": item.decided_by,
        "decided_at": item.decided_at.strftime("%Y-%m-%d %H:%M") if item.decided_at else "-",
        "rejection_reason": item.rejection_reason,
    } for item in ordered]
    result.data = {
        "rows": rows, "approved": approved, "rejected": rejected,
        "pending": len(items) - len(decided), "decided": len(decided), "total": len(items),
    }
    result.fact("Items approved", approved)
    result.fact("Items rejected", rejected)
    result.fact("Items still pending", len(items) - len(decided))
    for row in rows:
        result.fact(
            f"{row['review_item_id']} ({row['decision']})",
            f"{row['party']}, {money(row['amount'], row['currency'])}, by {row['decided_by']} at {row['decided_at']}"
            + (f" — {row['rejection_reason']}" if row["rejection_reason"] else ""),
        )
    result.items = ordered
    return result


def _reports(context: WorkspaceContext | None) -> QueryResult:
    if context is None:
        return _no_context()
    result = QueryResult()
    rows = [{
        "report_id": report.report_id,
        "generated_at": report.generated_at.strftime("%Y-%m-%d %H:%M"),
        "generated_by": report.generated_by,
        "items": report.item_count,
        "approved": report.approved_count,
        "rejected": report.rejected_count,
        "pending": report.pending_count,
        "flags": report.flag_count,
        "trail_records": report.audit_record_count,
    } for report in context.reports]
    result.data = {"rows": rows, "count": len(rows)}
    result.fact("Reports generated for this case", len(rows))
    for row in rows:
        result.fact(
            row["report_id"],
            f"generated {row['generated_at']} by {row['generated_by']}: {row['items']} items "
            f"({row['approved']} approved, {row['rejected']} rejected, {row['pending']} pending), "
            f"{row['flags']} flags, {row['trail_records']} trail records",
        )
    return result


def _history(context: WorkspaceContext | None) -> QueryResult:
    if context is None:
        return _no_context()
    result = QueryResult()
    records = list(context.trail)  # oldest first, as the store returns it
    recent = list(reversed(records))[:8]
    by_action = Counter(record.action.value for record in records)
    rows = [{
        "when": record.occurred_at.strftime("%Y-%m-%d %H:%M"),
        "action": record.action.value,
        "actor": record.actor_id,
        "actor_type": record.actor_type.value,
        "detail": (record.detail or "")[:90],
    } for record in recent]
    result.data = {"rows": rows, "total": len(records), "by_action": dict(by_action)}
    result.fact("Events in this case's trail", len(records))
    for action, count in sorted(by_action.items(), key=lambda kv: (-kv[1], kv[0]))[:8]:
        result.fact(f"Action {action}", count)
    return result


def _case_info(
    case: CaseRecord | None, items: list[ReviewItem], benford: BenfordResult | None,
    context: WorkspaceContext | None,
) -> QueryResult:
    """The engagement itself: whose it is, what period, where it stands."""
    if case is None:
        return _no_context()
    result = QueryResult()
    dates = [item.ledger_entry.date for item in items]
    derived = case.period_start is None and bool(dates)
    start = case.period_start or (min(dates) if dates else None)
    end = case.period_end or (max(dates) if dates else None)
    by_status = Counter(item.match.status for item in items)
    by_decision = Counter(item.decision for item in items)
    total = sum((item.ledger_entry.amount for item in items), Decimal(0))
    documents: dict[str, int] | None = None
    reports: int | None = None
    if context is not None:
        documents = dict(Counter(document.document_type.value for document in context.documents))
        reports = len(context.reports)
    result.data = {
        "case_id": case.case_id, "client": case.client_name, "status": case.status.value,
        "status_detail": case.status_detail, "created": case.created_at.date(),
        "created_by": case.created_by, "period_start": start, "period_end": end,
        "period_derived": derived, "items": len(items), "total": total, "currency": _currency(items),
        "parties": len({normalise_party_name(item.ledger_entry.party_name) for item in items}),
        "matched": by_status[MatchStatus.MATCHED], "partial": by_status[MatchStatus.PARTIAL],
        "unmatched": by_status[MatchStatus.UNMATCHED],
        "approved": by_decision[ReviewDecision.APPROVED], "rejected": by_decision[ReviewDecision.REJECTED],
        "pending": by_decision[ReviewDecision.PENDING],
        "flags": sum(len(item.flags) for item in items),
        "documents": documents, "reports": reports,
        "benford": benford is not None and benford.sample_size > 0,
    }
    result.fact("Client", case.client_name)
    result.fact("Case", f"{case.case_id}, {case.status.value}, created {case.created_at.date().isoformat()}")
    if start and end:
        result.fact("Period", f"{start.isoformat()} to {end.isoformat()}" + (" (from the ledger rows)" if derived else ""))
    result.fact("Ledger rows / parties", f"{len(items)} / {result.data['parties']}")
    result.fact("Total of ledger rows", money(total, result.data["currency"]))
    result.fact("Matched / partial / unmatched", f"{result.data['matched']} / {result.data['partial']} / {result.data['unmatched']}")
    result.fact("Approved / rejected / pending", f"{result.data['approved']} / {result.data['rejected']} / {result.data['pending']}")
    result.fact("Flags", result.data["flags"])
    if documents is not None:
        result.fact("Documents", ", ".join(f"{count} {kind}" for kind, count in sorted(documents.items())) or "none")
    if reports is not None:
        result.fact("Reports generated", reports)
    return result


def _concept(plan: Plan) -> QueryResult:
    result = QueryResult()
    topic = plan.topic or ""
    explanation = CONCEPTS.get(topic, {})
    result.data = {
        "topic": topic,
        "en": explanation.get("en", ""),
        "ur": explanation.get("ur", ""),
    }
    result.fact("Topic", topic)
    result.fact("Answered from", "Tarazu's built-in glossary, shipped in code")
    return result


def execute(
    plan: Plan,
    items: list[ReviewItem],
    benford: BenfordResult | None,
    context: WorkspaceContext | None = None,
    case: CaseRecord | None = None,
) -> QueryResult:
    """Run the deterministic query the plan names."""
    intent = plan.intent
    if intent is AssistantIntent.SUMMARY:
        return _summary(items, benford)
    if intent is AssistantIntent.MATCHES:
        return _matches(items, plan.status)
    if intent is AssistantIntent.UNMATCHED:
        return _unmatched(items)
    if intent is AssistantIntent.MISSING_EVIDENCE:
        return _missing_evidence(items)
    if intent is AssistantIntent.FLAGS:
        return _flags(items)
    if intent is AssistantIntent.RULE:
        return _rule(items, plan.rule_id or "")
    if intent is AssistantIntent.DUPLICATES:
        return _duplicates(items)
    if intent is AssistantIntent.PARTY:
        return _party(items, plan.party or "")
    if intent is AssistantIntent.ITEM:
        return _item(items, plan.reference or "")
    if intent is AssistantIntent.INVOICES:
        return _invoices(items)
    if intent is AssistantIntent.BANK:
        return _bank(items, context)
    if intent is AssistantIntent.LEDGER:
        return _ledger(items)
    if intent is AssistantIntent.CONFIDENCE:
        return _confidence(items)
    if intent is AssistantIntent.TOTALS:
        return _totals(items)
    if intent is AssistantIntent.TOP_VENDORS:
        return _top_vendors(items, plan.limit)
    if intent is AssistantIntent.LARGEST:
        return _largest(items, plan.limit)
    if intent is AssistantIntent.COMPARE_MONTHS:
        return _compare_months(items)
    if intent is AssistantIntent.SEARCH_AMOUNT:
        return _search_amount(items, plan.amount or Decimal(0))
    if intent is AssistantIntent.SEARCH_DATE:
        return _search_date(items, plan.day or date.today(), plan.granularity or "day")
    if intent is AssistantIntent.BENFORD:
        return _benford(benford)
    if intent is AssistantIntent.CASE_INFO:
        return _case_info(case, items, benford, context)
    if intent is AssistantIntent.CASES:
        return _cases(context)
    if intent is AssistantIntent.DOCUMENTS:
        return _documents(context)
    if intent is AssistantIntent.EXTRACTIONS:
        return _extractions(context)
    if intent is AssistantIntent.DECISIONS:
        return _decisions(items)
    if intent is AssistantIntent.REPORTS:
        return _reports(context)
    if intent is AssistantIntent.HISTORY:
        return _history(context)
    if intent is AssistantIntent.CONCEPT:
        return _concept(plan)
    if intent is AssistantIntent.HELP:
        return QueryResult(answer_confidence=Confidence.HIGH)
    # UNSUPPORTED and UNKNOWN: nothing to compute, and nothing to cite.
    return QueryResult(grounded=False, answer_confidence=Confidence.LOW)
