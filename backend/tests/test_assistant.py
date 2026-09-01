"""Ask Tarazu: grounded answers, computed in code, with sources.

Every test runs the deterministic path — no key, no model — over the sample
case, and asserts the exact figures the answer must carry. The one model test
uses a fake client to prove the number guard: a rephrasing that introduces a
figure is discarded in favour of the template.

The workspace intents — every case in the organization, the documents, what
the model read, the decisions, the reports, the trail — are tested twice:
against a `WorkspaceContext` built by hand, and through the route, which
loads the real one through the same org-scoped repository every route uses.
The route tests include the tenancy check, because "all my cases" is the one
answer that reaches beyond the active case.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.audit import record_action
from app.core.repository import StoredDocument
from app.modules.assistant import service as assistant
from app.modules.assistant.planner import detect_language, plan
from app.modules.assistant.service import (
    CaseOverview,
    WorkspaceContext,
    answer_question,
    numbers_in,
)
from app.modules.assistant.settings import AssistantSettings
from app.shared.schemas import (
    ActorType,
    AssistantIntent,
    AssistantLanguage,
    AuditAction,
    AuditRecord,
    BenfordResult,
    CaseRecord,
    CaseStatus,
    Confidence,
    DocumentType,
    ExtractedField,
    ExtractedRow,
    ExtractionResult,
    FieldDisagreement,
    Provenance,
    ReportRecord,
    ReviewDecision,
    SecondOpinion,
)
from tests.conftest import (
    DEMO_ORG_ID,
    DEMO_USER,
    OTHER_ORG_ID,
    OTHER_USER,
    load_sample_dashboard,
    load_sample_queue,
)

NO_MODEL = AssistantSettings(
    api_key=None, base_url="http://unused", model="none", demo_mode=True,
    phrasing_enabled=True, request_timeout_seconds=1.0,
)

#: The sample ledger's ten amounts, summed: what "total expenses" must say.
SAMPLE_TOTAL = "PKR 2,685,830.00"


@pytest.fixture()
def case_data():
    queue = load_sample_queue()
    dashboard = load_sample_dashboard()
    case = CaseRecord(
        case_id=queue.case_id, client_name="Haroon Textiles", status=CaseStatus.READY_FOR_REVIEW,
        created_by=DEMO_USER.user_id, created_at=datetime.now(timezone.utc),
    )
    return case, queue.items, BenfordResult.model_validate(dashboard["benford"])


def ask(case_data, question: str, language: AssistantLanguage | None = None, context=None):
    case, items, benford = case_data
    return answer_question(
        question, case=case, items=items, benford=benford, context=context,
        language=language, settings=NO_MODEL,
    )


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #


PARTIES = ["Gulberg Traders (Pvt) Ltd", "Karachi Packaging Co.", "Shalimar Trading Co"]


@pytest.mark.parametrize(
    "question,intent",
    [
        ("Which items are unmatched?", AssistantIntent.UNMATCHED),
        ("Explain the structuring flag in plain language", AssistantIntent.RULE),
        ("Why is the Sunday payment flagged?", AssistantIntent.RULE),
        ("Benford analysis summary", AssistantIntent.BENFORD),
        ("Any duplicate payments?", AssistantIntent.DUPLICATES),
        ("What did we pay Gulberg Traders?", AssistantIntent.PARTY),
        ("Total expenses this period", AssistantIntent.TOTALS),
        ("Who are the top vendors?", AssistantIntent.TOP_VENDORS),
        ("Show the largest payments", AssistantIntent.LARGEST),
        ("Compare the months", AssistantIntent.COMPARE_MONTHS),
        ("Any payment of 49,500?", AssistantIntent.SEARCH_AMOUNT),
        ("Which rows are missing evidence?", AssistantIntent.MISSING_EVIDENCE),
        ("What flags were raised?", AssistantIntent.FLAGS),
        ("Give me a summary", AssistantIntent.SUMMARY),
        ("help", AssistantIntent.HELP),
        ("What was our profit?", AssistantIntent.UNSUPPORTED),
        ("What is the weather in Lahore?", AssistantIntent.UNKNOWN),
    ],
)
def test_questions_are_routed_deterministically(question: str, intent: AssistantIntent) -> None:
    assert plan(question, PARTIES).intent is intent
    assert plan(question, PARTIES) == plan(question, PARTIES)


@pytest.mark.parametrize(
    "question,intent",
    [
        ("Show me all my cases", AssistantIntent.CASES),
        ("What documents are in this case?", AssistantIntent.DOCUMENTS),
        ("What did the model read from the statement?", AssistantIntent.EXTRACTIONS),
        ("What have we decided so far?", AssistantIntent.DECISIONS),
        ("Which reports exist?", AssistantIntent.REPORTS),
        ("What happened in this case?", AssistantIntent.HISTORY),
        ("What is reconciliation?", AssistantIntent.CONCEPT),
        ("Explain materiality", AssistantIntent.CONCEPT),
        ("I'm new to auditing, where do I start?", AssistantIntent.HELP),
        ("میرے تمام کیس دکھائیں", AssistantIntent.CASES),
        ("اس کیس میں کیا ہوا؟", AssistantIntent.HISTORY),
        ("مطابقت کیا ہے؟", AssistantIntent.CONCEPT),
    ],
)
def test_workspace_and_glossary_questions_are_routed(
    question: str, intent: AssistantIntent
) -> None:
    assert plan(question, PARTIES).intent is intent
    assert plan(question, PARTIES) == plan(question, PARTIES)


def test_a_definitional_question_about_a_dedicated_topic_stays_a_concept() -> None:
    # "What is a red flag?" explains red flags; "any red flags?" reads the case.
    assert plan("what is a red flag?", PARTIES).intent is AssistantIntent.CONCEPT
    assert plan("any red flags?", PARTIES).intent is AssistantIntent.FLAGS


def test_a_flag_question_stays_about_the_case_not_the_glossary() -> None:
    assert plan("explain the approval limit flag", PARTIES).intent is AssistantIntent.RULE
    assert plan("explain the approval limit flag", PARTIES).rule_id == "near-limit"


def test_a_case_specific_what_is_stays_a_data_question() -> None:
    assert plan("what is the total?", PARTIES).intent is AssistantIntent.TOTALS


def test_a_rule_question_names_its_rule() -> None:
    assert plan("explain structuring", PARTIES).rule_id == "structuring"
    assert plan("why the weekend entry", PARTIES).rule_id == "weekend-entry"
    assert plan("near the approval limit?", PARTIES).rule_id == "near-limit"


def test_a_party_question_names_the_party() -> None:
    assert plan("tell me about Karachi Packaging", PARTIES).party == "Karachi Packaging Co."


def test_an_amount_question_parses_the_amount() -> None:
    assert plan("who was paid 1,500,000", PARTIES).amount == Decimal("1500000")


def test_language_is_detected_from_script_or_request() -> None:
    assert detect_language("اردو میں خلاصہ دیں") is AssistantLanguage.URDU
    assert detect_language("summary in urdu please") is AssistantLanguage.URDU
    assert detect_language("summary") is AssistantLanguage.ENGLISH
    assert detect_language("summary", AssistantLanguage.URDU) is AssistantLanguage.URDU


# --------------------------------------------------------------------------- #
# Answers, computed from the case
# --------------------------------------------------------------------------- #


def test_unmatched_items_are_listed_with_their_figures(case_data) -> None:
    answer = ask(case_data, "Which items are unmatched?")
    assert answer.grounded is True
    assert answer.intent is AssistantIntent.UNMATCHED
    assert "1 ledger entry matched nothing" in answer.text
    assert "Shalimar Trading Co, PKR 187,500.00 on 2026-06-18 (RI-0010)" in answer.text
    assert answer.answer_confidence is Confidence.HIGH
    assert {c.document_id for c in answer.citations} == {"DOC-LED-001"}
    assert answer.citations[0].review_item_id == "RI-0010"
    assert ("Unmatched items", "1") in [(f.label, f.value) for f in answer.facts]


def test_the_structuring_flag_is_explained_from_its_rows(case_data) -> None:
    answer = ask(case_data, "Explain the structuring flag")
    assert answer.intent is AssistantIntent.RULE
    assert answer.text.startswith("Structuring means splitting one payment")
    assert "Hussain Brothers & Sons, PKR 49,500.00 on 2026-06-11 (RI-0005)" in answer.text
    assert "RI-0006" in answer.text
    assert "The decision on each item is yours" in answer.text
    assert any(c.row_number == 16 for c in answer.citations)


def test_a_party_question_totals_that_partys_rows(case_data) -> None:
    answer = ask(case_data, "What did we pay Karachi Packaging?")
    assert answer.intent is AssistantIntent.PARTY
    assert answer.text.startswith("Karachi Packaging Co.: 2 payments totalling PKR 192,800.00.")
    assert "RI-0002" in answer.text and "RI-0008" in answer.text
    assert "duplicate-invoice" in answer.text
    assert any(c.document_id == "DOC-INV-0087" for c in answer.citations)


def test_totals_are_summed_in_code(case_data) -> None:
    answer = ask(case_data, "What are the total expenses?")
    _case, items, _benford = case_data
    expected = sum((item.ledger_entry.amount for item in items), Decimal(0))
    assert f"PKR {expected:,.2f}" == SAMPLE_TOTAL
    assert f"The 10 ledger rows total {SAMPLE_TOTAL}" in answer.text
    assert "unmatched rows PKR 187,500.00" in answer.text
    assert "the ledger carries no income or profit figures" in answer.text


def test_top_vendors_are_ranked_by_amount(case_data) -> None:
    answer = ask(case_data, "top vendors")
    lines = [line for line in answer.text.splitlines() if line.startswith("•")]
    assert lines[0].startswith("• Indus Power Solutions: PKR 1,500,000.00 over 1 payment")
    assert lines[1].startswith("• Sialkot Metal Works: PKR 312,880.00")
    assert "55.8% of the total" in lines[0]


def test_the_largest_payments_are_listed_in_order(case_data) -> None:
    answer = ask(case_data, "largest payments")
    lines = [line for line in answer.text.splitlines() if line.startswith("•")]
    assert len(lines) == 5
    assert lines[0].startswith("• PKR 1,500,000.00 to Indus Power Solutions")
    assert lines[-1].startswith("• PKR 96,400.00 to Karachi Packaging Co.")


def test_a_single_month_says_there_is_nothing_to_compare(case_data) -> None:
    answer = ask(case_data, "compare the months")
    assert "covers only one month (2026-06)" in answer.text
    assert f"{SAMPLE_TOTAL} over 10 rows, 1 unmatched, 5 flagged" in answer.text
    assert answer.answer_confidence is Confidence.MEDIUM


def test_searching_an_amount_finds_ledger_rows_and_bank_lines(case_data) -> None:
    answer = ask(case_data, "any payment of 49,500?")
    assert "Exactly PKR 49,500.00 (2)" in answer.text
    assert "RI-0005" in answer.text and "RI-0006" in answer.text
    # 45,900 in the ledger was 49,500 at the bank: the transposition shows up here.
    assert "The bank statement shows that amount on these rows (1)" in answer.text
    assert "RI-0004" in answer.text


def test_missing_evidence_names_each_gap(case_data) -> None:
    answer = ask(case_data, "which rows are missing evidence?")
    assert "1 rows are short of evidence" in answer.text
    assert "(RI-0010): no bank payment and no invoice" in answer.text


def test_duplicates_come_from_the_rules_output(case_data) -> None:
    answer = ask(case_data, "any duplicate payments?")
    assert "2 flags" in answer.text
    assert "Invoice INV-2026-0087 is paid twice" in answer.text


def test_benford_is_read_from_the_stored_result(case_data) -> None:
    answer = ask(case_data, "benford summary")
    assert "Chi-square is 12.21 on 8 degrees of freedom: no significant deviation" in answer.text
    assert "The digit furthest from expectation is 4" in answer.text
    assert answer.answer_confidence is Confidence.MEDIUM
    assert answer.citations == []


def test_the_summary_counts_the_queue(case_data) -> None:
    answer = ask(case_data, "give me a summary")
    assert answer.text.startswith(
        "10 ledger rows: 8 matched, 1 partial, 1 unmatched. Decisions: 1 approved, 1 rejected, 8 pending."
    )
    assert "8 flags on 5 items: 6 high, 1 medium, 1 low severity." in answer.text


# --------------------------------------------------------------------------- #
# The rest of the engagement's record — every case, the documents, what the
# model read, the reports, the trail — and the glossary for a first-time auditor
# --------------------------------------------------------------------------- #


EXTRACTED_AT = datetime(2026, 6, 19, 8, 30, tzinfo=timezone.utc)
REPORT_AT = datetime(2026, 6, 19, 11, 0, tzinfo=timezone.utc)


def a_document(
    document_id: str, document_type: DocumentType, filename: str, size_bytes: int
) -> StoredDocument:
    return StoredDocument(
        document_id=document_id, document_type=document_type, filename=filename,
        size_bytes=size_bytes, storage_path=f"documents/{document_id}/{filename}",
    )


def _reading(
    document_id: str, field: str, value, confidence: Confidence, *, page: int
) -> ExtractedField:
    return ExtractedField(
        field=field, value=value, extraction_confidence=confidence,
        source=Provenance(document_id=document_id, page=page, text_snippet=f"{field} as printed"),
    )


def a_bank_extraction() -> ExtractionResult:
    """A statement mostly read with high confidence, with one unreadable
    account number, one medium-confidence row, and a second pass that
    disagrees — the readings a checker wants shown first."""
    return ExtractionResult(
        document_id="DOC-BNK-001", document_type=DocumentType.BANK_STATEMENT,
        filename="haroon-bank-june.pdf", page_count=3, extracted_at=EXTRACTED_AT,
        model="qwen-vl-max",
        fields=[
            _reading("DOC-BNK-001", "account_holder", "Haroon Textiles", Confidence.HIGH, page=1),
            ExtractedField(
                field="account_number", value=None, extraction_confidence=Confidence.LOW,
                unreadable=True,
                source=Provenance(document_id="DOC-BNK-001", page=1, text_snippet="account number line"),
            ),
        ],
        rows=[
            ExtractedRow(row_id="BNK-R1", page=1, fields=[
                _reading("DOC-BNK-001", "date", "02/06/2026", Confidence.HIGH, page=1),
                _reading("DOC-BNK-001", "amount", "284,000.00", Confidence.HIGH, page=1),
                _reading("DOC-BNK-001", "description", "YARN PURCHASE JUNE LOT 1", Confidence.HIGH, page=1),
            ]),
            ExtractedRow(row_id="BNK-R2", page=2, fields=[
                _reading("DOC-BNK-001", "date", "10/06/2026", Confidence.MEDIUM, page=2),
                _reading("DOC-BNK-001", "amount", "49,500.00", Confidence.MEDIUM, page=2),
            ]),
        ],
        second_opinion=SecondOpinion(
            ran=True, model="qwen-vl-max", agrees=False,
            disagreements=[FieldDisagreement(field="amount", first_reading="49,500.00", second_reading="49.500,00")],
        ),
        needs_human_review=True,
    )


def an_invoice_extraction() -> ExtractionResult:
    return ExtractionResult(
        document_id="DOC-INV-0087", document_type=DocumentType.INVOICE,
        filename="invoice-INV-2026-0087.pdf", page_count=1, extracted_at=EXTRACTED_AT,
        model="qwen-vl-max",
        fields=[
            _reading("DOC-INV-0087", "invoice_number", "INV-2026-0087", Confidence.HIGH, page=1),
            _reading("DOC-INV-0087", "total", "49,500.00", Confidence.HIGH, page=1),
            _reading("DOC-INV-0087", "party_name", "Al-Habib Stationers", Confidence.HIGH, page=1),
        ],
        second_opinion=SecondOpinion(ran=True, model="qwen-vl-max", agrees=True),
    )


def the_documents() -> list[StoredDocument]:
    """Three uploads: two the pipeline read, and the ledger not extracted yet."""
    return [
        a_document("DOC-BNK-001", DocumentType.BANK_STATEMENT, "haroon-bank-june.pdf", 1_500_000),
        a_document("DOC-INV-0087", DocumentType.INVOICE, "invoice-INV-2026-0087.pdf", 96_400),
        a_document("DOC-LED-001", DocumentType.LEDGER, "haroon-ledger-june.xlsx", 45_632),
    ]


def a_report_record(case_id: str) -> ReportRecord:
    return ReportRecord(
        report_id="RPT-20260619-01", case_id=case_id, generated_by=DEMO_USER.user_id,
        generated_at=REPORT_AT, pdf_path="reports/RPT-20260619-01.pdf",
        excel_path="reports/RPT-20260619-01.xlsx", pdf_sha256="a" * 64, excel_sha256="b" * 64,
        item_count=10, approved_count=1, rejected_count=1, pending_count=8,
        flag_count=8, audit_record_count=5,
    )


@pytest.fixture()
def workspace(case_data):
    """The engagement's wider record, built by hand: two engagements, three
    documents, two extractions, one report, five trail events. The active
    case's counts are computed from the same queue the answers run over."""
    case, items, _benford = case_data
    other_case = CaseRecord(
        case_id="CASE-2026-05-RMD", client_name="Rahim Dairies",
        status=CaseStatus.READY_FOR_REVIEW, created_by=DEMO_USER.user_id,
        created_at=datetime(2026, 5, 30, 9, 0, tzinfo=timezone.utc),
    )

    def trail(
        audit_id: str, action: AuditAction, at: datetime, *, actor_id: str = DEMO_USER.user_id,
        item_id: str | None = None, detail: str | None = None,
    ) -> AuditRecord:
        return AuditRecord(
            audit_id=audit_id, case_id=case.case_id, actor_type=ActorType.HUMAN,
            actor_id=actor_id, action=action, item_id=item_id, detail=detail, occurred_at=at,
        )

    return WorkspaceContext(
        documents=the_documents(),
        extractions=[a_bank_extraction(), an_invoice_extraction()],
        reports=[a_report_record(case.case_id)],
        trail=[
            trail("AUD-01", AuditAction.CASE_CREATED, datetime(2026, 6, 19, 8, 0, tzinfo=timezone.utc),
                  detail="Haroon Textiles, period 2026-06-02 to 2026-06-18"),
            trail("AUD-02", AuditAction.DOCUMENT_UPLOADED, datetime(2026, 6, 19, 8, 5, tzinfo=timezone.utc),
                  detail="haroon-bank-june.pdf"),
            trail("AUD-03", AuditAction.ITEM_APPROVED, datetime(2026, 6, 19, 9, 41, tzinfo=timezone.utc),
                  actor_id="user-demo-auditor", item_id="RI-0001"),
            trail("AUD-04", AuditAction.ITEM_REJECTED, datetime(2026, 6, 19, 10, 2, tzinfo=timezone.utc),
                  actor_id="user-demo-auditor", item_id="RI-0004", detail="Ledger amount is wrong"),
            trail("AUD-05", AuditAction.REPORT_GENERATED, REPORT_AT, item_id="RPT-20260619-01"),
        ],
        cases=[
            CaseOverview(
                case=case, total_items=len(items),
                pending=sum(1 for item in items if item.decision is ReviewDecision.PENDING),
                approved=sum(1 for item in items if item.decision is ReviewDecision.APPROVED),
                rejected=sum(1 for item in items if item.decision is ReviewDecision.REJECTED),
                flags=sum(len(item.flags) for item in items),
            ),
            CaseOverview(case=other_case, total_items=6, pending=6, approved=0, rejected=0, flags=2),
        ],
        active_case_id=case.case_id,
    )


def test_every_engagement_of_the_organization_is_listed(case_data, workspace) -> None:
    answer = ask(case_data, "Show me all my cases", context=workspace)
    assert answer.intent is AssistantIntent.CASES
    assert answer.grounded is True
    assert "Your organization holds 2 engagements:" in answer.text
    assert (
        "Haroon Textiles (CASE-2026-06-STX) (active case): 10 items, 8 pending, 8 flags; ready_for_review"
        in answer.text
    )
    assert "Rahim Dairies (CASE-2026-05-RMD): 6 items, 6 pending, 2 flags; ready_for_review, created 2026-05-30" in answer.text
    assert "Switch cases from the header" in answer.text
    assert ("Engagements in this organization", "2") in [(f.label, f.value) for f in answer.facts]


def test_the_documents_answer_names_each_file_and_its_reading(case_data, workspace) -> None:
    answer = ask(case_data, "What documents are in this case?", context=workspace)
    assert answer.intent is AssistantIntent.DOCUMENTS
    assert "This case holds 3 documents, 2 of them read by the extraction pipeline:" in answer.text
    assert (
        "• haroon-bank-june.pdf: bank_statement, 1.5 MB; read by qwen-vl-max over 3 page(s), "
        "7 values; the two passes disagreed, needs human review" in answer.text
    )
    assert "• invoice-INV-2026-0087.pdf: invoice, 96 KB; read by qwen-vl-max over 1 page(s), 3 values" in answer.text
    assert "• haroon-ledger-june.xlsx: ledger, 46 KB; not extracted yet" in answer.text
    assert ("haroon-ledger-june.xlsx", "ledger, 46 KB, not extracted yet") in [
        (f.label, f.value) for f in answer.facts
    ]


def test_what_the_model_read_counts_confidences_and_admits_the_unreadable(case_data, workspace) -> None:
    answer = ask(case_data, "What did the model read from the statement?", context=workspace)
    assert answer.intent is AssistantIntent.EXTRACTIONS
    assert (
        "• haroon-bank-june.pdf (bank_statement): 7 values over 3 page(s): "
        "4 high, 2 medium, 0 low confidence, 1 unreadable (read by qwen-vl-max)" in answer.text
    )
    # The readings worth a second look come first; the unreadable one is
    # admitted as unreadable, never guessed.
    assert "  – account_number: unreadable (low)" in answer.text
    assert "  – amount: 49,500.00 (medium)" in answer.text
    assert "  – the second pass disagrees; needs human review" in answer.text
    assert "never guessed" in answer.text
    assert (
        "haroon-bank-june.pdf",
        "7 values over 3 page(s): 4 high, 2 medium, 0 low confidence, 1 unreadable; read by qwen-vl-max",
    ) in [(f.label, f.value) for f in answer.facts]
    # The citations point at the pages the readings came from, not at items;
    # two readings off the same page share one cited region.
    assert len(answer.citations) == 2
    assert {c.document_id for c in answer.citations} == {"DOC-BNK-001"}
    assert {c.page for c in answer.citations} == {1, 2}
    assert all(c.review_item_id is None for c in answer.citations)


def test_the_decisions_taken_so_far_are_listed_with_their_deciders(case_data) -> None:
    answer = ask(case_data, "What have we decided so far?")  # reads the queue; needs no workspace
    assert answer.intent is AssistantIntent.DECISIONS
    assert "So far 1 item approved and 1 rejected, out of 10; 8 still pending:" in answer.text
    assert "• RI-0001: Gulberg Traders (Pvt) Ltd, PKR 284,000.00; approved by user-demo-auditor at 2026-06-19 09:41" in answer.text
    assert (
        "• RI-0004: Al-Habib Stationers, PKR 45,900.00; rejected by user-demo-auditor "
        "at 2026-06-19 10:02. Reason: Ledger amount is wrong" in answer.text
    )
    assert "the assistant never approves or rejects anything" in answer.text
    assert {c.review_item_id for c in answer.citations} == {"RI-0001", "RI-0004"}


def test_existing_reports_are_listed_with_the_counts_they_froze(case_data, workspace) -> None:
    answer = ask(case_data, "Which reports exist?", context=workspace)
    assert answer.intent is AssistantIntent.REPORTS
    assert "1 report exists for this case:" in answer.text
    assert (
        f"• RPT-20260619-01, generated 2026-06-19 11:00 by {DEMO_USER.user_id}: "
        "10 items (1 approved, 1 rejected, 8 pending), 8 flags, 5 trail records" in answer.text
    )
    assert "Reports are append-only evidence" in answer.text
    assert ("Reports generated for this case", "1") in [(f.label, f.value) for f in answer.facts]


def test_the_history_answer_reads_the_trail_backwards(case_data, workspace) -> None:
    answer = ask(case_data, "What happened in this case?", context=workspace)
    assert answer.intent is AssistantIntent.HISTORY
    assert "The trail records 5 events for this case. Most recent:" in answer.text
    assert f"• 2026-06-19 11:00, report_generated by {DEMO_USER.user_id}" in answer.text
    assert "item_rejected by user-demo-auditor: Ledger amount is wrong" in answer.text
    assert "The trail is append-only: no entry can be edited or removed" in answer.text
    assert ("Events in this case's trail", "5") in [(f.label, f.value) for f in answer.facts]


def test_a_concept_question_is_answered_from_the_glossary_not_the_case(case_data) -> None:
    answer = ask(case_data, "What is reconciliation?")
    assert answer.intent is AssistantIntent.CONCEPT
    assert answer.grounded is True
    assert answer.text.startswith(
        "Reconciliation is checking that two independent records of the same money agree"
    )
    assert "That is from Tarazu's built-in glossary, written and reviewed in code, not generated" in answer.text
    # It claims nothing about the case, so it cites nothing.
    assert answer.citations == []
    assert ("Answered from", "Tarazu's built-in glossary, shipped in code") in [
        (f.label, f.value) for f in answer.facts
    ]


def test_a_concept_question_in_urdu_is_answered_in_urdu(case_data) -> None:
    answer = ask(case_data, "مطابقت کیا ہے؟")
    assert answer.language is AssistantLanguage.URDU
    assert answer.intent is AssistantIntent.CONCEPT
    assert answer.text.startswith("مطابقت (ریکنسلئیشن) کا مطلب")
    assert "کوڈ میں لکھی اور جانچی گئی، مشین سے تخلیق نہیں" in answer.text


def test_a_beginner_is_shown_help_with_the_glossary_in_it(case_data) -> None:
    answer = ask(case_data, "I'm new to auditing, where do I start?")
    assert answer.intent is AssistantIntent.HELP
    assert answer.grounded is True
    assert "plain-language glossary" in answer.text


@pytest.mark.parametrize(
    "question,intent",
    [
        ("Show me all my cases", AssistantIntent.CASES),
        ("What documents are in this case?", AssistantIntent.DOCUMENTS),
        ("What did the model read from the statement?", AssistantIntent.EXTRACTIONS),
        ("Which reports exist?", AssistantIntent.REPORTS),
        ("What happened in this case?", AssistantIntent.HISTORY),
    ],
)
def test_a_workspace_question_with_no_workspace_loaded_is_refused(
    case_data, question: str, intent: AssistantIntent
) -> None:
    """No context loaded, no answer: refused, never guessed — the same refusal
    an out-of-scope question gets."""
    answer = ask(case_data, question)
    assert answer.intent is intent
    assert answer.grounded is False
    assert answer.answer_confidence is Confidence.LOW
    assert answer.citations == []
    assert answer.text.startswith("I can't answer that from this case's uploaded documents")


def test_an_urdu_workspace_question_is_answered_in_urdu(case_data, workspace) -> None:
    answer = ask(case_data, "میرے تمام کیس دکھائیں", context=workspace)
    assert answer.language is AssistantLanguage.URDU
    assert answer.intent is AssistantIntent.CASES
    assert "آپ کی تنظیم میں 2 کیس ہیں" in answer.text
    assert "(فعلی کیس)" in answer.text
    assert "Haroon Textiles" in answer.text
    assert "10 آئٹم" in answer.text


# --------------------------------------------------------------------------- #
# Refusals: rule 7 made visible
# --------------------------------------------------------------------------- #


def test_a_question_outside_the_documents_is_refused_not_guessed(case_data) -> None:
    answer = ask(case_data, "What is the weather in Lahore today?")
    assert answer.grounded is False
    assert answer.intent is AssistantIntent.UNKNOWN
    assert answer.answer_confidence is Confidence.LOW
    assert answer.citations == []
    assert answer.text.startswith("I can't answer that from this case's uploaded documents")


def test_a_figure_the_ledger_cannot_carry_is_declined_with_the_reason(case_data) -> None:
    answer = ask(case_data, "What was our profit in June?")
    assert answer.grounded is False
    assert answer.intent is AssistantIntent.UNSUPPORTED
    assert "does not carry sales, revenue, income, or profit figures" in answer.text


def test_every_answer_carries_a_confidence_and_a_composer(case_data) -> None:
    for question in ("summary", "unmatched", "weather", "profit", "help"):
        answer = ask(case_data, question)
        assert answer.answer_confidence in set(Confidence)
        assert answer.composed_by == assistant.DETERMINISTIC_COMPOSER


# --------------------------------------------------------------------------- #
# Urdu
# --------------------------------------------------------------------------- #


def test_an_urdu_question_is_answered_in_urdu_with_the_same_figures(case_data) -> None:
    answer = ask(case_data, "اردو میں خلاصہ دیں")
    assert answer.language is AssistantLanguage.URDU
    assert answer.intent is AssistantIntent.SUMMARY
    assert "10 لیجر قطاریں" in answer.text
    assert "8 مماثل" in answer.text and "1 غیر مماثل" in answer.text
    assert SAMPLE_TOTAL in answer.text


def test_urdu_can_be_requested_for_an_english_question(case_data) -> None:
    answer = ask(case_data, "which items are unmatched?", AssistantLanguage.URDU)
    assert answer.language is AssistantLanguage.URDU
    assert "Shalimar Trading Co" in answer.text and "PKR 187,500.00" in answer.text
    assert "فرضی وینڈر" in answer.text


def test_urdu_refusals_are_in_urdu(case_data) -> None:
    answer = ask(case_data, "آج لاہور کا موسم کیسا ہے؟")
    assert answer.grounded is False
    assert answer.text.startswith("میں اس سوال کا جواب")


# --------------------------------------------------------------------------- #
# The model may phrase, never compute
# --------------------------------------------------------------------------- #


class FakeChat:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    def complete_text(self, messages, temperature=0.2):  # noqa: ANN001
        self.calls += 1
        self.messages = messages
        return self.reply

    def close(self) -> None:
        pass


WITH_MODEL = AssistantSettings(
    api_key="test-key", base_url="http://unused", model="qwen-plus", demo_mode=False,
    phrasing_enabled=True, request_timeout_seconds=1.0,
)


def test_a_faithful_rephrasing_is_used_and_attributed(case_data) -> None:
    case, items, benford = case_data
    fake = FakeChat(
        "One ledger entry, Shalimar Trading Co for PKR 187,500.00 on 2026-06-18 (RI-0010), "
        "matched nothing in the bank statement or the invoices - the fictitious-vendor pattern."
    )
    answer = answer_question(
        "unmatched?", case=case, items=items, benford=benford, settings=WITH_MODEL, client=fake
    )
    assert fake.calls == 1
    assert answer.text == fake.reply
    assert answer.composed_by == "qwen-plus"
    # The model saw facts and a template, never a document.
    prompt = fake.messages[1]["content"]
    assert "Facts:" in prompt and "Shalimar Trading Co" in prompt
    assert "Do not compute" in fake.messages[0]["content"]


def test_a_rephrasing_that_invents_a_number_is_discarded(case_data) -> None:
    case, items, benford = case_data
    fake = FakeChat("There are 3 unmatched entries totalling PKR 500,000.00, all suspicious.")
    answer = answer_question(
        "unmatched?", case=case, items=items, benford=benford, settings=WITH_MODEL, client=fake
    )
    assert fake.calls == 1
    assert answer.composed_by == assistant.DETERMINISTIC_COMPOSER
    assert "1 ledger entry matched nothing" in answer.text


def test_refusals_never_reach_the_model(case_data) -> None:
    """A question the keywords cannot place is shown to the model once — to
    choose a query, never to answer. A reply that is not a query choice
    leaves the question refused, and the phrasing step never runs on a
    refusal, so nothing the model said can reach the answer."""
    case, items, benford = case_data
    fake = FakeChat("Lahore is sunny.")
    answer = answer_question(
        "weather in Lahore?", case=case, items=items, benford=benford,
        settings=WITH_MODEL, client=fake,
    )
    assert fake.calls == 1
    assert "You route questions" in fake.messages[0]["content"]
    assert answer.grounded is False
    assert answer.intent is AssistantIntent.UNKNOWN
    assert "sunny" not in answer.text
    assert answer.composed_by == assistant.DETERMINISTIC_COMPOSER


def test_demo_mode_never_reaches_the_model(case_data) -> None:
    case, items, benford = case_data
    fake = FakeChat("anything")
    demo = AssistantSettings(
        api_key="test-key", base_url="http://unused", model="qwen-plus", demo_mode=True,
        phrasing_enabled=True, request_timeout_seconds=1.0,
    )
    answer_question("summary", case=case, items=items, benford=benford, settings=demo, client=fake)
    assert fake.calls == 0


def test_numbers_are_normalised_for_the_guard() -> None:
    assert numbers_in("PKR 187,500.00 on 2026-06-18 (RI-0010)") == {"187500", "2026", "6", "18", "10"}
    assert numbers_in("12.21 on 8") == {"12.21", "8"}


# --------------------------------------------------------------------------- #
# The route
# --------------------------------------------------------------------------- #


def test_the_route_answers_and_records_both_sides_of_the_exchange(
    client: TestClient, repository, seeded_case: str
) -> None:
    before = len(repository.list_audit(DEMO_ORG_ID, seeded_case))
    response = client.post("/v1/assistant/chat", json={"question": "Which items are unmatched?"})
    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == seeded_case
    assert body["answer"]["grounded"] is True
    assert body["answer"]["answer_confidence"] == "high"
    assert "confidence" not in body["answer"]
    assert body["answer"]["citations"][0]["document_id"] == "DOC-LED-001"
    assert body["audit_record"]["action"] == "assistant_answered"

    trail = repository.list_audit(DEMO_ORG_ID, seeded_case)
    assert len(trail) == before + 2
    assert trail[-2].action is AuditAction.ASSISTANT_QUESTION_ASKED
    assert trail[-2].actor_id == DEMO_USER.user_id
    assert trail[-2].detail == "Which items are unmatched?"
    assert trail[-1].action is AuditAction.ASSISTANT_ANSWERED
    assert trail[-1].actor_id == assistant.DETERMINISTIC_COMPOSER
    assert trail[-1].detail.startswith("unmatched, grounded, high confidence, 1 citation(s):")


def test_the_route_scopes_the_case_like_everything_else(
    other_client: TestClient, seeded_case: str
) -> None:
    response = other_client.post(
        "/v1/assistant/chat", json={"question": "summary", "case_id": seeded_case}
    )
    assert response.status_code == 404


def test_a_blank_question_is_refused_by_the_contract(client: TestClient, seeded_case: str) -> None:
    assert client.post("/v1/assistant/chat", json={"question": "   "}).status_code == 422


def test_the_language_can_be_forced_through_the_api(client: TestClient, seeded_case: str) -> None:
    body = client.post(
        "/v1/assistant/chat", json={"question": "summary", "language": "ur"}
    ).json()
    assert body["answer"]["language"] == "ur"
    assert "لیجر" in body["answer"]["text"]


def seed_engagement(repository, case_id: str) -> None:
    """Persist the engagement's wider record the way the pipeline does, so the
    route loads a real workspace for its questions."""
    repository.add_documents(DEMO_ORG_ID, case_id, the_documents(), DEMO_USER.user_id)
    repository.save_extraction(DEMO_ORG_ID, case_id, a_bank_extraction())
    repository.save_extraction(DEMO_ORG_ID, case_id, an_invoice_extraction())
    repository.save_report(DEMO_ORG_ID, a_report_record(case_id))
    for action, actor_id, item_id, detail in (
        (AuditAction.CASE_CREATED, DEMO_USER.user_id, None, "Haroon Textiles, period 2026-06-02 to 2026-06-18"),
        (AuditAction.DOCUMENT_UPLOADED, DEMO_USER.user_id, None, "haroon-bank-june.pdf"),
        (AuditAction.ITEM_APPROVED, "user-demo-auditor", "RI-0001", None),
        (AuditAction.ITEM_REJECTED, "user-demo-auditor", "RI-0004", "Ledger amount is wrong"),
        (AuditAction.REPORT_GENERATED, DEMO_USER.user_id, "RPT-20260619-01", None),
    ):
        record_action(
            repository, DEMO_ORG_ID, case_id, ActorType.HUMAN, actor_id, action,
            item_id=item_id, detail=detail,
        )


def test_the_route_answers_workspace_questions_from_the_persisted_record(
    client: TestClient, repository, seeded_case: str
) -> None:
    seed_engagement(repository, seeded_case)
    answer = client.post(
        "/v1/assistant/chat", json={"question": "What documents are in this case?"}
    ).json()["answer"]
    assert answer["intent"] == "documents"
    assert answer["grounded"] is True
    assert "This case holds 3 documents, 2 of them read by the extraction pipeline:" in answer["text"]
    assert "haroon-bank-june.pdf" in answer["text"]
    assert "not extracted yet" in answer["text"]


def test_the_route_cites_the_pages_the_model_read(
    client: TestClient, repository, seeded_case: str
) -> None:
    seed_engagement(repository, seeded_case)
    answer = client.post(
        "/v1/assistant/chat", json={"question": "What did the model read from the statement?"}
    ).json()["answer"]
    assert answer["intent"] == "extractions"
    assert "1 unreadable" in answer["text"]
    citations = answer["citations"]
    assert len(citations) == 2
    assert {c["document_id"] for c in citations} == {"DOC-BNK-001"}
    assert {c["page"] for c in citations} == {1, 2}
    assert all(c["review_item_id"] is None for c in citations)


def test_all_my_cases_stays_inside_the_organization(
    client: TestClient, other_client: TestClient, repository, seeded_case: str
) -> None:
    repository.create_case(DEMO_ORG_ID, CaseRecord(
        case_id="CASE-2026-05-RMD", client_name="Rahim Dairies",
        status=CaseStatus.READY_FOR_REVIEW, created_by=DEMO_USER.user_id,
        created_at=datetime(2026, 5, 30, 9, 0, tzinfo=timezone.utc),
    ))
    repository.create_case(OTHER_ORG_ID, CaseRecord(
        case_id="CASE-B-0001", client_name="Bright Steel Mills",
        status=CaseStatus.READY_FOR_REVIEW, created_by=OTHER_USER.user_id,
        created_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
    ))

    ours = client.post("/v1/assistant/chat", json={"question": "Show me all my cases"}).json()["answer"]
    assert ours["intent"] == "cases"
    assert "Haroon Textiles" in ours["text"] and "Rahim Dairies" in ours["text"]
    assert "Bright Steel Mills" not in ours["text"]

    theirs = other_client.post(
        "/v1/assistant/chat", json={"question": "Show me all my cases"}
    ).json()["answer"]
    assert "Bright Steel Mills" in theirs["text"]
    assert "Haroon Textiles" not in theirs["text"]
    assert "Rahim Dairies" not in theirs["text"]


def test_the_history_answer_stops_before_the_question_being_asked(
    client: TestClient, repository, seeded_case: str
) -> None:
    seed_engagement(repository, seeded_case)
    answer = client.post(
        "/v1/assistant/chat", json={"question": "What happened in this case?"}
    ).json()["answer"]
    assert answer["intent"] == "history"
    assert "The trail records 5 events for this case." in answer["text"]
    assert "case_created" in answer["text"] and "report_generated" in answer["text"]
    # The trail is loaded before the question is recorded, so the question is
    # never part of its own answer.
    assert "assistant_question_asked" not in answer["text"]
    # The exchange itself lands on the trail afterwards, like everything else.
    assert len(repository.list_audit(DEMO_ORG_ID, seeded_case)) == 7
