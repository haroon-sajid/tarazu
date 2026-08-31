"""Step 1b of the Ask Tarazu pipeline: a model may choose the query — never the answer.

`planner.plan` places a question by keywords. When it cannot, and a model is
configured, this file asks the model one thing: *which* of the planner's fixed
queries the question is asking for, and with which parameters. That is the
extension ADR 0006 left room for, and it stays inside the same rule the
phrasing step obeys — the model decides nothing about what the answer says.
It never sees a document, and its reply is not trusted:

- the intent must be one of the fixed set, or the reply is discarded;
- a party must be one the ledger actually names;
- an amount, a date, or an identifier must be written in the question itself
  — the model cannot introduce one;
- a rule id or a glossary topic must be one the module ships.

A reply that fails a check leaves the question refused, exactly as if the
model had never been asked. The chosen plan then runs the same deterministic
query as a keyword-placed one, and the answer records that the model chose
the intent (a fact, and a confidence one step lower) so a reader can see it.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from app.modules.assistant.concepts import CONCEPTS
from app.modules.assistant.planner import Plan, date_named
from app.modules.assistant.qwen_chat import AssistantModelError, QwenChatClient
from app.modules.assistant.queries import RULE_DESCRIPTIONS
from app.shared.schemas import AssistantIntent, AssistantLanguage, MatchStatus
from app.shared.text import normalise_party_name, normalise_reference

__all__ = ["INTENT_GUIDE", "classify"]

logger = logging.getLogger(__name__)

#: One line per query the planner can run — what the model chooses between.
#: Kept beside the code that runs them, not in a prompt file, so adding a
#: query means adding a line here.
INTENT_GUIDE: dict[AssistantIntent, str] = {
    AssistantIntent.SUMMARY: "an overview of the case: how many rows matched, were flagged, were decided, and the total",
    AssistantIntent.MATCHES: "how the ledger rows reconciled against the bank statement and the invoices, optionally one status (status)",
    AssistantIntent.UNMATCHED: "ledger rows with no bank line and no invoice behind them",
    AssistantIntent.MISSING_EVIDENCE: "rows short of evidence, or with an unreadable value in a source document",
    AssistantIntent.FLAGS: "every red flag raised, by severity and rule",
    AssistantIntent.RULE: "one red-flag rule explained with the rows it fired on (needs rule_id)",
    AssistantIntent.DUPLICATES: "duplicate payments and invoices paid twice",
    AssistantIntent.PARTY: "everything paid to one party named in the question (needs party, from the list)",
    AssistantIntent.ITEM: "one row, invoice, bank line, or flag by an identifier written in the question (needs reference)",
    AssistantIntent.INVOICES: "the invoices in the evidence and which ledger rows they settle",
    AssistantIntent.BANK: "the bank statement lines and which ledger rows they pay",
    AssistantIntent.LEDGER: "every ledger row listed with its status and decision",
    AssistantIntent.CONFIDENCE: "how confidently the vision model read the evidence behind each row",
    AssistantIntent.TOTALS: "the total paid, split by match status, with the period and the largest row",
    AssistantIntent.TOP_VENDORS: "the parties ranked by amount paid",
    AssistantIntent.LARGEST: "the largest payments",
    AssistantIntent.COMPARE_MONTHS: "totals month by month",
    AssistantIntent.SEARCH_AMOUNT: "rows and bank lines of one amount written in the question (needs amount)",
    AssistantIntent.SEARCH_DATE: "what is dated one day or month written in the question (needs date as YYYY-MM-DD)",
    AssistantIntent.BENFORD: "the Benford first-digit analysis of this case",
    AssistantIntent.CASE_INFO: "the case itself: the client, the period, its status, its counts",
    AssistantIntent.CASES: "every engagement in the organization",
    AssistantIntent.DOCUMENTS: "the documents uploaded to this case",
    AssistantIntent.EXTRACTIONS: "what the vision model read from each document, with confidences",
    AssistantIntent.DECISIONS: "the approvals and rejections taken so far, by whom",
    AssistantIntent.REPORTS: "the reports generated for this case",
    AssistantIntent.HISTORY: "the case's audit trail: who did what, when",
    AssistantIntent.CONCEPT: "what an auditing term means, from the glossary (needs topic, from the list)",
    AssistantIntent.HELP: "what the assistant can be asked",
    AssistantIntent.UNSUPPORTED: "sales, revenue, income, or profit — figures a payments ledger does not carry",
    AssistantIntent.UNKNOWN: "not about this audit case, its documents, its results, or auditing at all",
}

_SYSTEM = (
    "You route questions for an audit assistant. You are given one question about one audit "
    "case, the list of query types the assistant can run, the party names in the case's ledger, "
    "the rule ids, and the glossary topics.\n\n"
    "Reply with one JSON object and nothing else, of this exact shape:\n"
    '{"intent": "<one query type>", "party": "<a party from the list, or null>", '
    '"amount": <a number written in the question, or null>, "rule_id": "<a rule id, or null>", '
    '"reference": "<an identifier written in the question, or null>", '
    '"date": "<a date written in the question as YYYY-MM-DD, or null>", '
    '"status": "<matched, partial, unmatched, or null>", "topic": "<a glossary topic, or null>"}\n\n'
    "Rules:\n"
    "- Choose the single query type that answers the question from the case's own data.\n"
    "- Never invent a party, amount, identifier, or date: each must be written in the question.\n"
    "- Choose \"unknown\" only when the question is not about the audit case, its documents, "
    "its results, or auditing.\n"
    "- Never answer the question. You only choose the query."
)

_INTEGER = re.compile(r"\d+")


def _parse_json(reply: str) -> dict[str, Any] | None:
    """The first JSON object in the reply, tolerating code fences and prose around it."""
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(reply[start:end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _checked_party(value: Any, parties: list[str]) -> str | None:
    """The ledger's own spelling of the party the model named, or None."""
    named = normalise_party_name(_text(value))
    if not named:
        return None
    for party in parties:
        if normalise_party_name(party) == named:
            return party
    tokens = set(named.split())
    for party in parties:
        if tokens and tokens <= set(normalise_party_name(party).split()):
            return party
    return None


def _checked_amount(value: Any, question: str) -> Decimal | None:
    """The amount, only if its digits are written in the question."""
    raw = _text(value)
    if raw is None:
        return None
    try:
        amount = Decimal(raw.replace(",", "").replace(" ", ""))
    except InvalidOperation:
        return None
    if amount < 100:
        return None
    digits = str(int(amount)) if amount == amount.to_integral_value() else str(amount)
    plain = re.sub(r"[,\s]", "", question)
    return amount if digits in plain else None


def _checked_reference(value: Any, question: str, references: Iterable[str]) -> str | None:
    """The identifier, only if the question contains it; the case's spelling when it has one."""
    raw = _text(value)
    if raw is None:
        return None
    wanted = normalise_reference(raw)
    if len(wanted) < 3 or wanted not in normalise_reference(question):
        return None
    for reference in references:
        if normalise_reference(reference) == wanted:
            return reference
    return raw


def _checked_date(value: Any, question: str, default_year: int | None) -> tuple[date, str] | None:
    """A date the planner's own parser finds in the question wins; otherwise
    the model's ISO date is accepted only if its day is written in the question."""
    parsed = date_named(question, default_year)
    if parsed is not None:
        return parsed
    raw = _text(value)
    if raw is None:
        return None
    try:
        if len(raw) == 7:
            return date.fromisoformat(f"{raw}-01"), "month"
        day = date.fromisoformat(raw[:10])
    except ValueError:
        return None
    numbers = {int(token) for token in _INTEGER.findall(question)}
    return (day, "day") if day.day in numbers else None


def classify(
    question: str,
    *,
    parties: list[str],
    language: AssistantLanguage,
    client: QwenChatClient,
    references: Iterable[str] = (),
    default_year: int | None = None,
) -> Plan | None:
    """Ask the model which query the question is asking for. None when it
    cannot be reached, does not answer usably, or names anything the checks
    reject — in every such case the question stays refused."""
    guide = "\n".join(f"- {intent.value}: {text}" for intent, text in INTENT_GUIDE.items())
    party_lines = "\n".join(f"- {party}" for party in parties) or "- (none)"
    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                f"Question: {question}\n\nQuery types:\n{guide}\n\n"
                f"Parties in the ledger:\n{party_lines}\n\n"
                f"Rule ids: {', '.join(RULE_DESCRIPTIONS)}\n\n"
                f"Glossary topics: {', '.join(CONCEPTS)}"
            ),
        },
    ]
    try:
        reply = client.complete_text(messages, temperature=0.0)
    except AssistantModelError as error:
        logger.warning("Assistant classification skipped: %s", error)
        return None
    parsed = _parse_json(reply)
    if parsed is None:
        logger.warning("Assistant classification discarded: the reply was not a JSON object")
        return None

    try:
        intent = AssistantIntent(str(parsed.get("intent", "")).strip().lower())
    except ValueError:
        logger.warning("Assistant classification discarded: unknown intent %r", parsed.get("intent"))
        return None
    if intent is AssistantIntent.UNKNOWN:
        return None

    references = list(references)
    if intent is AssistantIntent.PARTY:
        party = _checked_party(parsed.get("party"), parties)
        return Plan(intent, language, party=party) if party else None
    if intent is AssistantIntent.RULE:
        rule_id = _text(parsed.get("rule_id"))
        return Plan(intent, language, rule_id=rule_id) if rule_id in RULE_DESCRIPTIONS else None
    if intent is AssistantIntent.SEARCH_AMOUNT:
        amount = _checked_amount(parsed.get("amount"), question)
        return Plan(intent, language, amount=amount) if amount is not None else None
    if intent is AssistantIntent.ITEM:
        reference = _checked_reference(parsed.get("reference"), question, references)
        return Plan(intent, language, reference=reference) if reference else None
    if intent is AssistantIntent.SEARCH_DATE:
        dated = _checked_date(parsed.get("date"), question, default_year)
        return Plan(intent, language, day=dated[0], granularity=dated[1]) if dated else None
    if intent is AssistantIntent.MATCHES:
        raw_status = _text(parsed.get("status"))
        status = MatchStatus(raw_status) if raw_status in {s.value for s in MatchStatus} else None
        return Plan(intent, language, status=status)
    if intent is AssistantIntent.CONCEPT:
        topic = _text(parsed.get("topic"))
        return Plan(intent, language, topic=topic) if topic in CONCEPTS else None
    return Plan(intent, language)
