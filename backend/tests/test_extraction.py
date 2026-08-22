"""Extraction tests. Every Qwen call is mocked; no test touches the network.

The mocks are `httpx.MockTransport` handlers, so the real request-building,
retry, and parsing code runs — only the socket is replaced.
"""

from __future__ import annotations

import io
import json
from datetime import date
from decimal import Decimal

import httpx
import pandas as pd
import pymupdf
import pytest

from app.modules.extraction import demo_mode, service
from app.modules.extraction.ledger_reader import LedgerReadError, read_ledger
from app.modules.extraction.page_images import PageImage, pdf_to_page_images
from app.modules.extraction.qwen_client import (
    QwenResponseError,
    QwenTransportError,
    QwenVisionClient,
)
from app.modules.extraction.settings import ExtractionSettings
from app.shared.schemas import Confidence, DocumentType, ExtractedField, Provenance


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def make_settings(**overrides) -> ExtractionSettings:
    base = dict(
        api_key="test-key",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        vl_model="qwen-vl-max",
        second_opinion_model="qwen-vl-max",
        verify_at_or_below="low",
        demo_mode=False,
        page_image_dpi=100,
        request_timeout_seconds=5.0,
        max_attempts=3,
        backoff_base_seconds=0.0,
    )
    base.update(overrides)
    return ExtractionSettings(**base)


def qwen_reply(content: str) -> httpx.Response:
    """An OpenAI-compatible chat-completion response carrying `content`."""
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "model": "qwen-vl-max",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        },
    )


def client_returning(*bodies: str, sleeps: list[float] | None = None) -> QwenVisionClient:
    """A client whose successive calls return `bodies`, cycling on the last one."""
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        index = min(calls["n"], len(bodies) - 1)
        calls["n"] += 1
        return qwen_reply(bodies[index])

    return QwenVisionClient(
        settings=make_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=(sleeps.append if sleeps is not None else lambda _seconds: None),
    )


EXTRACTION_BODY = json.dumps(
    {
        "fields": [
            {
                "field": "invoice_number",
                "value": "SMW/2026/0431",
                "extraction_confidence": "high",
                "bbox": [0.118, 0.164, 0.412, 0.198],
                "text_snippet": "Invoice # SMW/2026/0431",
                "unreadable": False,
            },
            {
                "field": "party_name",
                "value": "Sialkot Metal Works",
                "extraction_confidence": "high",
                "bbox": [0.101, 0.072, 0.487, 0.121],
                "text_snippet": "SIALKOT METAL WORKS",
                "unreadable": False,
            },
            {
                "field": "date",
                "value": "2026-06-15",
                "extraction_confidence": "medium",
                "bbox": [0.631, 0.164, 0.869, 0.196],
                "text_snippet": "Date: 15-06-2026",
                "unreadable": False,
            },
            {
                "field": "amount",
                "value": "Rs. 312,880/-",
                "extraction_confidence": "low",
                "bbox": [0.548, 0.681, 0.833, 0.724],
                "text_snippet": "Rs. 312,880/-",
                "unreadable": False,
            },
        ]
    }
)

AGREE_BODY = json.dumps({"checks": [{"field": "amount", "agrees": True, "reading": 312880}]})
DISAGREE_BODY = json.dumps(
    {"checks": [{"field": "amount", "agrees": False, "reading": "312,860"}]}
)


@pytest.fixture()
def page() -> PageImage:
    return PageImage(page=1, content=b"\x89PNG\r\n\x1a\nstub", mime_type="image/png",
                     width=1000, height=1400)


@pytest.fixture()
def one_page_pdf() -> bytes:
    document = pymupdf.open()
    sheet = document.new_page(width=595, height=842)
    sheet.insert_text((72, 120), "INVOICE SMW/2026/0431", fontsize=18)
    data = document.tobytes()
    document.close()
    return data


# --------------------------------------------------------------------------- #
# 1. PDF to page images
# --------------------------------------------------------------------------- #


def test_pdf_renders_one_image_per_page() -> None:
    document = pymupdf.open()
    for _ in range(3):
        document.new_page(width=595, height=842)
    data = document.tobytes()
    document.close()

    pages = pdf_to_page_images(data, dpi=72)

    assert [image.page for image in pages] == [1, 2, 3]
    assert all(image.content.startswith(b"\x89PNG") for image in pages)
    assert all(image.mime_type == "image/png" for image in pages)
    # 595pt at 72dpi is 595px, give or take MuPDF's rounding.
    assert 590 <= pages[0].width <= 600


def test_render_dpi_controls_image_size(one_page_pdf: bytes) -> None:
    low = pdf_to_page_images(one_page_pdf, dpi=72)[0]
    high = pdf_to_page_images(one_page_pdf, dpi=144)[0]
    assert high.width > low.width * 1.8


def test_page_image_becomes_a_data_url(page: PageImage) -> None:
    url = page.as_data_url()
    assert url.startswith("data:image/png;base64,")


def test_a_corrupt_pdf_is_rejected() -> None:
    with pytest.raises(ValueError, match="could not open the PDF"):
        pdf_to_page_images(b"this is not a pdf")


def test_a_photo_is_wrapped_as_a_single_page(page: PageImage) -> None:
    pages = service._pages_for(page.content, "invoice-photo.png", dpi=100)
    assert len(pages) == 1
    assert pages[0].page == 1


# --------------------------------------------------------------------------- #
# 2. extract_page
# --------------------------------------------------------------------------- #


def test_extract_page_returns_extracted_field_objects(page: PageImage) -> None:
    fields = service.extract_page(
        page, "DOC-INV-0431", client=client_returning(EXTRACTION_BODY),
        settings=make_settings(),
    )

    assert len(fields) == 4
    assert all(isinstance(field, ExtractedField) for field in fields)
    by_name = {field.field: field for field in fields}
    assert set(by_name) == {"invoice_number", "party_name", "date", "amount"}


def test_every_field_carries_confidence_and_provenance(page: PageImage) -> None:
    fields = service.extract_page(
        page, "DOC-INV-0431", client=client_returning(EXTRACTION_BODY),
        settings=make_settings(),
    )
    for field in fields:
        assert isinstance(field.extraction_confidence, Confidence)
        assert field.source.document_id == "DOC-INV-0431"
        assert field.source.page == 1
        assert field.source.bbox is not None or field.source.text_snippet


def test_monetary_values_are_parsed_but_the_snippet_stays_verbatim(page: PageImage) -> None:
    fields = service.extract_page(
        page, "DOC-INV-0431", client=client_returning(EXTRACTION_BODY),
        settings=make_settings(),
    )
    amount = next(field for field in fields if field.field == "amount")
    assert amount.value == 312880.0
    assert amount.source.text_snippet == "Rs. 312,880/-"


def test_an_unreadable_field_carries_no_value(page: PageImage) -> None:
    body = json.dumps(
        {
            "fields": [
                {
                    "field": "invoice_number",
                    "value": None,
                    "extraction_confidence": "low",
                    "bbox": [0.1, 0.1, 0.3, 0.2],
                    "text_snippet": None,
                    "unreadable": True,
                }
            ]
        }
    )
    fields = service.extract_page(
        page, "DOC-INV-0431", client=client_returning(body), settings=make_settings()
    )
    assert fields[0].unreadable is True
    assert fields[0].value is None


def test_a_null_value_is_treated_as_unreadable_even_if_the_model_says_otherwise(
    page: PageImage,
) -> None:
    """The model must not be able to claim it read something and send nothing."""
    body = json.dumps(
        {
            "fields": [
                {
                    "field": "amount",
                    "value": None,
                    "extraction_confidence": "high",
                    "bbox": [0.1, 0.1, 0.3, 0.2],
                    "text_snippet": "smudged",
                    "unreadable": False,
                }
            ]
        }
    )
    fields = service.extract_page(
        page, "DOC-INV-0431", client=client_returning(body), settings=make_settings()
    )
    assert fields[0].unreadable is True
    assert fields[0].value is None


def test_an_unusable_bbox_falls_back_to_the_text_snippet(page: PageImage) -> None:
    """Vision models are unreliable at boxes; the snippet keeps rule 3 satisfied."""
    body = json.dumps(
        {
            "fields": [
                {
                    "field": "amount",
                    "value": 96400,
                    "extraction_confidence": "high",
                    "bbox": [0.9, 0.2, 0.1, 0.4],  # x1 < x0
                    "text_snippet": "96,400.00",
                    "unreadable": False,
                }
            ]
        }
    )
    field = service.extract_page(
        page, "DOC-BNK-001", client=client_returning(body), settings=make_settings()
    )[0]
    assert field.source.bbox is None
    assert field.source.text_snippet == "96,400.00"


def test_out_of_range_bbox_coordinates_are_rejected(page: PageImage) -> None:
    body = json.dumps(
        {
            "fields": [
                {
                    "field": "amount",
                    "value": 500,
                    "extraction_confidence": "high",
                    "bbox": [12, 34, 560, 780],  # pixels, not normalised
                    "text_snippet": "500.00",
                    "unreadable": False,
                }
            ]
        }
    )
    field = service.extract_page(
        page, "DOC-BNK-001", client=client_returning(body), settings=make_settings()
    )[0]
    assert field.source.bbox is None


def test_an_unrecognised_confidence_defaults_to_low(page: PageImage) -> None:
    """'We do not know how sure it was' must never read as 'high'."""
    body = json.dumps(
        {
            "fields": [
                {
                    "field": "amount",
                    "value": 100,
                    "extraction_confidence": "quite sure",
                    "bbox": None,
                    "text_snippet": "100",
                    "unreadable": False,
                }
            ]
        }
    )
    field = service.extract_page(
        page, "DOC-BNK-001", client=client_returning(body), settings=make_settings()
    )[0]
    assert field.extraction_confidence is Confidence.LOW


def test_unknown_field_names_are_dropped(page: PageImage) -> None:
    body = json.dumps(
        {
            "fields": [
                {
                    "field": "vat_registration",
                    "value": "PK-993",
                    "extraction_confidence": "high",
                    "bbox": None,
                    "text_snippet": "PK-993",
                    "unreadable": False,
                },
                {
                    "field": "amount",
                    "value": 100,
                    "extraction_confidence": "high",
                    "bbox": None,
                    "text_snippet": "100",
                    "unreadable": False,
                },
            ]
        }
    )
    fields = service.extract_page(
        page, "DOC-INV-1", client=client_returning(body), settings=make_settings()
    )
    assert [field.field for field in fields] == ["amount"]


# --------------------------------------------------------------------------- #
# Client behaviour: fences, repair, backoff, hard failures
# --------------------------------------------------------------------------- #


def test_markdown_fenced_json_is_still_parsed(page: PageImage) -> None:
    fenced = f"```json\n{EXTRACTION_BODY}\n```"
    fields = service.extract_page(
        page, "DOC-INV-0431", client=client_returning(fenced), settings=make_settings()
    )
    assert len(fields) == 4


def test_unparseable_json_is_repaired_once(page: PageImage) -> None:
    fields = service.extract_page(
        page,
        "DOC-INV-0431",
        client=client_returning("Sorry, here you go:", EXTRACTION_BODY),
        settings=make_settings(),
    )
    assert len(fields) == 4


def test_a_second_unparseable_reply_gives_up(page: PageImage) -> None:
    with pytest.raises(QwenResponseError, match="unparseable JSON twice"):
        service.extract_page(
            page,
            "DOC-INV-0431",
            client=client_returning("nope", "still nope"),
            settings=make_settings(),
        )


def test_rate_limits_are_retried_with_backoff(page: PageImage) -> None:
    attempts = {"n": 0}
    slept: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "2"}, text="slow down")
        return qwen_reply(EXTRACTION_BODY)

    client = QwenVisionClient(
        settings=make_settings(backoff_base_seconds=1.0),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=slept.append,
    )
    fields = service.extract_page(page, "DOC-INV-0431", client=client, settings=make_settings())

    assert len(fields) == 4
    assert attempts["n"] == 2
    assert slept == [2.0], "Retry-After should win over the exponential delay"


def test_timeouts_are_retried_then_reported(page: PageImage) -> None:
    attempts = {"n": 0}
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        raise httpx.ReadTimeout("timed out", request=request)

    client = QwenVisionClient(
        settings=make_settings(max_attempts=3, backoff_base_seconds=1.0),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=slept.append,
    )
    with pytest.raises(QwenTransportError, match="after 3 attempts"):
        service.extract_page(page, "DOC-INV-0431", client=client, settings=make_settings())

    assert attempts["n"] == 3
    assert slept == [1.0, 2.0], "backoff should double, and not sleep after the last try"


def test_an_auth_error_is_not_retried(page: PageImage) -> None:
    attempts = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(401, text="invalid api key")

    client = QwenVisionClient(
        settings=make_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
    )
    with pytest.raises(Exception, match="401"):
        service.extract_page(page, "DOC-INV-0431", client=client, settings=make_settings())
    assert attempts["n"] == 1


def test_a_missing_api_key_says_what_to_do() -> None:
    client = QwenVisionClient(
        settings=make_settings(api_key=None),
        http_client=httpx.Client(transport=httpx.MockTransport(lambda r: qwen_reply("{}"))),
        sleep=lambda _seconds: None,
    )
    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        client.complete_json([{"role": "user", "content": "hi"}])


def test_the_request_is_shaped_for_the_openai_compatible_endpoint(page: PageImage) -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return qwen_reply(EXTRACTION_BODY)

    client = QwenVisionClient(
        settings=make_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
    )
    service.extract_page(page, "DOC-INV-0431", client=client, settings=make_settings())

    assert seen["url"].endswith("/compatible-mode/v1/chat/completions")
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["model"] == "qwen-vl-max"
    assert seen["body"]["temperature"] == 0.0
    parts = seen["body"]["messages"][-1]["content"]
    assert parts[0]["type"] == "image_url"
    assert parts[0]["image_url"]["url"].startswith("data:image/png;base64,")


# --------------------------------------------------------------------------- #
# 3. The ledger: pandas only
# --------------------------------------------------------------------------- #


def csv_bytes(rows: str) -> bytes:
    return rows.encode("utf-8")


LEDGER_CSV = csv_bytes(
    "Date,Particulars,Party Name,Amount,Account Code\n"
    "02/06/2026,Yarn purchase,Gulberg Traders (Pvt) Ltd,\"284,000.00\",5010\n"
    "10/06/2026,Office supplies,Al-Habib Stationers,\"Rs. 45,900/-\",6110\n"
    "14/06/2026,Generator advance,Indus Power Solutions,1500000,1720\n"
    ",,,,\n"
    "18/06/2026,Consultancy,Shalimar Trading Co,\"(187,500.00)\",6420\n"
)


def test_ledger_is_read_into_ledger_entries() -> None:
    entries = read_ledger("DOC-LED-001", "ledger.csv", LEDGER_CSV)

    assert len(entries) == 4
    assert entries[0].party_name == "Gulberg Traders (Pvt) Ltd"
    assert entries[0].amount == Decimal("284000.00")
    assert entries[0].description == "Yarn purchase"
    assert entries[0].account_code == "5010"
    assert entries[0].currency == "PKR"


def test_ledger_dates_are_day_first() -> None:
    """`02/06/2026` is 2 June in Pakistan, not 6 February."""
    entries = read_ledger("DOC-LED-001", "ledger.csv", LEDGER_CSV)
    assert entries[0].date == date(2026, 6, 2)


def test_ledger_amounts_survive_currency_marks_and_brackets() -> None:
    entries = read_ledger("DOC-LED-001", "ledger.csv", LEDGER_CSV)
    by_party = {entry.party_name: entry.amount for entry in entries}
    assert by_party["Al-Habib Stationers"] == Decimal("45900")
    assert by_party["Shalimar Trading Co"] == Decimal("-187500.00")


def test_ledger_provenance_is_the_spreadsheet_row_not_a_page() -> None:
    entries = read_ledger("DOC-LED-001", "ledger.csv", LEDGER_CSV)
    source = entries[0].source
    assert source == Provenance(document_id="DOC-LED-001", row_number=2)
    assert source.page is None and source.bbox is None


def test_blank_rows_are_skipped() -> None:
    entries = read_ledger("DOC-LED-001", "ledger.csv", LEDGER_CSV)
    assert all(entry.party_name for entry in entries)


def test_ledger_reads_excel_too() -> None:
    buffer = io.BytesIO()
    pd.DataFrame(
        {
            "Txn Date": ["05/06/2026"],
            "Vendor": ["Karachi Packaging Co."],
            "Amt": [96400],
        }
    ).to_excel(buffer, index=False)
    entries = read_ledger("DOC-LED-002", "ledger.xlsx", buffer.getvalue())

    assert len(entries) == 1
    assert entries[0].party_name == "Karachi Packaging Co."
    assert entries[0].amount == Decimal("96400")


def test_a_missing_required_column_is_reported_clearly() -> None:
    with pytest.raises(LedgerReadError, match="party_name"):
        read_ledger("DOC-LED-003", "ledger.csv", csv_bytes("Date,Amount\n01/06/2026,100\n"))


def test_an_unsupported_ledger_format_is_rejected() -> None:
    with pytest.raises(LedgerReadError, match="unsupported ledger format"):
        read_ledger("DOC-LED-004", "ledger.pdf", b"%PDF-1.4")


def test_the_ledger_path_never_reaches_a_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reliability rule 2's boundary: a spreadsheet cell must not meet an LLM."""
    def explode(*_args, **_kwargs):
        raise AssertionError("the ledger path must never call Qwen")

    monkeypatch.setattr(QwenVisionClient, "complete_json", explode)
    assert read_ledger("DOC-LED-001", "ledger.csv", LEDGER_CSV)


def test_extract_document_refuses_a_ledger() -> None:
    with pytest.raises(service.ExtractionError, match="read_ledger"):
        service.extract_document(
            "DOC-LED-001", DocumentType.LEDGER, "ledger.xlsx", b"stub",
            settings=make_settings(),
        )


# --------------------------------------------------------------------------- #
# 4. The verifier
# --------------------------------------------------------------------------- #


def low(name: str, value: object) -> ExtractedField:
    return ExtractedField(
        field=name,
        value=value,
        extraction_confidence=Confidence.LOW,
        source=Provenance(document_id="DOC-INV-0431", page=1, text_snippet=str(value)),
    )


def high(name: str, value: object) -> ExtractedField:
    return ExtractedField(
        field=name,
        value=value,
        extraction_confidence=Confidence.HIGH,
        source=Provenance(document_id="DOC-INV-0431", page=1, text_snippet=str(value)),
    )


def test_verifier_reports_agreement(page: PageImage) -> None:
    outcome = service.verify_page(
        page, [low("amount", 312880.0)],
        client=client_returning(AGREE_BODY), settings=make_settings(),
    )
    assert outcome.second_opinion.ran is True
    assert outcome.second_opinion.agrees is True
    assert outcome.needs_human_review is False


def test_a_monetary_disagreement_escalates_with_both_readings(page: PageImage) -> None:
    outcome = service.verify_page(
        page, [low("amount", 312880.0)],
        client=client_returning(DISAGREE_BODY), settings=make_settings(),
    )

    assert outcome.needs_human_review is True
    assert outcome.second_opinion.agrees is False
    disagreement = outcome.second_opinion.disagreements[0]
    assert disagreement.field == "amount"
    assert disagreement.first_reading == 312880.0
    assert disagreement.second_reading == 312860.0


def test_the_verifier_never_picks_a_winner(page: PageImage) -> None:
    """Both readings survive, and no field exists in which to record a verdict."""
    outcome = service.verify_page(
        page, [low("amount", 312880.0)],
        client=client_returning(DISAGREE_BODY), settings=make_settings(),
    )
    disagreement = outcome.second_opinion.disagreements[0]
    assert {disagreement.first_reading, disagreement.second_reading} == {312880.0, 312860.0}
    assert not any(
        "resolv" in name or "winner" in name or "correct" in name
        for name in type(disagreement).model_fields
    )


def test_escalation_cannot_be_suppressed() -> None:
    """The schema itself refuses a monetary disagreement that is not escalated."""
    from app.shared.schemas import FieldDisagreement, SecondOpinion, VerificationOutcome

    with pytest.raises(ValueError, match="needs_human_review must be true"):
        VerificationOutcome(
            second_opinion=SecondOpinion(
                ran=True,
                model="qwen-vl-max",
                agrees=False,
                disagreements=[
                    FieldDisagreement(field="amount", first_reading=1, second_reading=2)
                ],
            ),
            needs_human_review=False,
        )


def test_only_low_confidence_fields_are_verified(page: PageImage) -> None:
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.content.decode("utf-8"))
        return qwen_reply(AGREE_BODY)

    client = QwenVisionClient(
        settings=make_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
    )
    service.verify_page(
        page,
        [high("party_name", "Sialkot Metal Works"), low("amount", 312880.0)],
        client=client,
        settings=make_settings(),
    )

    assert len(sent) == 1
    assert "amount" in sent[0]
    assert "Sialkot Metal Works" not in sent[0]


def test_the_verifier_does_not_run_when_nothing_is_low_confidence(page: PageImage) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("the verifier should not have called Qwen")

    client = QwenVisionClient(
        settings=make_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
    )
    outcome = service.verify_page(
        page, [high("amount", 100.0)], client=client, settings=make_settings()
    )
    assert outcome.second_opinion.ran is False
    assert outcome.needs_human_review is False


def test_the_threshold_can_include_medium_confidence(page: PageImage) -> None:
    medium = ExtractedField(
        field="amount",
        value=100.0,
        extraction_confidence=Confidence.MEDIUM,
        source=Provenance(document_id="DOC-INV-0431", page=1, text_snippet="100"),
    )
    settings = make_settings(verify_at_or_below="medium")
    outcome = service.verify_page(
        page, [medium], client=client_returning(AGREE_BODY), settings=settings
    )
    assert outcome.second_opinion.ran is True


def test_unreadable_fields_are_not_verified(page: PageImage) -> None:
    unreadable = ExtractedField(
        field="amount",
        value=None,
        extraction_confidence=Confidence.LOW,
        source=Provenance(document_id="DOC-INV-0431", page=1, text_snippet="smudge"),
        unreadable=True,
    )
    outcome = service.verify_page(
        page, [unreadable], client=client_returning(AGREE_BODY), settings=make_settings()
    )
    assert outcome.second_opinion.ran is False


# --------------------------------------------------------------------------- #
# 5. extract_document, end to end
# --------------------------------------------------------------------------- #


def test_extract_document_reads_every_page_and_verifies(one_page_pdf: bytes) -> None:
    client = client_returning(EXTRACTION_BODY, DISAGREE_BODY)
    result = service.extract_document(
        "DOC-INV-0431", DocumentType.INVOICE, "invoice.pdf", one_page_pdf,
        client=client, settings=make_settings(),
    )

    assert result.page_count == 1
    assert result.document_type is DocumentType.INVOICE
    assert len(result.fields) == 4
    assert result.second_opinion is not None
    assert result.second_opinion.agrees is False
    assert result.needs_human_review is True


def test_extract_document_agrees_when_the_verifier_agrees(one_page_pdf: bytes) -> None:
    client = client_returning(EXTRACTION_BODY, AGREE_BODY)
    result = service.extract_document(
        "DOC-INV-0431", DocumentType.INVOICE, "invoice.pdf", one_page_pdf,
        client=client, settings=make_settings(),
    )
    assert result.needs_human_review is False
    assert result.second_opinion is not None
    assert result.second_opinion.agrees is True


def test_extract_document_fails_loudly_when_nothing_is_readable(one_page_pdf: bytes) -> None:
    client = client_returning(json.dumps({"fields": []}))
    with pytest.raises(service.ExtractionError, match="no usable fields"):
        service.extract_document(
            "DOC-INV-9", DocumentType.INVOICE, "blank.pdf", one_page_pdf,
            client=client, settings=make_settings(),
        )


# --------------------------------------------------------------------------- #
# 6. DEMO_MODE
# --------------------------------------------------------------------------- #


def test_demo_mode_never_calls_qwen() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("DEMO_MODE must not touch the network")

    client = QwenVisionClient(
        settings=make_settings(demo_mode=True),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
    )
    result = service.extract_document(
        "DOC-INV-0431", DocumentType.INVOICE, "smw-0431.jpg", b"ignored",
        client=client, settings=make_settings(demo_mode=True),
    )
    assert result.document_id == "DOC-INV-0431"
    assert result.fields


def test_demo_mode_returns_the_same_schema_as_the_live_path() -> None:
    """Same type, same downstream code path — only the data source changes."""
    demo = service.extract_document(
        "DOC-INV-0431", DocumentType.INVOICE, "smw-0431.jpg", b"ignored",
        settings=make_settings(demo_mode=True),
    )
    live = service.extract_document(
        "DOC-INV-0431", DocumentType.INVOICE, "invoice.png",
        b"\x89PNG\r\n\x1a\nstub",
        client=client_returning(EXTRACTION_BODY, AGREE_BODY), settings=make_settings(),
    )
    assert type(demo) is type(live)
    assert demo.needs_human_review is True  # the cached invoice disagreed on amount


def test_demo_mode_rewrites_provenance_to_the_requested_document() -> None:
    """Otherwise the evidence viewer would open the wrong file."""
    result = service.extract_document(
        "DOC-INV-9999", DocumentType.INVOICE, "another-invoice.pdf", b"ignored",
        settings=make_settings(demo_mode=True),
    )
    assert result.document_id == "DOC-INV-9999"
    assert result.filename == "another-invoice.pdf"
    assert {field.source.document_id for field in result.fields} == {"DOC-INV-9999"}


def test_demo_mode_prefers_a_per_document_cache(tmp_path, monkeypatch) -> None:
    cache_dir = tmp_path / "extraction-cache"
    cache_dir.mkdir()
    template = json.loads((demo_mode.FIXTURES_DIR / "extraction-result.json").read_text("utf-8"))
    template["filename"] = "cached-on-disk.jpg"
    (cache_dir / "DOC-INV-0431.json").write_text(json.dumps(template), encoding="utf-8")
    monkeypatch.setattr(demo_mode, "CACHE_DIR", cache_dir)

    result = demo_mode.cached_extraction(
        "DOC-INV-0431", DocumentType.INVOICE, "whatever-was-uploaded.jpg"
    )
    assert result.filename == "cached-on-disk.jpg"
