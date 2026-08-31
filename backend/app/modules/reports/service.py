"""Public interface of the reports module.

This is the only file other modules may import from `modules/reports/`.

Deterministic templating over human-decided data; no AI calls, no
recomputation. It accepts and returns `app/shared/` schema objects (plus the
bytes of the two files), and it does no I/O of its own: the caller stores the
files and records the `ReportRecord`.

What a report contains, in order: a summary block; every item carrying an
explicit human decision, with its match result and the decision; the flags on
those items; the provenance of every figure behind them; the Benford
first-digit table; and the case's full audit trail. Pending items are counted
and named as pending and never listed as findings — see the module README.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from app.modules.reports.content import ReportContent, build_report_content
from app.modules.reports.excel import render_excel
from app.modules.reports.pdf import render_pdf
from app.shared.schemas import (
    AuditRecord,
    BenfordResult,
    CaseRecord,
    ReportRecord,
    ReviewItem,
)

__all__ = ["ReportFiles", "generate_report", "report_content"]


@dataclass(frozen=True)
class ReportFiles:
    """The two rendered files and the record describing them.

    `record` carries the storage paths the caller is expected to write the
    bytes to, and the digests of exactly these bytes, so the record and the
    files can be checked against each other later.
    """

    pdf: bytes
    excel: bytes
    record: ReportRecord
    content: ReportContent


def report_content(
    case: CaseRecord,
    items: list[ReviewItem],
    audit: list[AuditRecord],
    benford: BenfordResult | None,
    *,
    report_id: str,
    generated_by: str,
    generated_at: datetime,
) -> ReportContent:
    """The report as tables of strings, before rendering. Useful for tests."""
    return build_report_content(
        case, items, audit, benford,
        report_id=report_id, generated_by=generated_by, generated_at=generated_at,
    )


def generate_report(
    case: CaseRecord,
    items: list[ReviewItem],
    audit: list[AuditRecord],
    benford: BenfordResult | None,
    *,
    report_id: str,
    generated_by: str,
    generated_at: datetime,
) -> ReportFiles:
    """Render the PDF and the Excel workbook for one case.

    Args:
        case: The case being reported.
        items: Its persisted review queue, decided and pending alike. Only
            decided items are reported as findings.
        audit: The case's audit trail, oldest first, as it stands.
        benford: The stored Benford result, if the case has one.
        report_id: The id the caller minted for this generation.
        generated_by: The accountable person, as a user id.
        generated_at: When. Printed on every page and kept on the record.

    Returns:
        `ReportFiles` with both files and a `ReportRecord` describing them.
    """
    content = report_content(
        case, items, audit, benford,
        report_id=report_id, generated_by=generated_by, generated_at=generated_at,
    )
    pdf = render_pdf(content)
    excel = render_excel(content)
    base = f"{case.case_id}/reports/{report_id}"
    record = ReportRecord(
        report_id=report_id,
        case_id=case.case_id,
        generated_by=generated_by,
        generated_at=generated_at,
        pdf_path=f"{base}/tarazu-report.pdf",
        excel_path=f"{base}/tarazu-report.xlsx",
        pdf_sha256=hashlib.sha256(pdf).hexdigest(),
        excel_sha256=hashlib.sha256(excel).hexdigest(),
        item_count=content.item_count,
        approved_count=content.approved_count,
        rejected_count=content.rejected_count,
        pending_count=content.pending_count,
        flag_count=content.flag_count,
        audit_record_count=content.audit_record_count,
    )
    return ReportFiles(pdf=pdf, excel=excel, record=record, content=content)
