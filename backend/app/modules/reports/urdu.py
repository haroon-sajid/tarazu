"""The Urdu executive summary — the page the business owner actually reads.

The assistant has spoken Urdu since the first build; the deliverable the client
receives has not. This closes that gap for the one part of a report a business
owner reads: a short statement of what was checked, what matched, what was
flagged, and who decided.

**Composed, never translated by a model.** Every sentence here is assembled by
deterministic code from counts the pipeline already produced — the same
approach `assistant/composer.py` takes, and for the same reason: a model that
paraphrases a figure can change it. There is no AI import in this module and
there must never be one (rule 2).

**Where it appears.** In the Excel workbook, in the evidence bundle's JSON, and
in the API response — everywhere the reader's own font renders the text. It is
deliberately *not* drawn into the PDF: reportlab's built-in fonts have no
Arabic-script glyphs and reportlab does not do the bidirectional reordering or
contextual shaping Urdu needs, so drawing it there would produce a row of empty
boxes and call it a summary. The PDF prints a pointer to the Excel annexure
instead. Rendering it properly needs a bundled Nastaliq font plus a shaping
pass; that is a deliberate, separate piece of work, and pretending otherwise
would be worse than pointing at the sheet that reads correctly today.
"""

from __future__ import annotations

from decimal import Decimal

__all__ = ["URDU_HEADING", "urdu_executive_summary"]

#: The heading the summary is filed under, in both the sheet and the bundle.
URDU_HEADING = "مختصر جائزہ (Urdu executive summary)"


def _u(number: int) -> str:
    """Western digits, deliberately.

    Urdu is written with either Western or Eastern Arabic numerals, and an
    accountant reading this alongside the English tables and the ledger is
    comparing figures across all three. Keeping one set of digits everywhere is
    what makes that possible; prettier numerals that do not match the workbook
    would cost more than they are worth.
    """
    return f"{number:,}"


def urdu_executive_summary(
    *,
    client_name: str,
    period_start: str | None,
    period_end: str | None,
    item_count: int,
    matched: int,
    partial: int,
    unmatched: int,
    approved: int,
    rejected: int,
    pending: int,
    flag_count: int,
    high_severity: int,
    total_amount: Decimal | None = None,
    currency: str = "PKR",
) -> str:
    """A short plain-Urdu account of the engagement, built from the counts.

    Written for the business owner rather than the auditor: no rule ids, no
    match strengths, no jargon. Every number in it is one of the arguments —
    nothing is computed here beyond joining sentences, so this text can never
    disagree with the tables it summarises.
    """
    sentences: list[str] = []

    period = (
        f" ({period_start} تا {period_end})"
        if period_start and period_end
        else ""
    )
    sentences.append(
        f"{client_name}{period} کے ریکارڈ کا جائزہ مکمل ہو گیا ہے۔"
    )
    sentences.append(
        f"کل {_u(item_count)} اندراجات جانچے گئے۔"
    )
    sentences.append(
        f"ان میں سے {_u(matched)} کا بینک اسٹیٹمنٹ اور رسیدوں سے مکمل ملان ہوا، "
        f"{_u(partial)} کا جزوی ملان ہوا، اور {_u(unmatched)} کا کوئی جوڑ نہیں ملا۔"
    )

    if total_amount is not None:
        sentences.append(
            f"جانچی گئی کل رقم {currency} {total_amount:,.2f} ہے۔"
        )

    if flag_count:
        high = (
            f" ان میں {_u(high_severity)} کو زیادہ اہم قرار دیا گیا۔"
            if high_severity
            else ""
        )
        sentences.append(
            f"{_u(flag_count)} امور کو جانچ کے لیے نشان زد کیا گیا۔{high}"
        )
    else:
        sentences.append("کسی اندراج پر کوئی اعتراض نہیں اٹھایا گیا۔")

    sentences.append(
        f"آڈیٹر نے {_u(approved)} اندراجات منظور اور {_u(rejected)} مسترد کیے۔"
    )
    if pending:
        sentences.append(
            f"{_u(pending)} اندراجات پر ابھی فیصلہ باقی ہے، اس لیے انہیں نتائج میں شامل نہیں کیا گیا۔"
        )

    # The closing line is the product's own promise, in the owner's language.
    sentences.append(
        "ہر عدد کمپیوٹر کے طے شدہ اصولوں سے نکالا گیا ہے اور ہر فیصلہ ایک نامزد "
        "شخص نے کیا ہے۔ مکمل ریکارڈ محفوظ ہے اور اسے تبدیل نہیں کیا جا سکتا۔"
    )

    return " ".join(sentences)
