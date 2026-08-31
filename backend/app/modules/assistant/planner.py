"""Step 1 of the Ask Tarazu pipeline: understand the intent, deterministically.

A question becomes a `Plan`: which deterministic query to run, in which
language to answer, and with what parameters (a rule id, a party, an amount,
an identifier, a date). The planner is keyword routing over a fixed vocabulary
— English and Urdu — rather than a model call, for two reasons: it is
reproducible, and a question the planner cannot place is *refused* rather
than guessed at (reliability rule 7). When a model is configured, a question
the keywords miss may be handed to `classifier.py`, which asks the model to
choose *which* of these queries runs — under checks — and never what the
answer says.

The vocabulary is deliberately wide. The assistant's job is to answer any
question about this audit's own data and results: what was uploaded, what
the pipeline read, how each row matched, which flags fired, what was
decided, and any one row, invoice, or bank line by its identifier. A
question about those things must never fall through to the refusal because
it was phrased in words the planner did not list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Iterable

from app.modules.assistant.concepts import DEDICATED_TOPICS, TOPIC_WORDS
from app.shared.schemas import AssistantIntent, AssistantLanguage, MatchStatus
from app.shared.text import normalise_party_name, normalise_reference

__all__ = ["Plan", "detect_language", "plan", "date_named", "reference_named"]

_URDU_SCRIPT = re.compile(r"[؀-ۿ]")
_NUMBER = re.compile(r"(?<![A-Za-z-])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![A-Za-z-])\d{4,}(?:\.\d+)?")


@dataclass(frozen=True)
class Plan:
    intent: AssistantIntent
    language: AssistantLanguage
    rule_id: str | None = None
    party: str | None = None
    amount: Decimal | None = None
    #: The glossary topic a `concept` plan explains (`concepts.CONCEPTS` key).
    topic: str | None = None
    limit: int = 5
    #: `matches`: restrict the readout to one match status; None for every row.
    status: MatchStatus | None = None
    #: `item`: what the question named. Either an identifier as typed — a
    #: review item, ledger row, bank line, invoice, flag, or document id, or
    #: an invoice number — or `KIND:digits` for "item 5", "row 16",
    #: "invoice 0087", "flag 9" (`KIND` is ITEM, ROW, INVOICE, or FLAG).
    reference: str | None = None
    #: `search_date`: the day asked about (the first of the month when the
    #: question named only a month), and which of the two it was.
    day: date | None = None
    granularity: str | None = None
    #: `unknown`: "audit" when the question used this audit's vocabulary but
    #: named no query the planner knows — so the refusal can say so, and
    #: point at the nearest things that can be asked.
    hint: str | None = None


def detect_language(question: str, forced: AssistantLanguage | None = None) -> AssistantLanguage:
    """Urdu when forced, when the question is in Urdu script, or asks for Urdu."""
    if forced is not None:
        return forced
    lowered = question.lower()
    if _URDU_SCRIPT.search(question) or "urdu" in lowered:
        return AssistantLanguage.URDU
    return AssistantLanguage.ENGLISH


@lru_cache(maxsize=1024)
def _pattern(needle: str) -> re.Pattern[str]:
    """A keyword as a whole-word match; a trailing `*` allows any ending.

    `sum` must not match inside "summary", and `flag` must match "flags" and
    "flagged" — so `flag*` is the spelling for the second and plain `sum` for
    the first. Only ASCII keywords get boundaries; Urdu ones are matched as
    substrings, because word boundaries in that script are unreliable.
    """
    prefix = needle.endswith("*")
    core = re.escape(needle.rstrip("*"))
    trailing = "" if prefix else r"(?![a-z0-9])"
    return re.compile(rf"(?<![a-z0-9]){core}{trailing}")


def _any(text: str, *needles: str) -> bool:
    for needle in needles:
        if needle.isascii():
            if _pattern(needle).search(text):
                return True
        elif needle in text:
            return True
    return False


# --------------------------------------------------------------------------- #
# Vocabularies
# --------------------------------------------------------------------------- #

#: Rule-specific vocabulary. Checked first, because "explain the structuring
#: flag" contains "flag" and must not fall through to the generic overview.
_RULE_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("structuring", ("structur*", "split payment*", "splitting", "same day", "تقسیم", "سٹرکچر")),
    ("weekend-entry", ("weekend*", "sunday*", "saturday*", "اتوار", "ہفتے", "ویک اینڈ", "چھٹی")),
    ("round-number", ("round number*", "round figure*", "round amount*", "round payment*", "راؤنڈ", "گول رقم")),
    ("near-limit", ("near limit*", "near-limit", "near the limit", "under the limit", "below the limit", "approval limit*", "حد کے قریب", "منظوری کی حد")),
    ("invoice-sequence-gap", ("sequence*", "gap*", "missing invoice number*", "numbering", "ترتیب", "نمبر غائب")),
)

#: Phrases that ask what a term *means* — the glossary's door. "What is the
#: total?" is not among them: a definite article or a possessive makes the
#: question about this case's thing, not the idea, so those are excluded.
_DEFINITIONAL = (
    "what is", "what are", "what does", "mean*", "define", "definition*",
    "difference between", "کیا ہے", "کیا ہیں", "کا مطلب", "تعریف",
)
#: …and these forms ask about a specific thing in the case, so they stay data
#: questions even though they start like the ones above. "What is in the bank
#: statement?" asks for its lines, not for what a bank statement is.
_DEFINITIONAL_EXCEPT = (
    "what is the", "what is this", "what is my", "what is our",
    "what are the", "what are these", "what are my", "what are our",
    "what is in", "what is on", "what's in", "what's on", "what is inside",
    "what is included", "میں کیا ہے", "میں کیا ہیں",
)
#: Phrases that ask for a lesson rather than a readout.
_EXPLAIN = (
    "explain*", "teach me", "tell me about", "help me understand", "how does", "how do",
    "سمجھائیں", "سمجھاؤ", "سکھائیں",
)
#: A first-time auditor saying so. Routes to the glossary when a topic is
#: named, to the (beginner-aware) help text otherwise.
_BEGINNER = (
    "i'm new", "i am new", "new to audit*", "first audit", "beginner*", "new to this",
    "where do i start", "شروع کہاں سے", "پہلی بار",
)

#: Someone asking whether they may ask — "can I ask you about one invoice?" —
#: without yet naming a thing the planner can look up. The answer is yes,
#: with the shape of a question that works; never a refusal.
_META = (
    "can i ask", "may i ask", "could i ask", "i have a question", "i want to ask",
    "i'd like to ask", "i would like to ask", "one question", "a question", "ask you something",
    "ask something", "ask about", "کیا میں پوچھ", "ایک سوال", "سوال پوچھ",
)

#: Words that say the question is about *this audit's* data, even when no
#: query above could be named. The refusal for such a question must not say
#: "not answerable from the documents" — it is answerable, once rephrased.
_DOMAIN = (
    "ledger", "bank", "invoice*", "payment*", "paid", "pay", "item*", "row*", "entr*",
    "transaction*", "audit*", "case", "match*", "vendor*", "supplier*", "amount*", "rupee*",
    "pkr", "rs", "flag*", "document*", "statement*", "record*", "account*", "reconcil*",
    "review*", "decision*", "report*", "client", "money", "cheque*", "check*", "receipt*",
    "voucher*", "expense*", "cost*", "purchase*", "party", "parties", "figure*", "number*",
    "total*", "date*", "month*", "result*", "finding*", "evidence", "extract*",
    "لیجر", "بینک", "انوائس", "ادائیگی", "آئٹم", "قطار", "آڈٹ", "اس کیس", "کیس میں", "کیس کا",
    "کیس کے", "کیس کی", "رقم", "دستاویز",
)

#: Identifier prefixes the case's records use. A token like "INV-2026-0087"
#: or "RI-0005" is an identifier; "month-on-month" is not (no digit), and
#: "Q2-2026" is not (unknown prefix), so neither is looked up as an item.
_KNOWN_PREFIXES = frozenset({"RI", "LED", "BNK", "INV", "DOC", "FLG", "RPT", "AUD", "CASE"})
_IDENTIFIER = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2,6})(?:[-/][A-Za-z0-9]+)+(?![A-Za-z0-9])")
#: "invoice 0087", "item 5", "row 16", "flag 9" — a kind and a number.
_NUMBERED = re.compile(
    r"(?<![a-z0-9])(item|items|ri|row|rows|entry|line|invoice|invoices|inv|bill|flag)"
    r"\s*(?:number|no\.?|num|#)?\s*(\d{1,6})(?![0-9,.])"
)
_NUMBERED_KIND = {
    "item": "ITEM", "items": "ITEM", "ri": "ITEM",
    "row": "ROW", "rows": "ROW", "entry": "ROW", "line": "ROW",
    "invoice": "INVOICE", "invoices": "INVOICE", "inv": "INVOICE", "bill": "INVOICE",
    "flag": "FLAG",
}

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
    "جنوری": 1, "فروری": 2, "مارچ": 3, "اپریل": 4, "مئی": 5, "جون": 6, "جولائی": 7,
    "اگست": 8, "ستمبر": 9, "اکتوبر": 10, "نومبر": 11, "دسمبر": 12,
}
#: Month names that may stand alone ("payments in June"). Abbreviations and
#: "may" need a day or a year beside them — "may I ask" is not a month.
_MONTHS_ALONE = {name for name in _MONTHS if len(name) > 3 or not name.isascii()} - {"may"}


def _alternation(names: Iterable[str]) -> str:
    return "|".join(sorted((re.escape(name) for name in names), key=len, reverse=True))


_ISO_DATE = re.compile(r"(?<![0-9])(20\d{2})-(\d{1,2})-(\d{1,2})(?![0-9])")
_NUMERIC_DATE = re.compile(r"(?<![0-9])(\d{1,2})[/.-](\d{1,2})[/.-](20\d{2})(?![0-9])")
_DAY_MONTH = re.compile(
    rf"(?<![0-9])(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_alternation(_MONTHS)})(?:[,\s]+(20\d{{2}}))?(?![a-z])"
)
_MONTH_DAY = re.compile(
    rf"(?<![a-z])({_alternation(_MONTHS)})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:[,\s]+(20\d{{2}}))?(?![0-9,.])"
)
_MONTH_YEAR = re.compile(rf"(?<![a-z])({_alternation(_MONTHS)})\s+(20\d{{2}})(?![0-9])")
_MONTH_ALONE = re.compile(rf"(?<![a-z])({_alternation(_MONTHS_ALONE)})(?![a-z])")


# --------------------------------------------------------------------------- #
# Parameter extraction
# --------------------------------------------------------------------------- #


def _party_named(question: str, parties: list[str]) -> str | None:
    """The party whose name the question mentions, if any.

    Whole-token matching over normalised names, so "Karachi" in a question
    finds Karachi Packaging Co. without a model. The party with the most
    tokens mentioned wins; ties go to the first in ledger order.
    """
    words = set(re.findall(r"[a-z0-9]+", question.lower()))
    if not words:
        return None
    best: tuple[int, str] | None = None
    for party in parties:
        tokens = [token for token in normalise_party_name(party).split() if len(token) > 2]
        hits = sum(1 for token in tokens if token in words)
        if hits and (best is None or hits > best[0]):
            best = (hits, party)
    return best[1] if best else None


def _amount_named(question: str) -> Decimal | None:
    for match in _NUMBER.finditer(question):
        raw = match.group(0)
        if "," not in raw and "." not in raw and len(raw) == 4 and raw.startswith("20"):
            continue  # a bare year, not an amount
        try:
            value = Decimal(raw.replace(",", ""))
        except InvalidOperation:
            continue
        if value >= 100:
            return value
    return None


def reference_named(question: str, references: Iterable[str] = ()) -> str | None:
    """The identifier the question names, if any.

    Three ways, in order: an identifier the case actually uses, however the
    separators were typed ("ri 0005", "INV 2026/0087"); anything shaped like
    one of the case's identifiers ("LED-0014"); or a kind and a number
    ("invoice 0087", "row 16", "item 5"), returned as `KIND:digits` for the
    query to resolve.
    """
    known: dict[str, str] = {}
    prefixes = set(_KNOWN_PREFIXES)
    for reference in references:
        if not reference:
            continue
        known[normalise_reference(reference)] = reference
        head = re.match(r"[A-Za-z]+", reference)
        if head:
            prefixes.add(head.group(0).upper())

    if known:
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9/-]*", question)
        for index, token in enumerate(tokens):
            candidates = [token]
            if index + 1 < len(tokens):
                candidates.append(token + tokens[index + 1])
            for candidate in candidates:
                normalised = normalise_reference(candidate)
                if len(normalised) >= 4 and normalised in known:
                    return known[normalised]

    for match in _IDENTIFIER.finditer(question):
        token = match.group(0)
        if match.group(1).upper() in prefixes and any(ch.isdigit() for ch in token):
            return token.upper()

    numbered = _NUMBERED.search(question.lower())
    if numbered:
        return f"{_NUMBERED_KIND[numbered.group(1)]}:{numbered.group(2)}"
    return None


def date_named(question: str, default_year: int | None = None) -> tuple[date, str] | None:
    """The day or month the question names, as (anchor date, granularity).

    Accepts ISO (2026-06-11), day-first numeric (11/06/2026), "11 June",
    "June 11th", "June 2026", and a month on its own. A day without a year
    takes `default_year` (the year the case's rows are in) or the current
    year. Returns None when no date is written.
    """
    text = question.lower()
    year_default = default_year or date.today().year

    def build(year: int, month: int, day: int, granularity: str) -> tuple[date, str] | None:
        try:
            return date(year, month, day), granularity
        except ValueError:
            return None

    match = _ISO_DATE.search(text)
    if match:
        return build(int(match.group(1)), int(match.group(2)), int(match.group(3)), "day")
    match = _NUMERIC_DATE.search(text)
    if match:
        return build(int(match.group(3)), int(match.group(2)), int(match.group(1)), "day")
    match = _DAY_MONTH.search(text)
    if match:
        year = int(match.group(3)) if match.group(3) else year_default
        return build(year, _MONTHS[match.group(2)], int(match.group(1)), "day")
    match = _MONTH_DAY.search(text)
    if match:
        year = int(match.group(3)) if match.group(3) else year_default
        return build(year, _MONTHS[match.group(1)], int(match.group(2)), "day")
    match = _MONTH_YEAR.search(text)
    if match:
        return build(int(match.group(2)), _MONTHS[match.group(1)], 1, "month")
    match = _MONTH_ALONE.search(text)
    if match:
        return build(year_default, _MONTHS[match.group(1)], 1, "month")
    return None


def _topic_named(lowered: str) -> str | None:
    """The glossary topic the question names, with this file's keyword style."""
    for topic, words in TOPIC_WORDS.items():
        if _any(lowered, *words):
            return topic
    return None


def _is_definitional(lowered: str) -> bool:
    if _any(lowered, *_DEFINITIONAL_EXCEPT):
        return False
    return _any(lowered, *_DEFINITIONAL)


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #


def plan(
    question: str,
    parties: list[str],
    language: AssistantLanguage | None = None,
    references: Iterable[str] = (),
    default_year: int | None = None,
) -> Plan:
    """Decide what the question asks for. Pure; the same question always plans the same.

    Args:
        question: What was asked, in English or Urdu.
        parties: The party names the ledger carries, in ledger order.
        language: Force the answer language; detected when omitted.
        references: Every identifier the case uses (review items, ledger
            rows, bank lines, invoices and their numbers, flags, documents),
            so "ri 0005" is recognised however it was typed.
        default_year: The year to assume for a date written without one.
    """
    text = question.strip()
    lowered = text.lower()
    lang = detect_language(text, language)

    # -- a lesson, before anything else: "help me understand materiality" is a
    #    glossary question even though it says "help", and "I'm new to
    #    auditing, explain reconciliation" should never be answered with a
    #    greeting. Falls through untouched when no topic is named. A question
    #    that names a rule or a flag ("explain the approval limit flag") wants
    #    this case's rule readout, not the glossary — except for the dedicated
    #    topics, where "what is a red flag?" is the glossary question itself.
    topic = _topic_named(lowered)
    mentions_rule_or_flag = _any(lowered, "flag*", "flagged", "rule*")
    if topic is not None and _is_definitional(lowered) and (
        topic in DEDICATED_TOPICS or not mentions_rule_or_flag
    ):
        return Plan(AssistantIntent.CONCEPT, lang, topic=topic)
    if (
        topic is not None
        and topic not in DEDICATED_TOPICS
        and not mentions_rule_or_flag
        and _any(lowered, *_EXPLAIN)
    ):
        return Plan(AssistantIntent.CONCEPT, lang, topic=topic)
    if _any(lowered, *_BEGINNER):
        return Plan(AssistantIntent.HELP, lang)

    # -- greetings and help --------------------------------------------------
    if len(lowered) < 4 or _any(
        lowered, "help", "hello", "hi", "hey", "what can you", "what can i ask", "salam*",
        "assalam*", "مدد", "سلام", "کیا پوچھ",
    ):
        return Plan(AssistantIntent.HELP, lang)

    # -- one thing, by its identifier: "RI-0005", "invoice INV-2026-0087",
    #    "row 16". The sharpest question there is, so it goes before every
    #    broader one — "why is RI-0005 flagged?" wants that row, flags and all.
    reference = reference_named(text, references)
    if reference is not None:
        return Plan(AssistantIntent.ITEM, lang, reference=reference)

    # -- things the uploaded data cannot answer ------------------------------
    if _any(
        lowered, "sales", "revenue*", "profit*", "loss*", "margin*", "income", "turnover",
        "tax return*", "vat", "gst", "forecast*", "budget*", "منافع", "فروخت", "آمدنی", "نقصان",
    ):
        return Plan(AssistantIntent.UNSUPPORTED, lang)

    # -- rule explanations ---------------------------------------------------
    for rule_id, words in _RULE_WORDS:
        if _any(lowered, *words):
            return Plan(AssistantIntent.RULE, lang, rule_id=rule_id)

    if _any(lowered, "duplicate*", "twice", "double*", "paid again", "repeat*", "دوبارہ", "ڈپلیکیٹ", "دو بار"):
        return Plan(AssistantIntent.DUPLICATES, lang)

    if _any(lowered, "benford*", "first digit*", "first-digit", "digit distribution", "بینفورڈ", "پہلا ہندسہ"):
        return Plan(AssistantIntent.BENFORD, lang)

    if _any(lowered, "unmatched", "no bank", "not in the bank", "not found in bank", "fictitious", "no counterpart", "غیر مماثل", "بینک میں نہیں", "فرضی"):
        return Plan(AssistantIntent.UNMATCHED, lang)

    if _any(lowered, "missing evidence", "missing document*", "missing invoice*", "no supporting", "without invoice*", "without evidence", "no receipt*", "no invoice*", "unreadable", "evidence missing", "ثبوت", "دستاویز غائب", "انوائس نہیں"):
        return Plan(AssistantIntent.MISSING_EVIDENCE, lang)

    # -- a specific party, before totals: "how much did we pay Gulberg" -------
    party = _party_named(lowered, parties)
    if party is not None:
        return Plan(AssistantIntent.PARTY, lang, party=party)

    # -- a specific day or month: "what was paid on 11 June", "payments in June"
    dated = date_named(text, default_year)
    if dated is not None:
        return Plan(AssistantIntent.SEARCH_DATE, lang, day=dated[0], granularity=dated[1])

    # -- the evidence itself: the invoices, the bank statement's lines --------
    if _any(lowered, "invoice*", "bill*", "انوائس"):
        return Plan(AssistantIntent.INVOICES, lang)

    if _any(
        lowered, "bank statement*", "bank line*", "bank transaction*", "bank entr*", "bank side",
        "bank record*", "bank payment*", "bank row*", "bank account*", "bank balance*", "balance*",
        "statement line*", "statement entr*", "in the bank", "on the bank", "from the bank",
        "bank shows", "bank say*", "بینک",
    ):
        return Plan(AssistantIntent.BANK, lang)

    # -- the match results: all of them, or one status -----------------------
    if _any(lowered, "partial*", "partly", "جزوی"):
        return Plan(AssistantIntent.MATCHES, lang, status=MatchStatus.PARTIAL)
    if _any(
        lowered, "match*", "reconciled", "reconciliation result*", "reconciliation status*",
        "three-way", "three way", "counterpart*", "میچ", "مماثل", "ملاپ", "ملان",
    ):
        only_matched = _any(lowered, "matched", "مماثل") and not _any(
            lowered, "result*", "all", "every", "how", "overview", "status*", "summar*",
        )
        return Plan(
            AssistantIntent.MATCHES, lang,
            status=MatchStatus.MATCHED if only_matched else None,
        )

    # -- the rest of the engagement's record, read-only. Each is phrased so a
    #    question about the case's numbers above cannot fall into them.
    if _any(
        lowered, "all cases", "all my cases", "all the cases", "every case", "each case",
        "which cases", "how many cases", "list cases", "list the cases", "case list",
        "other case*", "another case", "across cases", "what case*",
        "تمام کیس", "ہر کیس", "کتنے کیس", "دوسرے کیس",
    ):
        return Plan(AssistantIntent.CASES, lang)

    if _any(
        lowered, "what did you read", "what did the model read", "what did the ai read",
        "what did it read", "what did you extract", "what was read", "extract*", "extraction*",
        "vision model*", "read from the document*", "کیا پڑھا", "پڑھا گیا",
    ):
        return Plan(AssistantIntent.EXTRACTIONS, lang)

    if _any(
        lowered, "decision*", "decided", "who approved", "who rejected", "approved so far",
        "approvals", "sign off", "sign-off", "signoff", "what did we decide",
        "فیصلے", "فیصلہ",
    ):
        return Plan(AssistantIntent.DECISIONS, lang)

    if _any(lowered, "report*", "export*", "deliverable*", "رپورٹ"):
        return Plan(AssistantIntent.REPORTS, lang)

    if _any(
        lowered, "history", "timeline", "what happened", "audit trail*", "trail", "event log",
        "who did what", "when did", "when was", "لاگ", "تاریخچہ", "کیا ہوا", "کب ہوا",
    ):
        return Plan(AssistantIntent.HISTORY, lang)

    if _any(
        lowered, "what document*", "which document*", "what files", "which files", "uploaded",
        "upload*", "documents did", "documents are", "documents have", "document list",
        "what sources", "which sources", "کون سے دستاویزات", "کیا اپ لوڈ",
    ):
        return Plan(AssistantIntent.DOCUMENTS, lang)

    # -- how sure the reading is ---------------------------------------------
    if _any(
        lowered, "confiden*", "how sure", "how reliable", "how accurate", "accura*", "certain*",
        "uncertain*", "read correctly", "misread*", "reading quality", "اعتماد", "یقین", "بھروسہ",
    ):
        return Plan(AssistantIntent.CONFIDENCE, lang)

    # -- the case itself: who it is for, what period, where it stands --------
    if _any(
        lowered, "client*", "case period", "audit period", "period cover*", "period of",
        "which period", "what period", "date range", "case status", "case detail*", "case info*",
        "about this case", "about the case", "which company", "what company", "whose", "case id",
        "کلائنٹ", "کیس کی مدت", "کیس کی حیثیت", "کس کمپنی", "کیس کے بارے",
    ):
        return Plan(AssistantIntent.CASE_INFO, lang)

    # -- a specific amount: "who was paid 49,500" -----------------------------
    amount = _amount_named(text)
    if amount is not None and _any(
        lowered, "amount*", "payment of", "paid", "find", "search", "who", "which", "any", "look",
        "رقم", "ادائیگی", "تلاش", "کس", "کون",
    ):
        return Plan(AssistantIntent.SEARCH_AMOUNT, lang, amount=amount)

    if _any(lowered, "compare*", "month over month", "month-on-month", "versus", "vs", "by month", "monthly", "each month", "per month", "مہینے", "ماہانہ", "موازنہ"):
        return Plan(AssistantIntent.COMPARE_MONTHS, lang)

    if _any(lowered, "top vendor*", "top supplier*", "top part*", "biggest vendor*", "largest vendor*", "biggest supplier*", "largest supplier*", "most paid", "paid the most", "by vendor", "by supplier", "by party", "per vendor", "which vendor*", "vendor*", "supplier*", "parties", "سب سے بڑا فریق", "سب سے بڑا وینڈر", "کس فریق کو سب سے زیادہ", "وینڈر", "فریق"):
        return Plan(AssistantIntent.TOP_VENDORS, lang)

    if _any(lowered, "largest", "biggest", "highest", "top payment*", "top expense*", "top 5", "top five", "top ten", "top 10", "سب سے بڑی", "سب سے زیادہ رقم"):
        return Plan(AssistantIntent.LARGEST, lang)

    if _any(lowered, "total*", "sum", "how much", "expense*", "expenditure*", "spend*", "spent", "paid out", "outflow*", "کل", "کتنا", "اخراجات", "مجموعی"):
        return Plan(AssistantIntent.TOTALS, lang)

    if _any(lowered, "flag*", "risk*", "fraud*", "red flag*", "suspicious", "anomal*", "concern*", "attention", "warning*", "alert*", "issue*", "problem*", "wrong", "نشان", "خطر", "مشکوک", "فلیگ", "مسئل"):
        return Plan(AssistantIntent.FLAGS, lang)

    if _any(
        lowered, "summar*", "overview", "status", "progress", "pending", "where are we",
        "how many items", "result*", "outcome*", "finding*", "what did you find", "everything about",
        "all about", "full picture", "whole picture", "complete picture", "whole audit", "entire audit",
        "so far", "state of", "خلاصہ", "صورتحال", "زیر التوا", "کتنے آئٹم", "نتائج", "نتیجہ",
    ):
        return Plan(AssistantIntent.SUMMARY, lang)

    # -- every row, listed ----------------------------------------------------
    if _any(
        lowered, "all items", "all the items", "every item", "each item", "all rows", "all the rows",
        "every row", "all entries", "all the entries", "every entry", "all transactions",
        "all the transactions", "every transaction", "all payments", "all the payments",
        "every payment", "list items", "list the items", "list all", "list everything", "show all",
        "show everything", "show me everything", "full list", "whole list", "entire ledger",
        "whole ledger", "the ledger", "ledger row*", "ledger entr*", "ledger line*", "line item*",
        "how many rows", "how many entries", "how many transactions", "how many payments",
        "تمام قطاریں", "ساری قطاریں", "تمام آئٹم", "سب آئٹم", "پوری فہرست", "تمام ادائیگیاں", "لیجر",
    ):
        return Plan(AssistantIntent.LEDGER, lang)

    if amount is not None:
        return Plan(AssistantIntent.SEARCH_AMOUNT, lang, amount=amount)

    # -- "can I ask you something?" — yes. Say what works. --------------------
    if _any(lowered, *_META):
        return Plan(AssistantIntent.HELP, lang)

    hint = "audit" if _any(lowered, *_DOMAIN) else None
    return Plan(AssistantIntent.UNKNOWN, lang, hint=hint)
