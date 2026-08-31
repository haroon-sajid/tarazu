"""Render a `ReportContent` to PDF with reportlab.

Deterministic templating: the same content produces the same document, with
the generation timestamp as the only thing that changes between runs, and it
is part of the content. Landscape A4, because the decided-items and audit
tables are wide and an auditor reading a reconciliation wants the columns
side by side rather than folded.
"""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.modules.reports.content import ReportContent, TableSection

__all__ = ["render_pdf"]

_PAGE = landscape(A4)
_MARGIN = 14 * mm
_INK = colors.HexColor("#10243A")
_MUTED = colors.HexColor("#6B7A8A")
_BRAND = colors.HexColor("#0E7C66")
_RULE = colors.HexColor("#E1E7E4")
_ZEBRA = colors.HexColor("#F7FAF9")

_styles = getSampleStyleSheet()
_TITLE = ParagraphStyle("TarazuTitle", parent=_styles["Title"], fontSize=20, leading=24,
                        textColor=_INK, alignment=0, spaceAfter=2 * mm)
_SUBTITLE = ParagraphStyle("TarazuSubtitle", parent=_styles["Normal"], fontSize=10,
                           leading=13, textColor=_MUTED, spaceAfter=6 * mm)
_H2 = ParagraphStyle("TarazuH2", parent=_styles["Heading2"], fontSize=13, leading=16,
                     textColor=_INK, spaceBefore=4 * mm, spaceAfter=1.5 * mm)
_NOTE = ParagraphStyle("TarazuNote", parent=_styles["Normal"], fontSize=8.5, leading=11,
                       textColor=_MUTED, spaceAfter=2.5 * mm)
_CELL = ParagraphStyle("TarazuCell", parent=_styles["Normal"], fontSize=7.5, leading=9.5,
                       textColor=_INK)
_HEAD = ParagraphStyle("TarazuHead", parent=_CELL, fontName="Helvetica-Bold",
                       textColor=colors.white)
_LABEL = ParagraphStyle("TarazuLabel", parent=_CELL, fontName="Helvetica-Bold", fontSize=8.5,
                        leading=11, textColor=_MUTED)
_VALUE = ParagraphStyle("TarazuValue", parent=_CELL, fontSize=8.5, leading=11)
_CLOSING = ParagraphStyle("TarazuClosing", parent=_styles["Normal"], fontSize=9, leading=12,
                          textColor=_INK, spaceBefore=6 * mm)


def _p(text: str, style: ParagraphStyle = _CELL) -> Paragraph:
    return Paragraph(escape(text or "").replace("\n", "<br/>"), style)


def _table(section: TableSection, width: float) -> Table:
    weights = section.widths or [1.0] * len(section.columns)
    total = sum(weights)
    col_widths = [width * weight / total for weight in weights]

    data = [[_p(column, _HEAD) for column in section.columns]]
    for row in section.rows:
        data.append([_p(cell) for cell in row])
    if not section.rows:
        data.append([_p("Nothing to report.", _NOTE)] + [_p("")] * (len(section.columns) - 1))

    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _BRAND),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, _RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]
    for index in range(1, len(data)):
        if index % 2 == 0:
            style.append(("BACKGROUND", (0, index), (-1, index), _ZEBRA))
    table.setStyle(TableStyle(style))
    return table


def render_pdf(content: ReportContent) -> bytes:
    """The whole report as PDF bytes."""
    buffer = io.BytesIO()
    meta = content.meta
    title = "Tarazu — Audit Reconciliation Report"

    def on_page(canvas, document) -> None:  # noqa: ANN001 - reportlab callback
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(_MUTED)
        canvas.drawString(_MARGIN, 8 * mm, f"{title} · {meta.client_name} · {meta.case_id} · {meta.report_id}")
        canvas.drawRightString(_PAGE[0] - _MARGIN, 8 * mm, f"Page {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        buffer,
        pagesize=_PAGE,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
        title=f"{title} — {meta.client_name} — {meta.case_id}",
        author="Tarazu — AI Audit Assistant",
        subject=f"Report {meta.report_id}",
        creator="Tarazu reports/ (deterministic templating, no AI)",
    )
    width = _PAGE[0] - 2 * _MARGIN

    story: list = [
        Paragraph(escape(title), _TITLE),
        Paragraph(
            escape(
                f"{meta.client_name} · {meta.case_id} · generated "
                f"{meta.generated_at.strftime('%Y-%m-%d %H:%M UTC')} · {meta.report_id}"
            ),
            _SUBTITLE,
        ),
        Paragraph("Summary", _H2),
    ]

    summary = Table(
        [[_p(label, _LABEL), _p(value, _VALUE)] for label, value in content.summary],
        colWidths=[width * 0.22, width * 0.78],
    )
    summary.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, _RULE),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ]
        )
    )
    story.append(summary)
    story.append(Paragraph(escape(content.closing), _CLOSING))

    for section in content.sections:
        story.append(PageBreak())
        heading = [Paragraph(escape(section.title), _H2)]
        if section.note:
            heading.append(Paragraph(escape(section.note), _NOTE))
        story.append(KeepTogether(heading))
        story.append(_table(section, width))
        story.append(Spacer(1, 3 * mm))

    document.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buffer.getvalue()
