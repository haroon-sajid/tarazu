"""Public interface of the assistant module.

This is the only file other modules may import from `modules/assistant/`.

Ask Tarazu answers three kinds of question, each from its own source:
about the case under review — its results as a whole, one row, invoice, or
bank line by its identifier, the evidence behind the rows — from that case's
persisted results; about the engagement's wider record and the
organization's other cases, from the read-only `WorkspaceContext` the route
loaded; and about auditing itself, from a glossary shipped in code for the
first-time auditor. The pipeline, in order:

1. **Understand the intent** — `planner.plan`, deterministic keyword routing
   in English and Urdu. When the keywords cannot place a question and a
   model is configured, `classifier.classify` asks the model which of the
   fixed queries the question is asking for — under checks that let it name
   nothing the question does not already contain — and a reply that fails
   them leaves the question refused. The model chooses a query; it never
   answers.
2. **Plan the query** — the intent names one deterministic query.
3. **Run the calculation in code** — `queries.execute`, Python `Decimal`
   over the review items, the stored Benford result, the case record and —
   where the question is about the wider record — the workspace context.
   Counts, sums, groupings, lookups; nothing a model touched.
4. **Word the result** — `composer.compose`, templates in the answer's
   language. When a Qwen key is configured (and not in `DEMO_MODE`) the
   model is asked to rephrase the template *without adding a number*, and
   the reply is checked: every number in it must already appear in the
   computed facts, or the template stands.
5. **Show the sources** — citations into the documents behind the items the
   answer rests on, and the list of facts the prose was written from.

The model formats and explains, and may choose which query runs. It never
computes, and it never sees the documents — only the question, the figures
the deterministic layer produced, and the names of the queries.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from app.modules.assistant import classifier, composer, planner, queries
from app.modules.assistant.queries import CaseOverview, WorkspaceContext
from app.modules.assistant.qwen_chat import AssistantModelError, QwenChatClient
from app.modules.assistant.settings import AssistantSettings, get_settings
from app.shared.schemas import (
    AssistantAnswer,
    AssistantCitation,
    AssistantIntent,
    AssistantLanguage,
    BenfordResult,
    CaseRecord,
    Confidence,
    Flag,
    ReviewItem,
)

#: `WorkspaceContext` and `CaseOverview` are re-exported because this file is
#: the module's public interface: the route builds the context from
#: repository reads, so it needs the types from here and nowhere else.
__all__ = [
    "DETERMINISTIC_COMPOSER",
    "ROUTED_BY_LABEL",
    "CaseOverview",
    "WorkspaceContext",
    "answer_question",
    "numbers_in",
]

logger = logging.getLogger(__name__)

#: What `AssistantAnswer.composed_by` says when no model touched the wording.
DETERMINISTIC_COMPOSER = "assistant.deterministic"

#: The fact label recording that the model, not the keywords, chose the query.
ROUTED_BY_LABEL = "Question understood by"

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

_PHRASING_SYSTEM = (
    "You rewrite an audit assistant's answer so it reads naturally. You are given the "
    "answer and the facts it was built from.\n\n"
    "Rules:\n"
    "- Keep every figure, name, date, and identifier exactly as given. Do not add any "
    "number, amount, count, percentage, or date that is not in the facts.\n"
    "- Do not compute, round, total, or compare figures yourself.\n"
    "- Do not add claims, advice, or context from outside the facts.\n"
    "- Keep the bullet lines, the item identifiers in brackets, and the closing "
    "sentence about the human decision.\n"
    "- Answer in the same language as the answer you were given.\n"
    "Reply with the rewritten answer only."
)


def numbers_in(text: str) -> set[str]:
    """Every number in `text`, normalised (separators dropped, no trailing zeros)."""
    found: set[str] = set()
    for match in _NUMBER.finditer(text):
        raw = match.group(0).replace(",", "")
        if raw.count(".") > 1:
            raw = raw.replace(".", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        found.add(f"{value:.6g}")
    return found


def _phrase_with_model(
    question: str,
    template: str,
    facts: list,
    language: AssistantLanguage,
    client: QwenChatClient,
) -> str | None:
    """Ask the model to rephrase; return None if it must not be used."""
    fact_lines = "\n".join(f"- {fact.label}: {fact.value}" for fact in facts)
    messages = [
        {"role": "system", "content": _PHRASING_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Question: {question}\n\nLanguage: {language.value}\n\n"
                f"Facts:\n{fact_lines or '- (none)'}\n\nAnswer to rewrite:\n{template}"
            ),
        },
    ]
    try:
        rewritten = client.complete_text(messages)
    except AssistantModelError as error:
        logger.warning("Assistant phrasing skipped: %s", error)
        return None

    allowed = numbers_in(template) | numbers_in(fact_lines)
    introduced = numbers_in(rewritten) - allowed
    if introduced:
        logger.warning(
            "Assistant phrasing discarded: the model introduced numbers %s", sorted(introduced)
        )
        return None
    if len(rewritten) > 3 * len(template) + 400:
        logger.warning("Assistant phrasing discarded: the reply grew far beyond the facts")
        return None
    return rewritten


def _citations(items: list[ReviewItem], flags: list[Flag], limit: int = 8) -> list[AssistantCitation]:
    seen: set[tuple] = set()
    collected: list[AssistantCitation] = []

    def push(document_id: str, page, row_number, snippet, review_item_id) -> None:
        key = (document_id, page, row_number)
        if key in seen or len(collected) >= limit:
            return
        seen.add(key)
        collected.append(
            AssistantCitation(
                document_id=document_id,
                page=page,
                row_number=row_number,
                text_snippet=snippet,
                review_item_id=review_item_id,
            )
        )

    for flag in flags:
        if flag.source is not None:
            push(flag.source.document_id, flag.source.page, flag.source.row_number,
                 flag.source.text_snippet, None)
    for item in items:
        source = item.ledger_entry.source
        push(source.document_id, source.page, source.row_number, source.text_snippet,
             item.review_item_id)
        for reading in item.evidence:
            push(reading.source.document_id, reading.source.page, reading.source.row_number,
                 reading.source.text_snippet, item.review_item_id)
    return collected


def _answer_citations(result: queries.QueryResult) -> list[AssistantCitation]:
    """The query's own citations first, then those behind the items and flags.

    A query that rests directly on document regions — what the vision model
    read, an invoice's page, a bank line — builds `result.citations` itself;
    every other answer rests on review items, whose ledger rows and evidence
    `_citations` points at. Both streams deduplicate on the source region,
    under one cap.
    """
    collected: list[AssistantCitation] = []
    seen: set[tuple] = set()

    def push(citation: AssistantCitation) -> None:
        key = (citation.document_id, citation.page, citation.row_number)
        if key in seen or len(collected) >= 8:
            return
        seen.add(key)
        collected.append(citation)

    for citation in result.citations:
        push(citation)
    for citation in _citations(result.items, result.flags):
        push(citation)
    return collected


def _parties(items: list[ReviewItem]) -> list[str]:
    parties: list[str] = []
    seen: set[str] = set()
    for item in items:
        name = item.ledger_entry.party_name
        if name not in seen:
            seen.add(name)
            parties.append(name)
    return parties


def _references(items: list[ReviewItem]) -> list[str]:
    """Every identifier the case's rows carry, so the planner recognises one
    however it was typed: review items, ledger rows, bank lines, invoices and
    their numbers, flags, and the documents they came from."""
    references: list[str] = []
    seen: set[str] = set()

    def add(reference: str | None) -> None:
        if reference and reference not in seen:
            seen.add(reference)
            references.append(reference)

    for item in items:
        add(item.review_item_id)
        add(item.ledger_entry.ledger_row_id)
        add(item.ledger_entry.source.document_id)
        if item.bank_transaction is not None:
            add(item.bank_transaction.bank_row_id)
            add(item.bank_transaction.source.document_id)
        if item.invoice is not None:
            add(item.invoice.invoice_id)
            add(item.invoice.invoice_number)
            add(item.invoice.source.document_id)
        for flag in item.flags:
            add(flag.flag_id)
    return references


def _default_year(items: list[ReviewItem]) -> int | None:
    """The year most ledger rows fall in — what "11 June" means in this case."""
    years = Counter(item.ledger_entry.date.year for item in items)
    return years.most_common(1)[0][0] if years else None


def answer_question(
    question: str,
    *,
    case: CaseRecord,
    items: list[ReviewItem],
    benford: BenfordResult | None,
    context: WorkspaceContext | None = None,
    language: AssistantLanguage | None = None,
    settings: AssistantSettings | None = None,
    client: QwenChatClient | None = None,
) -> AssistantAnswer:
    """Answer one question: from the case's persisted results, from the
    workspace context the route loaded, or from the shipped glossary — and
    from nowhere else.

    Args:
        question: What the person asked, in English or Urdu.
        case: The case the question is about.
        items: Its persisted review queue.
        benford: Its stored Benford result, if any.
        context: The rest of the engagement's read-only record — documents,
            extractions, reports, the audit trail, and the organization's
            case overviews — for the workspace intents. When omitted the
            assistant answers those questions by refusing, never by guessing.
        language: Force the answer language; detected from the question when
            omitted.
        settings: Injected in tests. Read from the environment when omitted.
        client: Injected in tests. Built from settings when a model is used.

    Returns:
        An `AssistantAnswer` carrying the text, its confidence, its citations,
        and the computed facts it was written from. Never raises for a
        question it cannot answer — that is an answer with `grounded=False`.
    """
    settings = settings or get_settings()
    parties = _parties(items)
    references = _references(items)
    default_year = _default_year(items)

    plan = planner.plan(
        question, parties, language, references=references, default_year=default_year,
    )

    # One model client serves both model steps — choosing a query for a
    # question the keywords missed, and rephrasing the template — and none is
    # built when no model is configured or in demo mode.
    model_client: QwenChatClient | None = None
    owns_client = False
    if settings.uses_model:
        model_client = client or QwenChatClient(settings=settings)
        owns_client = client is None

    routed_by_model = False
    try:
        if plan.intent is AssistantIntent.UNKNOWN and model_client is not None:
            routed = classifier.classify(
                question, parties=parties, language=plan.language, client=model_client,
                references=references, default_year=default_year,
            )
            if routed is not None:
                plan = routed
                routed_by_model = True

        result = queries.execute(plan, items, benford, context, case=case)
        if routed_by_model:
            # The reader can see the model chose the query — and the answer
            # admits the interpretation involved.
            result.fact(ROUTED_BY_LABEL, settings.model)
            if result.answer_confidence is Confidence.HIGH:
                result.answer_confidence = Confidence.MEDIUM

        text = composer.compose(plan, result)
        composed_by = DETERMINISTIC_COMPOSER
        if (
            model_client is not None
            and result.grounded
            and plan.intent not in (AssistantIntent.HELP, AssistantIntent.UNSUPPORTED)
        ):
            rewritten = _phrase_with_model(question, text, result.facts, plan.language, model_client)
            if rewritten is not None:
                text = rewritten
                composed_by = settings.model
    finally:
        if owns_client and model_client is not None:
            model_client.close()

    grounded = result.grounded
    return AssistantAnswer(
        question=question,
        language=plan.language,
        intent=plan.intent,
        text=text,
        answer_confidence=result.answer_confidence if grounded else Confidence.LOW,
        grounded=grounded,
        citations=_answer_citations(result) if grounded else [],
        facts=result.facts,
        composed_by=composed_by,
    )
