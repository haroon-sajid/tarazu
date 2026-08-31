"""Ask Tarazu answers *from* the case, not only about it.

The first assistant answered the case's headline questions and refused the
rest — including "can I ask you one specific invoice match result?", which
names two things the case holds (invoices, match results) in words the
planner did not list. These tests pin the layer that closes that gap: the
match results row by row, one row or invoice or bank line by its identifier
however it was typed, the invoices and bank lines the rows rest on, every
ledger row, a day or a month, how confidently the evidence was read, and the
case itself — each computed in code over the sample case and asserted to the
figure. Then the two behaviours around the edge: a permission question is
answered yes, and an on-topic question the planner still cannot place is
refused in words that say so.

The last block covers the model-assisted classifier (ADR 0006's foreseen
extension): the model may choose *which* query runs, and every parameter it
names is checked against the question and the case before it is used.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.modules.assistant import service as assistant
from app.modules.assistant.classifier import _checked_date
from app.modules.assistant.planner import _amount_named, date_named, plan
from app.modules.assistant.service import ROUTED_BY_LABEL, WorkspaceContext, answer_question
from app.modules.assistant.settings import AssistantSettings
from app.shared.schemas import (
    AssistantIntent,
    BenfordResult,
    CaseRecord,
    CaseStatus,
    Confidence,
    MatchStatus,
)
from tests.conftest import DEMO_USER, load_sample_dashboard, load_sample_queue
from tests.test_assistant import (
    a_bank_extraction,
    a_report_record,
    an_invoice_extraction,
    the_documents,
)

NO_MODEL = AssistantSettings(
    api_key=None, base_url="http://unused", model="none", demo_mode=True,
    phrasing_enabled=True, request_timeout_seconds=1.0,
)
WITH_MODEL = AssistantSettings(
    api_key="test-key", base_url="http://unused", model="qwen-plus", demo_mode=False,
    phrasing_enabled=True, request_timeout_seconds=1.0,
)

PARTIES = ["Gulberg Traders (Pvt) Ltd", "Karachi Packaging Co.", "Shalimar Trading Co"]
REFERENCES = ["RI-0005", "LED-0014", "BNK-0051", "INV-0087", "INV-2026-0087", "SMW/2026/0431", "FLG-0009", "DOC-INV-0087"]


@pytest.fixture()
def case_data():
    queue = load_sample_queue()
    dashboard = load_sample_dashboard()
    case = CaseRecord(
        case_id=queue.case_id, client_name="Haroon Textiles", status=CaseStatus.READY_FOR_REVIEW,
        created_by=DEMO_USER.user_id, created_at=datetime(2026, 6, 19, 8, 0, tzinfo=timezone.utc),
    )
    return case, queue.items, BenfordResult.model_validate(dashboard["benford"])


@pytest.fixture()
def workspace(case_data):
    case, _items, _benford = case_data
    return WorkspaceContext(
        documents=the_documents(),
        extractions=[a_bank_extraction(), an_invoice_extraction()],
        reports=[a_report_record(case.case_id)],
        trail=[], cases=[], active_case_id=case.case_id,
    )


def ask(case_data, question: str, context=None, settings=NO_MODEL, client=None):
    case, items, benford = case_data
    return answer_question(
        question, case=case, items=items, benford=benford, context=context,
        settings=settings, client=client,
    )


def facts(answer) -> dict[str, str]:
    return {fact.label: fact.value for fact in answer.facts}


# --------------------------------------------------------------------------- #
# Routing: the audit's own vocabulary always lands somewhere
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "question,intent",
    [
        ("can i ask you one specifi invoice match result?", AssistantIntent.INVOICES),
        ("which invoices are in this case?", AssistantIntent.INVOICES),
        ("how many invoices do we have", AssistantIntent.INVOICES),
        ("match results", AssistantIntent.MATCHES),
        ("how did the matching go?", AssistantIntent.MATCHES),
        ("which items matched?", AssistantIntent.MATCHES),
        ("partial matches", AssistantIntent.MATCHES),
        ("what is in the bank statement?", AssistantIntent.BANK),
        ("show me the bank lines", AssistantIntent.BANK),
        ("list all ledger rows", AssistantIntent.LEDGER),
        ("show me everything", AssistantIntent.LEDGER),
        ("what was paid on 11 june?", AssistantIntent.SEARCH_DATE),
        ("payments in june", AssistantIntent.SEARCH_DATE),
        ("what happened on 2026-06-11", AssistantIntent.SEARCH_DATE),
        ("who is the client?", AssistantIntent.CASE_INFO),
        ("what period does this case cover?", AssistantIntent.CASE_INFO),
        ("how confident was the reading?", AssistantIntent.CONFIDENCE),
        ("which readings are low confidence?", AssistantIntent.CONFIDENCE),
        ("RI-0005", AssistantIntent.ITEM),
        ("tell me about invoice INV-2026-0087", AssistantIntent.ITEM),
        ("row 16", AssistantIntent.ITEM),
        ("why is LED-0014 flagged?", AssistantIntent.ITEM),
        ("can i ask you a question?", AssistantIntent.HELP),
        ("may i ask something about this audit?", AssistantIntent.HELP),
        ("what about the ledger totals for the whole audit", AssistantIntent.TOTALS),
        ("What was our profit?", AssistantIntent.UNSUPPORTED),
        ("What is the weather in Lahore?", AssistantIntent.UNKNOWN),
    ],
)
def test_questions_about_the_data_are_routed(question: str, intent: AssistantIntent) -> None:
    assert plan(question, PARTIES).intent is intent
    assert plan(question, PARTIES) == plan(question, PARTIES)


def test_the_match_readout_can_be_narrowed_to_one_status() -> None:
    assert plan("partial matches", PARTIES).status is MatchStatus.PARTIAL
    assert plan("which items matched?", PARTIES).status is MatchStatus.MATCHED
    assert plan("match results", PARTIES).status is None


def test_an_identifier_is_recognised_however_it_was_typed() -> None:
    assert plan("what about ri 0005", PARTIES, references=REFERENCES).reference == "RI-0005"
    assert plan("inv 2026/0087 please", PARTIES, references=REFERENCES).reference == "INV-2026-0087"
    assert plan("LED-0014", PARTIES).reference == "LED-0014"
    assert plan("invoice 0087", PARTIES).reference == "INVOICE:0087"
    assert plan("item 5", PARTIES).reference == "ITEM:5"
    # Not every hyphenated token is an identifier.
    assert plan("what about Q2-2026", PARTIES).intent is not AssistantIntent.ITEM
    assert plan("month-on-month comparison", PARTIES).intent is AssistantIntent.COMPARE_MONTHS


def test_dates_are_parsed_in_the_forms_people_type() -> None:
    assert date_named("what was paid on 11 june", 2026) == (date(2026, 6, 11), "day")
    assert date_named("June 11th, 2026") == (date(2026, 6, 11), "day")
    assert date_named("11/06/2026") == (date(2026, 6, 11), "day")
    assert date_named("on 2026-06-11") == (date(2026, 6, 11), "day")
    assert date_named("payments in june", 2026) == (date(2026, 6, 1), "month")
    assert date_named("may i ask", 2026) is None
    assert date_named("top 5 payments", 2026) is None


def test_a_bare_year_is_not_an_amount() -> None:
    assert _amount_named("in 2026") is None
    assert _amount_named("2,026") == Decimal("2026")
    assert _amount_named("49,500") == Decimal("49500")


# --------------------------------------------------------------------------- #
# The answers, computed from the case
# --------------------------------------------------------------------------- #


def test_the_refused_question_now_lists_the_invoices_with_their_match_results(case_data) -> None:
    answer = ask(case_data, "can i ask you one specifi invoice match result?")
    assert answer.intent is AssistantIntent.INVOICES
    assert answer.grounded is True
    assert answer.answer_confidence is Confidence.HIGH
    assert answer.text.startswith(
        "2 invoices in the evidence, totalling PKR 409,280.00; 7 ledger rows have no invoice behind them:"
    )
    assert (
        "• INV-2026-0087 — Karachi Packaging Co., PKR 96,400.00, dated 2026-06-03 (document DOC-INV-0087, page 1): "
        "settled by 2 ledger rows — RI-0002 on 2026-06-05 (matched, pending), RI-0008 on 2026-06-16 (matched, pending) "
        "— the same invoice paid more than once" in answer.text
    )
    assert "• SMW/2026/0431 — Sialkot Metal Works, PKR 312,880.00, dated 2026-06-15" in answer.text
    assert "Name an invoice by its number" in answer.text
    assert {"DOC-INV-0087", "DOC-INV-0431"} <= {c.document_id for c in answer.citations}
    assert facts(answer)["Invoices in the evidence"] == "2"
    assert facts(answer)["Ledger rows with no invoice"] == "7"


def test_an_invoice_number_returns_every_row_that_settles_it(case_data) -> None:
    answer = ask(case_data, "tell me about invoice INV-2026-0087")
    assert answer.intent is AssistantIntent.ITEM
    assert answer.text.startswith('"INV-2026-0087" matches 2 items:')
    assert "RI-0002 — Karachi Packaging Co., PKR 96,400.00 on 2026-06-05." in answer.text
    assert "RI-0008 — Karachi Packaging Co., PKR 96,400.00 on 2026-06-16." in answer.text
    assert "• Invoice: INV-2026-0087 dated 2026-06-03, PKR 96,400.00, Karachi Packaging Co. (page 1)." in answer.text
    assert "• Bank statement: BNK-0031 on 2026-06-05, PKR 96,400.00, \"CHQ 004412 KARACHI PACKAGING CO\" (page 1)." in answer.text
    assert "• Flags (1): duplicate-invoice (high) — Invoice INV-2026-0087 is paid twice" in answer.text
    assert facts(answer)["Items found"] == "2"
    assert facts(answer)["RI-0002 invoice"].startswith("INV-2026-0087 dated 2026-06-03")
    assert {c.review_item_id for c in answer.citations} == {"RI-0002", "RI-0008"}


def test_a_sheet_row_number_finds_the_ledger_row(case_data) -> None:
    answer = ask(case_data, "row 16")
    assert answer.intent is AssistantIntent.ITEM
    assert answer.text.startswith("RI-0005 — Hussain Brothers & Sons, PKR 49,500.00 on 2026-06-11.")
    assert "• Ledger: LED-0014 (sheet row 16), \"Dyeing services - part 1\", account 5040." in answer.text
    assert "• Invoice: none attached." in answer.text
    assert "• Match: matched (high strength) by rule exact-amount-exact-date" in answer.text
    assert "structuring (high)" in answer.text and "near-limit (high)" in answer.text
    assert "• Decision: pending — awaiting an explicit human decision on the Review screen." in answer.text


def test_an_invoice_named_by_its_digits_shows_the_weakest_reading(case_data) -> None:
    answer = ask(case_data, "invoice 0431")
    assert answer.text.startswith("RI-0009 — Sialkot Metal Works, PKR 312,880.00 on 2026-06-17.")
    assert "• Invoice: SMW/2026/0431 dated 2026-06-15, PKR 312,880.00, Sialkot Metal Works (page 1)." in answer.text
    assert "• Extraction confidence: low — 2 readings, 0 unreadable; weakest reading: amount = 312880.0 (low) from DOC-INV-0431 page 1." in answer.text
    assert any(c.document_id == "DOC-INV-0431" for c in answer.citations)


def test_an_item_card_shows_the_decision_and_its_reason(case_data) -> None:
    answer = ask(case_data, "RI-0004")
    assert "• Match: partial (low strength) by rule same-party-same-date-amount-mismatch" in answer.text
    assert (
        "• Decision: rejected by user-demo-auditor at 2026-06-19 10:02 — Ledger amount is wrong. "
        "The bank shows 49,500.00. Returned to the client for correction." in answer.text
    )
    assert "correction.." not in answer.text


def test_an_identifier_the_case_does_not_carry_is_a_grounded_not_found(case_data) -> None:
    answer = ask(case_data, "INV-9999")
    assert answer.intent is AssistantIntent.ITEM
    assert answer.grounded is True
    assert answer.text.startswith('No item in this case carries the reference "INV-9999".')
    assert answer.citations == []
    assert facts(answer)["Items found"] == "0"


def test_match_results_name_the_rule_and_the_counterpart_of_every_row(case_data) -> None:
    answer = ask(case_data, "match results")
    assert answer.intent is AssistantIntent.MATCHES
    assert answer.text.startswith(
        "How the 10 ledger rows reconciled: 8 matched, 1 partial, 1 unmatched; match strength 6 high, 2 medium, 2 low. "
        "The rows total PKR 2,685,830.00."
    )
    assert (
        "(RI-0002): matched (high) by exact-amount-exact-date — bank line BNK-0031 (2026-06-05, p.1); invoice INV-2026-0087."
        in answer.text
    )
    assert "(RI-0010): unmatched (low) by no-candidate-found — no bank line and no invoice." in answer.text
    assert "Matching is deterministic code" in answer.text
    assert facts(answer)["Match results (matched / partial / unmatched)"] == "8 / 1 / 1"
    assert len(answer.citations) == 8


def test_match_results_can_be_narrowed_to_one_status(case_data) -> None:
    matched = ask(case_data, "which items matched?")
    assert matched.text.startswith("8 matched rows, totalling PKR 2,452,430.00:")
    assert "RI-0004" not in matched.text and "RI-0010" not in matched.text

    partial = ask(case_data, "partial matches")
    assert partial.text.startswith("1 partial row, totalling PKR 45,900.00:")
    assert "(RI-0004): partial (low) by same-party-same-date-amount-mismatch — bank line BNK-0044 (2026-06-10, p.2)." in partial.text


def test_the_bank_statement_lines_are_listed_with_their_pages(case_data, workspace) -> None:
    answer = ask(case_data, "what is in the bank statement?")
    assert answer.intent is AssistantIntent.BANK
    assert answer.text.startswith(
        "9 bank statement lines are matched to ledger rows, totalling PKR 2,501,930.00, on page(s) 1, 2, 3; "
        "1 ledger row has no bank line."
    )
    assert (
        "• BNK-0012 — 2026-06-02, PKR 284,000.00, \"IBFT GULBERG TRADERS PVT LTD\" (page 1, balance PKR 4,821,330.00) "
        "→ pays RI-0001 Gulberg Traders (Pvt) Ltd" in answer.text
    )
    # The statement's pages are cited first (one citation per page region);
    # the ledger rows those lines pay follow.
    statement = [c for c in answer.citations if c.document_id == "DOC-BNK-001"]
    assert answer.citations[:3] == statement
    assert {c.page for c in statement} == {1, 2, 3}
    assert "Statement lines read by the vision model" not in facts(answer)

    with_context = ask(case_data, "what is in the bank statement?", context=workspace)
    assert "The vision model read 2 lines from the statement in all." in with_context.text
    assert facts(with_context)["Statement lines read by the vision model"] == "2"


def test_every_ledger_row_is_listed_in_date_order(case_data) -> None:
    answer = ask(case_data, "list all ledger rows")
    assert answer.intent is AssistantIntent.LEDGER
    assert answer.text.startswith(
        "The ledger has 10 rows totalling PKR 2,685,830.00, dated 2026-06-02 to 2026-06-18, to 8 parties:"
    )
    lines = [line for line in answer.text.splitlines() if line.startswith("•")]
    assert len(lines) == 10
    assert lines[0] == "• 2026-06-02 — Gulberg Traders (Pvt) Ltd, PKR 284,000.00 (RI-0001, sheet row 5): matched, approved — Yarn purchase - June lot 1"
    assert lines[4] == "• 2026-06-11 — Hussain Brothers & Sons, PKR 49,500.00 (RI-0005, sheet row 16): matched, pending, 2 flags — Dyeing services - part 1"
    assert lines[-1].startswith("• 2026-06-18 — Shalimar Trading Co, PKR 187,500.00 (RI-0010, sheet row 33): unmatched, pending")


def test_a_day_is_searched_across_ledger_bank_invoices_and_decisions(case_data) -> None:
    eleventh = ask(case_data, "what was paid on 11 june?")
    assert eleventh.intent is AssistantIntent.SEARCH_DATE
    assert eleventh.text.startswith(
        "On 2026-06-11: 2 ledger rows totalling PKR 99,000.00, 2 bank lines, 0 invoices dated then, 0 decisions taken."
    )
    assert "• Hussain Brothers & Sons, PKR 49,500.00 (RI-0005): matched, decision pending" in eleventh.text
    assert "• BNK-0051: PKR 49,500.00, \"IBFT HUSSAIN BROTHERS AND SONS\" (page 2) → pays RI-0005" in eleventh.text

    # The 19th has no ledger row, but a bank clearing and the two decisions.
    nineteenth = ask(case_data, "what happened on 19 June 2026?")
    assert nineteenth.text.startswith(
        "On 2026-06-19: 0 ledger rows totalling PKR 0.00, 1 bank line, 0 invoices dated then, 2 decisions taken."
    )
    assert "• BNK-0079: PKR 312,880.00, \"IBFT SIALKOT METAL WORKS\" (page 3) → pays RI-0009" in nineteenth.text
    assert "• RI-0001: approved by user-demo-auditor at 2026-06-19 09:41" in nineteenth.text
    assert "• RI-0004: rejected by user-demo-auditor at 2026-06-19 10:02 — Ledger amount is wrong." in nineteenth.text


def test_a_month_is_searched_and_an_invoice_is_counted_once(case_data) -> None:
    answer = ask(case_data, "payments in june")
    assert answer.text.startswith(
        "In June 2026: 10 ledger rows totalling PKR 2,685,830.00, 9 bank lines, 2 invoices dated then, 2 decisions taken."
    )


def test_a_day_with_nothing_on_it_says_so_and_gives_the_range(case_data) -> None:
    answer = ask(case_data, "what was paid on 25 june?")
    assert answer.grounded is True
    assert answer.text == (
        "Nothing in this case is dated 2026-06-25: no ledger row, bank line, invoice, or decision. "
        "The ledger runs from 2026-06-02 to 2026-06-18."
    )


def test_the_case_itself_is_described(case_data, workspace) -> None:
    answer = ask(case_data, "who is the client?")
    assert answer.intent is AssistantIntent.CASE_INFO
    assert answer.text.startswith("Haroon Textiles — case CASE-2026-06-STX, status ready for review.")
    assert "Period 2026-06-02 to 2026-06-18 (taken from the ledger rows; the case record sets no period)." in answer.text
    assert (
        "10 ledger rows totalling PKR 2,685,830.00 across 8 parties: 8 matched, 1 partial, 1 unmatched; "
        "1 approved, 1 rejected, 8 pending; 8 flags." in answer.text
    )
    assert "Documents:" not in answer.text
    assert facts(answer)["Client"] == "Haroon Textiles"

    with_context = ask(case_data, "who is the client?", context=workspace)
    assert "Documents: 3 — 1 bank statement, 1 invoice, 1 ledger. Reports generated: 1." in with_context.text


def test_extraction_confidence_is_read_out_per_item(case_data) -> None:
    answer = ask(case_data, "how confident was the reading?")
    assert answer.intent is AssistantIntent.CONFIDENCE
    assert answer.text.startswith(
        "Extraction confidence across 10 items: 8 high, 1 medium, 1 low; 0 source values unreadable."
    )
    assert "The 2 items below high confidence:" in answer.text
    assert "(RI-0009): low confidence — weakest reading: amount = 312880.0 (low) from DOC-INV-0431 page 1" in answer.text
    assert "(RI-0003): medium confidence — weakest reading: amount = 63750.0 (medium) from DOC-BNK-001 page 2" in answer.text
    assert "match strength is a separate, deterministic score" in answer.text
    assert facts(answer)["Items by extraction confidence (high / medium / low)"] == "8 / 1 / 1"


def test_a_permission_question_is_answered_yes_with_the_shapes_that_work(case_data) -> None:
    answer = ask(case_data, "can i ask you a question?")
    assert answer.intent is AssistantIntent.HELP
    assert answer.grounded is True
    assert answer.text.startswith("Yes — ask away.")
    assert "\"invoice INV-2026-0087\"" in answer.text


def test_an_on_topic_question_the_planner_cannot_place_is_refused_in_those_words(case_data) -> None:
    answer = ask(case_data, "are the payments okay")
    assert answer.intent is AssistantIntent.UNKNOWN
    assert answer.grounded is False
    assert answer.answer_confidence is Confidence.LOW
    assert answer.text.startswith("That sounds like a question about this audit, but I couldn't tell which part of it you mean")
    assert "\"match results\"" in answer.text


def test_an_off_topic_question_gets_the_plain_refusal_in_either_language(case_data) -> None:
    english = ask(case_data, "What is the weather in Lahore?")
    assert english.text.startswith("I can't answer that from this case's uploaded documents")
    urdu = ask(case_data, "آج لاہور کا موسم کیسا ہے؟")
    assert urdu.text.startswith("میں اس سوال کا جواب")


def test_an_urdu_data_question_is_answered_in_urdu(case_data) -> None:
    answer = ask(case_data, "اس کیس میں کون سی انوائسز ہیں؟")
    assert answer.intent is AssistantIntent.INVOICES
    assert "2 انوائسز" in answer.text and "INV-2026-0087" in answer.text
    matches = ask(case_data, "میچ کے نتائج")
    assert matches.intent is AssistantIntent.MATCHES
    assert "8 مماثل" in matches.text


# --------------------------------------------------------------------------- #
# The model may choose the query — never the answer
# --------------------------------------------------------------------------- #


class ScriptedChat:
    """A fake model that answers each call with the next scripted reply."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[list[dict]] = []

    def complete_text(self, messages, temperature=0.2):  # noqa: ANN001
        self.calls.append(messages)
        return self.replies.pop(0) if self.replies else ""

    def close(self) -> None:
        pass


def test_the_model_may_choose_the_query_for_a_question_the_keywords_miss(case_data) -> None:
    fake = ScriptedChat(
        '{"intent": "matches", "status": "partial", "party": null}',
        "One row reconciled only partially: Al-Habib Stationers, PKR 45,900.00 on 2026-06-10 (RI-0004).",
    )
    answer = ask(case_data, "are the payments okay", settings=WITH_MODEL, client=fake)
    assert len(fake.calls) == 2
    assert "You route questions" in fake.calls[0][0]["content"]
    assert "are the payments okay" in fake.calls[0][1]["content"]
    assert answer.intent is AssistantIntent.MATCHES
    assert answer.grounded is True
    # The reader can see the model chose the query, and the answer admits the interpretation.
    assert facts(answer)[ROUTED_BY_LABEL] == "qwen-plus"
    assert answer.answer_confidence is Confidence.MEDIUM
    # The second call phrased the deterministic template, under the number guard.
    assert "You rewrite" in fake.calls[1][0]["content"]
    assert answer.composed_by == "qwen-plus"
    assert "RI-0004" in answer.text


def test_a_party_the_ledger_does_not_name_is_rejected(case_data) -> None:
    fake = ScriptedChat('{"intent": "party", "party": "Acme Corporation"}')
    answer = ask(case_data, "are the payments okay", settings=WITH_MODEL, client=fake)
    assert len(fake.calls) == 1  # no phrasing for a refusal
    assert answer.intent is AssistantIntent.UNKNOWN
    assert answer.grounded is False
    assert "Acme" not in answer.text


def test_a_party_the_ledger_names_is_returned_in_the_ledgers_spelling(case_data) -> None:
    fake = ScriptedChat('{"intent": "party", "party": "karachi packaging"}', "rephrased")
    answer = ask(case_data, "are the payments okay", settings=WITH_MODEL, client=fake)
    assert answer.intent is AssistantIntent.PARTY
    assert "Karachi Packaging Co.: 2 payments totalling PKR 192,800.00." in answer.text or answer.composed_by == "qwen-plus"
    assert facts(answer)["Payments to Karachi Packaging Co."] == "2"


def test_an_amount_not_written_in_the_question_is_rejected(case_data) -> None:
    fake = ScriptedChat('{"intent": "search_amount", "amount": 99999}')
    answer = ask(case_data, "are the payments okay", settings=WITH_MODEL, client=fake)
    assert answer.intent is AssistantIntent.UNKNOWN
    assert answer.grounded is False


def test_an_identifier_must_be_written_in_the_question(case_data) -> None:
    invented = ScriptedChat('{"intent": "item", "reference": "RI-0001"}')
    answer = ask(case_data, "are the payments okay", settings=WITH_MODEL, client=invented)
    assert answer.intent is AssistantIntent.UNKNOWN

    written = ScriptedChat('{"intent": "item", "reference": "V-77"}', "rephrased without numbers")
    answer = ask(case_data, "what about voucher V-77?", settings=WITH_MODEL, client=written)
    assert answer.intent is AssistantIntent.ITEM
    assert answer.grounded is True
    assert facts(answer)["Items found"] == "0"


def test_a_reply_that_is_not_a_query_choice_leaves_the_question_refused(case_data) -> None:
    for reply in ("The payments look fine to me.", '{"intent": "approve_everything"}', '{"intent": "unknown"}', ""):
        fake = ScriptedChat(reply)
        answer = ask(case_data, "are the payments okay", settings=WITH_MODEL, client=fake)
        assert answer.intent is AssistantIntent.UNKNOWN, reply
        assert answer.grounded is False
        assert "fine to me" not in answer.text
        assert len(fake.calls) == 1


def test_a_keyword_placed_question_never_consults_the_classifier(case_data) -> None:
    fake = ScriptedChat("One ledger entry, Shalimar Trading Co for PKR 187,500.00 on 2026-06-18 (RI-0010), matched nothing.")
    answer = ask(case_data, "which items are unmatched?", settings=WITH_MODEL, client=fake)
    assert len(fake.calls) == 1
    assert "You rewrite" in fake.calls[0][0]["content"]
    assert answer.intent is AssistantIntent.UNMATCHED
    assert ROUTED_BY_LABEL not in facts(answer)
    assert answer.answer_confidence is Confidence.HIGH


def test_the_classifier_is_never_used_without_a_model(case_data) -> None:
    answer = ask(case_data, "are the payments okay", settings=NO_MODEL)
    assert answer.intent is AssistantIntent.UNKNOWN
    assert ROUTED_BY_LABEL not in facts(answer)


def test_a_model_date_is_accepted_only_when_its_day_is_written_in_the_question() -> None:
    assert _checked_date("2026-06-11", "what moved on the 11th?", 2026) == (date(2026, 6, 11), "day")
    assert _checked_date("2026-06-12", "what moved on the 11th?", 2026) is None
    assert _checked_date("2026-06", "what moved that month, the 11th?", 2026) == (date(2026, 6, 1), "month")
    # The planner's own parser wins when it finds a date.
    assert _checked_date("2026-01-01", "what was paid on 11 june?", 2026) == (date(2026, 6, 11), "day")
