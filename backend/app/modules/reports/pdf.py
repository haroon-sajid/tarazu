"""Render a `ReportContent` to PDF with reportlab.

Deterministic templating: the same content produces the same document, with
the generation timestamp as the only thing that changes between runs, and it
is part of the content. Landscape A4, because the decided-items and audit
tables are wide and an auditor reading a reconciliation wants the columns
side by side rather than folded.
"""

from __future__ import annotations

import base64
import binascii
import io
import logging
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.modules.reports.content import ReportBranding, ReportContent, TableSection

__all__ = ["render_pdf"]

logger = logging.getLogger(__name__)

#: How tall the firm's logo is drawn. The width follows from the aspect ratio,
#: capped so a wide logo cannot push the title off the page.
_LOGO_HEIGHT = 12 * mm
_LOGO_MAX_WIDTH = 45 * mm

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


_FIRM = ParagraphStyle("TarazuFirm", parent=_styles["Normal"], fontName="Helvetica-Bold",
                       fontSize=12, leading=15, textColor=_INK)
_FIRM_CONTACT = ParagraphStyle("TarazuFirmContact", parent=_styles["Normal"], fontSize=8,
                               leading=10, textColor=_MUTED)


def _p(text: str, style: ParagraphStyle = _CELL) -> Paragraph:
    return Paragraph(escape(text or "").replace("\n", "<br/>"), style)


def _logo(branding: ReportBranding | None) -> Image | None:
    """The firm's logo as a flowable, or None.

    A logo that cannot be decoded is not an error worth failing a report over:
    the deliverable is the reconciliation, and a firm should not lose it
    because somebody pasted a malformed data URL into a settings screen. The
    problem is logged and the report is produced without the picture.
    """
    if branding is None or not branding.logo:
        return None
    try:
        _, _, encoded = branding.logo.partition(",")
        raw = base64.b64decode(encoded, validate=True)
        reader = ImageReader(io.BytesIO(raw))
        width, height = reader.getSize()
        if not width or not height:
            return None
        scaled = min(_LOGO_HEIGHT * width / height, _LOGO_MAX_WIDTH)
        return Image(io.BytesIO(raw), width=scaled, height=scaled * height / width)
    except (binascii.Error, ValueError, OSError) as error:
        logger.warning("Could not render the firm logo on the report: %s", error)
        return None


def _letterhead(branding: ReportBranding | None, width: float) -> list:
    """The firm's name, contact line, and logo, above the report's own title."""
    if branding is None:
        return []
    left: list = [Paragraph(escape(branding.display_name), _FIRM)]
    if branding.contact_line:
        left.append(Paragraph(escape(branding.contact_line), _FIRM_CONTACT))

    logo = _logo(branding)
    if logo is None:
        return [*left, Spacer(1, 4 * mm)]

    header = Table(
        [[left, logo]],
        colWidths=[width - _LOGO_MAX_WIDTH, _LOGO_MAX_WIDTH],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (0, 0), "TOP"),
                ("VALIGN", (1, 0), (1, 0), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return [header, Spacer(1, 4 * mm)]


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

    branding = content.branding
    footer_left = (
        f"{branding.display_name} · {meta.client_name} · {meta.case_id} · {meta.report_id}"
        if branding
        else f"{title} · {meta.client_name} · {meta.case_id} · {meta.report_id}"
    )

    def on_page(canvas, document) -> None:  # noqa: ANN001 - reportlab callback
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(_MUTED)
        canvas.drawString(_MARGIN, 8 * mm, footer_left)
        if branding and branding.footer:
            canvas.drawCentredString(_PAGE[0] / 2, 5 * mm, branding.footer)
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
        *_letterhead(branding, width),
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

    if content.urdu_summary:
        # Pointed at rather than drawn. reportlab's built-in fonts carry no
        # Arabic-script glyphs and it performs neither bidirectional reordering
        # nor contextual shaping, so rendering the Urdu here would produce a
        # row of empty boxes over the word "summary". The workbook uses the
        # reader's own fonts and renders it correctly.
        story.append(
            Paragraph(
                escape(
                    "An Urdu executive summary for the business owner is included in "
                    "the Excel annexure to this report, on the "
                    "“Urdu summary” sheet."
                ),
                _NOTE,
            )
        )

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
