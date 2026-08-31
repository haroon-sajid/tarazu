"""Sales analytics tests. No network, no model — the module is pure pandas.

The reader tests feed real CSV/Excel bytes; the analysis tests drive
`analyze_sales` over handcrafted records so every figure is checkable by hand;
the route tests run the real endpoints over the real in-memory store, and the
pipeline test proves a SALES_DATA document in an upload produces a saved
readout and a trail entry.
"""

from __future__ import annotations

import ast
import io
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core.audit import Actor, ActorType
from app.core.config import DEFAULT_ORG_ID as ORG
from app.core.repository import StoredDocument
from app.core.sqlite_store import LocalDocumentStore, SqliteCaseRepository
from app.modules.analytics import service as analytics
from app.pipeline import run_pipeline
from app.shared.schemas import (
    AuditAction,
    CaseRecord,
    CaseStatus,
    DocumentType,
    Provenance,
    SalesAnalyticsResult,
    SalesRecord,
)

USER_ID = "00000000-0000-4000-8000-000000000001"
AUDITOR = Actor.human(USER_ID)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def a_sale(
    row_id: str,
    day: date,
    customer: str,
    product: str,
    amount: str,
    region: str | None = None,
    document_id: str = "DOC-SLS-0001",
    row_number: int = 2,
) -> SalesRecord:
    return SalesRecord(
        sales_row_id=row_id,
        date=day,
        amount=Decimal(amount),
        customer_name=customer,
        product=product,
        region=region,
        source=Provenance(document_id=document_id, row_number=row_number),
    )


def a_sales_csv() -> bytes:
    """Three clean rows: June ×2 (with regions), July ×1 (without one).

    Money containing the delimiter is quoted, the way a real CSV export writes
    it (RFC 4180) — see the refusal test below for what happens when it is not.
    """
    return (
        "Sale Date,Customer,Item,Region,Amount\n"
        '02/06/2026,Gulberg Traders,Yarn,Punjab,"Rs. 45,900/-"\n'
        "10/06/2026,Al-Habib Stationers,Cloth,Sindh,12000\n"
        "15/07/2026,Gulberg Traders,Cloth,,30000\n"
    ).encode("utf-8")


def a_pdf(text: str = "STATEMENT") -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((72, 120), text, fontsize=16)
    data = document.tobytes()
    document.close()
    return data


def a_ledger() -> bytes:
    buffer = io.BytesIO()
    pd.DataFrame(
        {
            "Date": ["02/06/2026", "10/06/2026", "14/06/2026"],
            "Party Name": [
                "Gulberg Traders (Pvt) Ltd",
                "Al-Habib Stationers",
                "Indus Power Solutions",
            ],
            "Amount": [284000, 45900, 1500000],
            "Particulars": ["Yarn purchase", "Office supplies", "Generator advance"],
        }
    ).to_excel(buffer, index=False)
    return buffer.getvalue()


def a_stored_document(
    case_id: str, document_id: str, filename: str, content: bytes
) -> StoredDocument:
    return StoredDocument(
        document_id=document_id,
        document_type=DocumentType.SALES_DATA,
        filename=filename,
        size_bytes=len(content),
        storage_path=f"{case_id}/{document_id}/{filename}",
    )


def seed_sales_case(
    repository: SqliteCaseRepository,
    org_id: str,
    storage: LocalDocumentStore,
    case_id: str = "CASE-SLS-001",
) -> str:
    """A case in `org_id` carrying one stored SALES_DATA document."""
    content = a_sales_csv()
    repository.create_case(
        org_id,
        CaseRecord(
            case_id=case_id,
            client_name="Haroon Textiles",
            status=CaseStatus.UPLOADED,
            created_by=USER_ID,
            created_at=datetime.now(timezone.utc),
        ),
    )
    document = a_stored_document(case_id, "DOC-SLS-0001", "sales.csv", content)
    storage.put(document.storage_path, content, "text/csv")
    repository.add_documents(org_id, case_id, [document], USER_ID)
    return case_id


# --------------------------------------------------------------------------- #
# Reading the export
# --------------------------------------------------------------------------- #


def test_reading_a_csv_maps_header_aliases_money_and_missing_regions() -> None:
    content = (
        "Ref,Sale Date,Customer,Item,Region,Amount\n"
        'R-001,02/06/2026,Gulberg Traders,Yarn,Punjab,"Rs. 45,900/-"\n'
        "R-002,10/06/2026,Al-Habib Stationers,Cloth,Sindh,12000\n"
        'R-003,20/07/2026,Indus Power,Yarn,,"(1,200)"\n'
    ).encode("utf-8")

    records = analytics.read_sales_data("DOC-SLS-001", "sales.csv", content)

    assert [record.sales_row_id for record in records] == ["R-001", "R-002", "R-003"]
    # dayfirst: the Pakistani 02/06/2026 is 2 June, not 6 February.
    assert [record.date for record in records] == [
        date(2026, 6, 2),
        date(2026, 6, 10),
        date(2026, 7, 20),
    ]
    assert [record.amount for record in records] == [
        Decimal("45900"),
        Decimal("12000"),
        Decimal("-1200"),  # accounting-style parentheses are negative
    ]
    assert records[0].region == "Punjab"
    assert records[2].region is None  # an empty cell is no region, not ""
    # Provenance is the spreadsheet row, and no model was involved.
    assert records[0].source.document_id == "DOC-SLS-001"
    assert records[0].source.row_number == 2
    assert records[0].source.page is None


def test_reading_an_excel_export_parses_numeric_amounts() -> None:
    buffer = io.BytesIO()
    pd.DataFrame(
        {
            "Date": ["03/06/2026", "09/06/2026"],
            "Customer": ["Gulberg Traders", "Indus Power"],
            "Product": ["Yarn", "Cloth"],
            "Region": ["Punjab", None],
            "Amount": [45900, 120000],
        }
    ).to_excel(buffer, index=False)

    records = analytics.read_sales_data("DOC-SLS-009", "sales.xlsx", buffer.getvalue())

    assert [record.amount for record in records] == [
        Decimal("45900"),
        Decimal("120000"),
    ]
    assert records[1].region is None
    # No id column: rows are numbered as a human sees them, header is row 1.
    assert [record.sales_row_id for record in records] == ["SAL-0002", "SAL-0003"]


def test_reading_sales_data_rejects_a_missing_required_column() -> None:
    content = b"Date,Customer,Amount\n02/06/2026,Gulberg Traders,45900\n"

    with pytest.raises(analytics.SalesReadError, match="product"):
        analytics.read_sales_data("DOC-SLS-001", "sales.csv", content)


def test_reading_sales_data_rejects_an_unsupported_format() -> None:
    with pytest.raises(analytics.SalesReadError, match="unsupported"):
        analytics.read_sales_data("DOC-SLS-001", "sales.pdf", b"%PDF-1.7")


def test_reading_sales_data_refuses_an_unquoted_comma_in_an_amount() -> None:
    """Left unquoted, pandas would read `Rs. 45` as the amount — or shift every
    column left. Silently auditing wrong numbers is the one thing this module
    must not do, so a ragged CSV is refused with instructions."""
    content = (
        "Sale Date,Customer,Item,Region,Amount\n"
        "02/06/2026,Gulberg Traders,Yarn,Punjab,Rs. 45,900/-\n"
    ).encode("utf-8")

    with pytest.raises(analytics.SalesReadError, match="quoted"):
        analytics.read_sales_data("DOC-SLS-001", "sales.csv", content)


# --------------------------------------------------------------------------- #
# The analysis
# --------------------------------------------------------------------------- #


def test_analyze_sales_partitions_the_records_by_month_and_product() -> None:
    records = [
        a_sale("SAL-0001", date(2026, 6, 2), "Gulberg Traders", "Yarn", "1000", "Punjab"),
        a_sale("SAL-0002", date(2026, 6, 10), "Al-Habib Stationers", "Yarn", "500", "Sindh"),
        a_sale("SAL-0003", date(2026, 6, 15), "Indus Power", "Cloth", "2000", "Punjab"),
        a_sale("SAL-0004", date(2026, 7, 1), "Gulberg Traders", "Cloth", "1500"),
        a_sale("SAL-0005", date(2026, 7, 20), "Indus Power", "Yarn", "300", "Sindh"),
    ]

    result = analytics.analyze_sales(records)

    assert result.record_count == 5
    assert result.total_revenue == Decimal("5300")
    assert result.period_start == date(2026, 6, 2)
    assert result.period_end == date(2026, 7, 20)
    assert result.document_ids == ["DOC-SLS-0001"]

    # Months partition the records exactly, and ascend.
    assert [(m.month, m.revenue, m.transaction_count) for m in result.monthly_revenue] == [
        ("2026-06", Decimal("3500"), 3),
        ("2026-07", Decimal("1800"), 2),
    ]

    # Products partition the records exactly, ranked by revenue.
    assert [(p.product, p.revenue, p.transaction_count) for p in result.revenue_by_product] == [
        ("Cloth", Decimal("3500"), 2),
        ("Yarn", Decimal("1800"), 3),
    ]
    assert [p.share for p in result.revenue_by_product] == [66.04, 33.96]


def test_analyze_sales_ranks_customers_and_regions() -> None:
    records = [
        a_sale("SAL-0001", date(2026, 6, 2), "Gulberg Traders", "Yarn", "1000", "Punjab"),
        a_sale("SAL-0002", date(2026, 6, 10), "Al-Habib Stationers", "Yarn", "500", "Sindh"),
        a_sale("SAL-0003", date(2026, 6, 15), "Indus Power", "Cloth", "2000", "Punjab"),
        a_sale("SAL-0004", date(2026, 7, 1), "Gulberg Traders", "Cloth", "1500"),
        a_sale("SAL-0005", date(2026, 7, 20), "Indus Power", "Yarn", "300", "Sindh"),
    ]

    result = analytics.analyze_sales(records)

    assert [
        (c.customer_name, c.revenue, c.transaction_count) for c in result.top_customers
    ] == [
        ("Gulberg Traders", Decimal("2500"), 2),
        ("Indus Power", Decimal("2300"), 2),
        ("Al-Habib Stationers", Decimal("500"), 1),
    ]
    # Only records that carry a region are counted — SAL-0004 has none.
    assert [(r.region, r.revenue, r.transaction_count) for r in result.sales_by_region] == [
        ("Punjab", Decimal("3000"), 2),
        ("Sindh", Decimal("800"), 2),
    ]
    # A clean month with clean rows raises nothing.
    assert result.anomalies == []


def test_top_customers_is_capped_at_five() -> None:
    records = [
        a_sale(
            f"SAL-{position:04d}",
            date(2026, 6, position),
            f"Customer {position}",
            "Yarn",
            "100",
        )
        for position in range(1, 7)  # six customers, equal revenue
    ]

    result = analytics.analyze_sales(records)

    assert len(result.top_customers) == 5
    # Equal revenue: the tie breaks alphabetically, deterministically.
    assert [c.customer_name for c in result.top_customers] == [
        "Customer 1",
        "Customer 2",
        "Customer 3",
        "Customer 4",
        "Customer 5",
    ]


def test_analyze_sales_flags_duplicate_and_negative_rows() -> None:
    records = [
        a_sale("SAL-0001", date(2026, 6, 2), "Gulberg Traders", "Yarn", "1000", "Punjab"),
        a_sale("SAL-0002", date(2026, 6, 2), "Gulberg Traders", "Yarn", "1000", "Punjab"),
        a_sale("SAL-0003", date(2026, 6, 5), "Indus Power", "Cloth", "-200", "Sindh", row_number=4),
    ]

    result = analytics.analyze_sales(records)

    by_kind = {anomaly.kind: anomaly for anomaly in result.anomalies}
    assert set(by_kind) == {"negative-amount", "duplicate-transaction"}

    duplicate = by_kind["duplicate-transaction"]
    assert duplicate.source_row_id == "SAL-0001"
    assert duplicate.related_row_ids == ["SAL-0001", "SAL-0002"]

    negative = by_kind["negative-amount"]
    assert negative.source_row_id == "SAL-0003"
    assert negative.source is not None
    assert negative.source.row_number == 4


def test_analyze_sales_flags_a_month_far_from_the_median() -> None:
    records = [
        a_sale("SAL-0001", date(2026, 4, 10), "April Buyer", "Yarn", "100"),
        a_sale("SAL-0002", date(2026, 5, 10), "May Buyer", "Yarn", "100"),
        a_sale("SAL-0003", date(2026, 6, 10), "June Buyer", "Yarn", "500"),
    ]

    result = analytics.analyze_sales(records)

    assert [anomaly.kind for anomaly in result.anomalies] == ["revenue-spike"]
    assert result.anomalies[0].month == "2026-06"
    assert result.anomalies[0].source_row_id is None


def test_analyze_sales_flags_a_transaction_far_above_the_median() -> None:
    records = [
        a_sale(f"SAL-{position:04d}", date(2026, 6, 10), f"Buyer {position}", "Yarn", "100")
        for position in range(1, 10)
    ] + [a_sale("SAL-0010", date(2026, 6, 11), "Wholesale Mart", "Yarn", "2000")]

    result = analytics.analyze_sales(records)

    assert [anomaly.kind for anomaly in result.anomalies] == ["large-transaction"]
    assert result.anomalies[0].source_row_id == "SAL-0010"
    # The nine ordinary sales are not flagged — the rule needs its sample first.
    assert result.record_count == 10


def test_analyze_sales_on_empty_input_is_an_empty_readout() -> None:
    result = analytics.analyze_sales([])

    assert result.record_count == 0
    assert result.total_revenue == Decimal("0")
    assert result.monthly_revenue == []
    assert result.anomalies == []
    assert result.period_start is None


def test_the_result_survives_a_round_trip_through_the_store(
    repository: SqliteCaseRepository, demo_org: str
) -> None:
    records = [
        a_sale("SAL-0001", date(2026, 6, 2), "Gulberg Traders", "Yarn", "1000", "Punjab"),
        a_sale("SAL-0002", date(2026, 7, 1), "Gulberg Traders", "Cloth", "-50"),
    ]
    repository.create_case(
        demo_org,
        CaseRecord(
            case_id="CASE-SLS-001",
            client_name="Haroon Textiles",
            created_by=USER_ID,
            created_at=datetime.now(timezone.utc),
        ),
    )
    result = analytics.analyze_sales(records)

    repository.save_sales_analytics(demo_org, "CASE-SLS-001", result)
    restored = repository.get_sales_analytics(demo_org, "CASE-SLS-001")

    assert restored == result
    assert restored is not None
    assert restored.total_revenue == Decimal("950")
    # Another firm's lookup finds nothing, not somebody else's readout.
    assert repository.get_sales_analytics("11111111-1111-4111-8111-111111111111", "CASE-SLS-001") is None
    # A re-run replaces, which is what upsert-on-(org, case) is for.
    repository.save_sales_analytics(demo_org, "CASE-SLS-001", analytics.analyze_sales([]))
    assert repository.get_sales_analytics(demo_org, "CASE-SLS-001").record_count == 0


# --------------------------------------------------------------------------- #
# The routes
# --------------------------------------------------------------------------- #


def test_post_runs_the_analysis_persists_it_and_records_the_trail(
    client, repository: SqliteCaseRepository, demo_org: str, storage: LocalDocumentStore
) -> None:
    case_id = seed_sales_case(repository, demo_org, storage)

    response = client.post(f"/v1/cases/{case_id}/analytics")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["record_count"] == 3
    assert Decimal(str(body["total_revenue"])) == Decimal("87900")
    assert [entry["month"] for entry in body["monthly_revenue"]] == ["2026-06", "2026-07"]

    saved = repository.get_sales_analytics(demo_org, case_id)
    assert saved is not None
    assert saved.record_count == 3
    assert saved.document_ids == ["DOC-SLS-0001"]

    runs = [
        record
        for record in repository.list_audit(demo_org, case_id)
        if record.action is AuditAction.SALES_ANALYTICS_RUN
    ]
    assert len(runs) == 1
    assert runs[0].actor_type is ActorType.HUMAN
    assert runs[0].actor_id == USER_ID


def test_get_returns_the_saved_result_and_404s_before_any_run(
    client, repository: SqliteCaseRepository, demo_org: str, storage: LocalDocumentStore
) -> None:
    case_id = seed_sales_case(repository, demo_org, storage)

    missing = client.get(f"/v1/cases/{case_id}/analytics")
    assert missing.status_code == 404

    assert client.post(f"/v1/cases/{case_id}/analytics").status_code == 201
    cached = client.get(f"/v1/cases/{case_id}/analytics")

    assert cached.status_code == 200
    assert Decimal(str(cached.json()["total_revenue"])) == Decimal("87900")
    assert cached.json()["record_count"] == 3


def test_post_without_a_sales_document_is_rejected(client, seeded_case: str) -> None:
    """The Haroon sample case has documents of no other kind either: 422, not 500."""
    response = client.post(f"/v1/cases/{seeded_case}/analytics")

    assert response.status_code == 422
    assert "no sales data document" in response.json()["detail"]


def test_analytics_is_scoped_to_the_callers_organization(
    client,
    other_client,
    repository: SqliteCaseRepository,
    demo_org: str,
    storage: LocalDocumentStore,
) -> None:
    case_id = seed_sales_case(repository, demo_org, storage)
    assert client.post(f"/v1/cases/{case_id}/analytics").status_code == 201

    # Firm B: same store, same route, another tenant. The case is not theirs,
    # so it does not exist as far as they can tell — 404, either verb.
    assert other_client.get(f"/v1/cases/{case_id}/analytics").status_code == 404
    assert other_client.post(f"/v1/cases/{case_id}/analytics").status_code == 404


# --------------------------------------------------------------------------- #
# The pipeline
# --------------------------------------------------------------------------- #


def test_the_pipeline_runs_analytics_when_sales_data_is_uploaded(
    repository: SqliteCaseRepository,
    storage: LocalDocumentStore,
    demo_mode,
) -> None:
    case_id = "CASE-SLS"
    documents = [
        (
            StoredDocument(
                document_id="DOC-BNK-001",
                document_type=DocumentType.BANK_STATEMENT,
                filename="statement.pdf",
                size_bytes=1,
                storage_path=f"{case_id}/DOC-BNK-001/statement.pdf",
            ),
            a_pdf(),
        ),
        (
            StoredDocument(
                document_id="DOC-LED-001",
                document_type=DocumentType.LEDGER,
                filename="ledger.xlsx",
                size_bytes=1,
                storage_path=f"{case_id}/DOC-LED-001/ledger.xlsx",
            ),
            a_ledger(),
        ),
        (
            StoredDocument(
                document_id="DOC-INV-0431",
                document_type=DocumentType.INVOICE,
                filename="invoice.pdf",
                size_bytes=1,
                storage_path=f"{case_id}/DOC-INV-0431/invoice.pdf",
            ),
            a_pdf("INVOICE"),
        ),
        (
            a_stored_document(case_id, "DOC-SLS-001", "sales.csv", a_sales_csv()),
            a_sales_csv(),
        ),
    ]

    outcome = run_pipeline(
        ORG, case_id, "Haroon Textiles", documents, AUDITOR, repository, storage
    )

    assert outcome.status is CaseStatus.READY_FOR_REVIEW
    assert len(outcome.review_items) == 3, "the ledger still drives the review queue"

    result = repository.get_sales_analytics(ORG, case_id)
    assert result is not None
    assert result.record_count == 3
    assert result.total_revenue == Decimal("87900")
    assert result.document_ids == ["DOC-SLS-001"]

    runs = [
        record
        for record in repository.list_audit(ORG, case_id)
        if record.action is AuditAction.SALES_ANALYTICS_RUN
    ]
    assert len(runs) == 1
    assert runs[0].actor_type is ActorType.SYSTEM
    assert runs[0].actor_id == "analytics.service"


def test_a_case_without_sales_data_has_no_readout(
    repository: SqliteCaseRepository, storage: LocalDocumentStore, demo_mode
) -> None:
    case_id = "CASE-NOSALES"
    documents = [
        (
            StoredDocument(
                document_id="DOC-LED-001",
                document_type=DocumentType.LEDGER,
                filename="ledger.xlsx",
                size_bytes=1,
                storage_path=f"{case_id}/DOC-LED-001/ledger.xlsx",
            ),
            a_ledger(),
        ),
    ]

    outcome = run_pipeline(
        ORG, case_id, "Client", documents, AUDITOR, repository, storage
    )

    assert outcome.status is CaseStatus.READY_FOR_REVIEW
    assert repository.get_sales_analytics(ORG, case_id) is None
    assert all(
        record.action is not AuditAction.SALES_ANALYTICS_RUN
        for record in repository.list_audit(ORG, case_id)
    )


# --------------------------------------------------------------------------- #
# Integration: upload endpoint + dashboard endpoint
# --------------------------------------------------------------------------- #


def _multipart_file(name: str, content: bytes) -> tuple[str, io.BytesIO]:
    return (name, io.BytesIO(content))


def test_upload_with_sales_data_processes_analytics_through_the_api(
    client: TestClient,
    repository: SqliteCaseRepository,
    demo_org: str,
    demo_mode,
) -> None:
    """The upload endpoint accepts an optional sales_data file and the pipeline
    runs analytics on it — same path as the unit test above, but through the
    real HTTP endpoint."""
    response = client.post(
        "/v1/upload",
        files=[
            ("bank_statement", _multipart_file("statement.pdf", a_pdf())),
            ("ledger", _multipart_file("ledger.xlsx", a_ledger())),
            ("invoices", _multipart_file("invoice.pdf", a_pdf("INVOICE"))),
            ("sales_data", _multipart_file("sales.csv", a_sales_csv())),
        ],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    case_id = body["case_id"]

    # The sales_data document is among the stored documents.
    sales_docs = [
        doc for doc in body["documents"] if doc["document_type"] == "sales_data"
    ]
    assert len(sales_docs) == 1

    # Analytics ran and was persisted.
    saved = repository.get_sales_analytics(demo_org, case_id)
    assert saved is not None
    assert saved.record_count == 3
    assert saved.total_revenue == Decimal("87900")

    # The trail records the analytics run.
    runs = [
        record
        for record in repository.list_audit(demo_org, case_id)
        if record.action is AuditAction.SALES_ANALYTICS_RUN
    ]
    assert len(runs) == 1
    assert runs[0].actor_id == "analytics.service"


def test_dashboard_includes_sales_analytics_when_available(
    client: TestClient,
    repository: SqliteCaseRepository,
    demo_org: str,
    seeded_case: str,
) -> None:
    """When sales analytics have been saved, the dashboard returns them."""
    records = [
        a_sale("SAL-0001", date(2026, 6, 2), "Gulberg Traders", "Yarn", "1000", "Punjab"),
        a_sale("SAL-0002", date(2026, 6, 10), "Al-Habib Stationers", "Yarn", "500", "Sindh"),
        a_sale("SAL-0003", date(2026, 7, 1), "Indus Power", "Cloth", "1500"),
    ]
    result = analytics.analyze_sales(records)
    repository.save_sales_analytics(demo_org, seeded_case, result)

    response = client.get("/v1/dashboard")
    assert response.status_code == 200
    body = response.json()

    assert body["sales_analytics"] is not None
    assert body["sales_analytics"]["record_count"] == 3
    assert Decimal(str(body["sales_analytics"]["total_revenue"])) == Decimal("3000")


def test_dashboard_returns_null_sales_analytics_when_none_saved(
    client: TestClient, seeded_case: str
) -> None:
    """A case without sales data has null sales_analytics on the dashboard."""
    response = client.get("/v1/dashboard")
    assert response.status_code == 200
    assert response.json()["sales_analytics"] is None


def test_upload_with_malformed_sales_csv_returns_clear_error(
    client: TestClient,
    demo_mode,
) -> None:
    """A sales CSV missing required columns gives a 422 with a clear message,
    not a 500."""
    bad_csv = b"Date,Customer,Amount\n02/06/2026,Gulberg Traders,45900\n"
    response = client.post(
        "/v1/upload",
        files=[
            ("bank_statement", _multipart_file("statement.pdf", a_pdf())),
            ("ledger", _multipart_file("ledger.xlsx", a_ledger())),
            ("invoices", _multipart_file("invoice.pdf", a_pdf("INVOICE"))),
            ("sales_data", _multipart_file("sales.csv", bad_csv)),
        ],
    )
    assert response.status_code == 422
    assert "product" in response.json()["detail"].lower()


# --------------------------------------------------------------------------- #
# The module contract
# --------------------------------------------------------------------------- #


def test_the_analytics_module_imports_no_ai_client_and_no_other_module() -> None:
    """Deterministic and self-contained, checked by hand the way `test_rules.py`
    checks `rules/`: no AI client anywhere in the package, and no other module
    either — the package stands on `app.shared/` alone."""
    forbidden = {"httpx", "openai", "dashscope", "anthropic", "requests"}
    package = Path(analytics.__file__).parent
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] not in forbidden, f"{path.name} imports {name}"
                assert not name.startswith("app.modules"), f"{path.name} imports {name}"
