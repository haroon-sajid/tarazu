"""Step 4 of the Ask Tarazu pipeline: word the computed result, in English or Urdu.

Templates over `QueryResult.data`. Every figure in the text comes from the
result; the composer adds sentences, never numbers. A model may later
rephrase what this produces (see `service.py`), and its output is checked
against these facts — so this file is the floor the answer can never fall
below, and it works with no model at all.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.modules.assistant.planner import Plan
from app.modules.assistant.queries import RULE_DESCRIPTIONS, QueryResult, money
from app.shared.schemas import AssistantIntent, AssistantLanguage

__all__ = ["compose"]

_DECIDE = {
    "en": "These are suggestions from deterministic rules. The decision on each item is yours and is recorded in the audit trail.",
    "ur": "یہ متعین اصولوں کی تجاویز ہیں۔ ہر آئٹم کا فیصلہ آپ کا ہے اور آڈٹ ٹریل میں محفوظ ہوتا ہے۔",
}

_REFUSAL = {
    "en": (
        "I can't answer that from this case's uploaded documents, so I won't guess: Tarazu answers only from "
        "what the client actually provided. Ask about the match results, one row or invoice by its identifier, "
        "the invoices, the bank statement lines, the flags, a party by name, a day or an amount, totals by "
        "vendor or month, the Benford analysis, the documents, the decisions, the reports, or the history."
    ),
    "ur": (
        "میں اس سوال کا جواب اس کیس کی اپ لوڈ شدہ دستاویزات سے نہیں دے سکتا، اس لیے اندازہ نہیں لگاؤں گا: ترازو صرف اسی سے جواب دیتا ہے جو کلائنٹ نے واقعی فراہم کیا ہو۔ "
        "میچ کے نتائج، کسی قطار یا انوائس کے شناختی نمبر، انوائسز، بینک اسٹیٹمنٹ کی قطاروں، نشانیوں، کسی فریق کے نام، کسی تاریخ یا رقم، وینڈر یا مہینے کے حساب سے مجموعی رقم، بینفورڈ تجزیے، دستاویزات، فیصلوں، رپورٹوں یا تاریخچے کے بارے میں پوچھیں۔"
    ),
}

#: The question was about this audit — it used its words — but named no query
#: the planner knows. Say that, and show the shapes that work; never tell an
#: auditor their own case is "not answerable from the documents".
_REFUSAL_ON_TOPIC = {
    "en": (
        "That sounds like a question about this audit, but I couldn't tell which part of it you mean, so I won't guess. "
        "I can answer, from this case's own data: the match results (\"match results\", \"partial matches\", \"which items are unmatched?\"); "
        "one row, invoice, or bank line by its identifier (\"RI-0005\", \"invoice INV-2026-0087\", \"row 16\"); "
        "the invoices, the bank statement lines, or every ledger row; a party by name; a day or month (\"what was paid on 11 June?\"); "
        "a specific amount; the flags and each rule; totals, top vendors, largest payments; how confidently the documents were read; "
        "the documents, the decisions, the reports, the history; and the case itself."
    ),
    "ur": (
        "یہ سوال اس آڈٹ کے بارے میں لگتا ہے، مگر میں یہ طے نہیں کر سکا کہ آپ کا مطلب اس کا کون سا حصہ ہے، اس لیے اندازہ نہیں لگاؤں گا۔ "
        "میں اس کیس کے اپنے ڈیٹا سے بتا سکتا ہوں: میچ کے نتائج (\"میچ کے نتائج\"، \"جزوی میچ\"، \"کون سے آئٹم غیر مماثل ہیں؟\")؛ "
        "کوئی ایک قطار، انوائس یا بینک لائن اس کے شناختی نمبر سے (\"RI-0005\"، \"انوائس INV-2026-0087\"، \"قطار 16\")؛ "
        "انوائسز، بینک اسٹیٹمنٹ کی قطاریں، یا لیجر کی ہر قطار؛ کوئی فریق نام سے؛ کوئی دن یا مہینہ؛ کوئی مخصوص رقم؛ نشانیاں اور ہر اصول؛ "
        "مجموعی رقم، بڑے وینڈر، بڑی ادائیگیاں؛ دستاویزات کتنے اعتماد سے پڑھی گئیں؛ دستاویزات، فیصلے، رپورٹیں، تاریخچہ؛ اور کیس خود۔"
    ),
}

_UNSUPPORTED = {
    "en": "The uploaded ledger records payments only - it does not carry sales, revenue, income, or profit figures, so I can't compute that from this case. I can tell you the total paid, the totals by vendor or by month, the largest payments, and what is unmatched or flagged.",
    "ur": "اپ لوڈ شدہ لیجر میں صرف ادائیگیاں درج ہیں؛ اس میں فروخت، آمدنی یا منافع کے اعداد نہیں ہیں، اس لیے میں اس کیس سے یہ نہیں نکال سکتا۔ میں کل ادا شدہ رقم، وینڈر یا مہینے کے حساب سے مجموعی رقم، سب سے بڑی ادائیگیاں، اور غیر مماثل یا نشان زدہ آئٹمز بتا سکتا ہوں۔",
}

_HELP = {
    "en": (
        "Yes, ask away. I answer questions about this audit, grounded only in what was actually uploaded and decided. "
        "About the results: \"match results\", \"which items are unmatched?\", \"explain the structuring flag\", "
        "\"any duplicate payments?\", \"Benford summary\". "
        "About the data: \"which invoices are in this case?\", \"what is in the bank statement?\", \"list all ledger rows\", "
        "\"what was paid on 11 June?\", \"any payment of 49,500?\", \"top vendors\", \"what did we pay Karachi Packaging?\". "
        "About one thing, name it: \"RI-0005\", \"invoice INV-2026-0087\", \"row 16\". "
        "About the engagement's own record: \"what documents are in this case?\", \"what did the model read?\", "
        "\"how confident was the reading?\", \"what have we decided so far?\", \"which reports exist?\", "
        "\"what happened in this case?\", \"who is the client?\", \"show me all my cases\". "
        "And if you are new to auditing, ask \"what is reconciliation?\" or \"explain materiality\". "
        "I keep a plain-language glossary for exactly that. "
        "I can also answer in Urdu: ask in Urdu or say \"in Urdu\"."
    ),
    "ur": (
        "جی، پوچھیں۔ میں اس آڈٹ کے سوالوں کے جواب صرف اپ لوڈ شدہ اور فیصلہ شدہ چیزوں کی بنیاد پر دیتا ہوں۔ "
        "نتائج کے بارے میں: \"میچ کے نتائج\"، \"کون سے آئٹم غیر مماثل ہیں؟\"، \"کل اخراجات\"، \"بینفورڈ خلاصہ\"۔ "
        "ڈیٹا کے بارے میں: \"اس کیس میں کون سی انوائسز ہیں؟\"، \"بینک اسٹیٹمنٹ میں کیا ہے؟\"، \"تمام قطاریں دکھائیں\"، \"11 جون کو کیا ادا ہوا؟\"۔ "
        "کسی ایک چیز کے بارے میں اس کا نمبر لکھیں: \"RI-0005\"، \"انوائس INV-2026-0087\"، \"قطار 16\"۔ "
        "ریکارڈ کے بارے میں: \"اس کیس میں کون سے دستاویزات ہیں؟\"، \"ماڈل نے کیا پڑھا؟\"، \"اب تک کیا فیصلے ہوئے؟\"، "
        "\"اس کیس میں کیا ہوا؟\"، \"کلائنٹ کون ہے؟\"، \"میرے تمام کیس دکھائیں\"۔ "
        "اگر آڈٹ کے لیے نئے ہیں تو پوچھیں \"مطابقت کیا ہے؟\" یا \"اہمیت کیا ہے؟\"۔ میرے پاس سادہ زبان کی لغت موجود ہے۔ "
        "اردو میں بھی جواب دے سکتا ہوں: اردو میں پوچھیں یا کہیں \"اردو میں\"۔"
    ),
}

_STATUS_UR = {"matched": "مماثل", "partial": "جزوی", "unmatched": "غیر مماثل"}
_DECISION_UR = {"pending": "زیر التوا", "approved": "منظور", "rejected": "مسترد"}
_LEVEL_UR = {"high": "زیادہ", "medium": "درمیانی", "low": "کم"}
_MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
_MONTHS_UR = ["جنوری", "فروری", "مارچ", "اپریل", "مئی", "جون", "جولائی", "اگست", "ستمبر", "اکتوبر", "نومبر", "دسمبر"]


def _d(value: date | None) -> str:
    return value.isoformat() if value else "-"


def _m(amount: Decimal, currency: str) -> str:
    return money(amount, currency)


def _n(count: int, singular: str, plural: str | None = None) -> str:
    """"1 row", "2 rows"."""
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def _status(value: str, lang: str) -> str:
    return _STATUS_UR.get(value, value) if lang == "ur" else value


def _decision(value: str, lang: str) -> str:
    return _DECISION_UR.get(value, value) if lang == "ur" else value


def _level(value: str, lang: str) -> str:
    return _LEVEL_UR.get(value, value) if lang == "ur" else value


def _more(count: int, lang: str) -> str:
    if count <= 0:
        return ""
    return f"\n\n… اور {count} مزید۔" if lang == "ur" else f"\n\n…and {count} more."


def _list(rows: list[dict], currency: str, lang: str) -> str:
    lines = []
    for row in rows:
        if lang == "ur":
            lines.append(f"• {row['party']}، {_m(row['amount'], row.get('currency', currency))}، {_d(row['date'])} ({row['review_item_id']}): {row.get('explanation') or row['reason']}")
        else:
            lines.append(f"• {row['party']}, {_m(row['amount'], row.get('currency', currency))} on {_d(row['date'])} ({row['review_item_id']}): {row.get('explanation') or row['reason']}")
    return "\n".join(lines)


def _counterpart(row: dict, lang: str) -> str:
    """"bank line BNK-0012 (2026-06-02, p.1); invoice INV-2026-0087" — from the
    row's structured counterparts, worded in the answer's language."""
    parts = []
    bank = row.get("bank")
    invoice = row.get("invoice")
    if bank:
        page = f"، صفحہ {bank['page']}" if lang == "ur" and bank["page"] else (f", p.{bank['page']}" if bank["page"] else "")
        parts.append((f"بینک لائن {bank['bank_row_id']} ({_d(bank['date'])}{page})" if lang == "ur"
                      else f"bank line {bank['bank_row_id']} ({_d(bank['date'])}{page})"))
    if invoice:
        parts.append(f"انوائس {invoice['number']}" if lang == "ur" else f"invoice {invoice['number']}")
    if not parts:
        return "نہ بینک لائن نہ انوائس" if lang == "ur" else "no bank line and no invoice"
    return "؛ ".join(parts) if lang == "ur" else "; ".join(parts)


def _item_card(detail: dict, lang: str) -> str:
    """Everything known about one row, as the review screen would show it."""
    currency = detail["currency"]
    bank, invoice = detail["bank"], detail["invoice"]
    flags = detail["flag_rows"]
    weakest = detail["weakest"]
    if lang == "ur":
        lines = [f"{detail['review_item_id']}: {detail['party']}، {_m(detail['amount'], currency)}، {_d(detail['date'])}۔"]
        lines.append(f"• لیجر: {detail['ledger_row_id']} (شیٹ قطار {detail['row_number'] or '-'})، \"{detail['description'] or '-'}\"، اکاؤنٹ {detail['account'] or '-'}۔")
        lines.append(
            f"• بینک اسٹیٹمنٹ: {bank['bank_row_id']}، {_d(bank['date'])}، {_m(bank['amount'], bank['currency'])}، \"{bank['description']}\" (صفحہ {bank['page'] or '-'})۔"
            if bank else "• بینک اسٹیٹمنٹ: کوئی نہیں۔ اس قطار کے لیے بینک لائن نہیں ملی۔"
        )
        lines.append(
            f"• انوائس: {invoice['number']}، {_d(invoice['date'])}، {_m(invoice['amount'], invoice['currency'])}، {invoice['party']} (صفحہ {invoice['page'] or '-'})۔"
            if invoice else "• انوائس: کوئی منسلک نہیں۔"
        )
        lines.append(f"• میچ: {_status(detail['status'], lang)} ({_level(detail['strength'], lang)} مضبوطی)، اصول {detail['rule_id']}۔ {detail['reason']}")
        if flags:
            lines.append(f"• نشانیاں ({len(flags)}): " + "؛ ".join(f"{f['rule_id']} ({_level(f['severity'], lang)}): {f['explanation']}" for f in flags))
        else:
            lines.append("• نشانیاں: کوئی نہیں۔")
        reading = ""
        if weakest and (weakest["unreadable"] or weakest["confidence"] != "high"):
            reading = (f"؛ کمزور ترین پڑھائی: {weakest['field']} ناقابلِ مطالعہ" if weakest["unreadable"]
                       else f"؛ کمزور ترین پڑھائی: {weakest['field']} = {weakest['value']} ({_level(weakest['confidence'], lang)})")
        lines.append(f"• نکاسی کا اعتماد: {_level(detail['confidence'], lang)} ({detail['readings']} پڑھائیاں، {detail['unreadable']} ناقابلِ مطالعہ){reading}۔")
        if detail["decision"] == "pending":
            lines.append("• فیصلہ: زیر التوا، جائزہ اسکرین پر واضح انسانی فیصلے کا منتظر۔")
        else:
            reason = f"۔ وجہ: {detail['rejection_reason'].rstrip('.۔')}" if detail["rejection_reason"] else ""
            lines.append(f"• فیصلہ: {_decision(detail['decision'], lang)}، {detail['decided_by']} نے {detail['decided_at']} پر{reason}۔")
        return "\n".join(lines)

    lines = [f"{detail['review_item_id']}: {detail['party']}, {_m(detail['amount'], currency)} on {_d(detail['date'])}."]
    lines.append(f"• Ledger: {detail['ledger_row_id']} (sheet row {detail['row_number'] or '-'}), \"{detail['description'] or '-'}\", account {detail['account'] or '-'}.")
    lines.append(
        f"• Bank statement: {bank['bank_row_id']} on {_d(bank['date'])}, {_m(bank['amount'], bank['currency'])}, \"{bank['description']}\" (page {bank['page'] or '-'})."
        if bank else "• Bank statement: none. No bank line was found for this row."
    )
    lines.append(
        f"• Invoice: {invoice['number']} dated {_d(invoice['date'])}, {_m(invoice['amount'], invoice['currency'])}, {invoice['party']} (page {invoice['page'] or '-'})."
        if invoice else "• Invoice: none attached."
    )
    lines.append(f"• Match: {detail['status']} ({detail['strength']} strength) by rule {detail['rule_id']}. {detail['reason']}")
    if flags:
        lines.append(f"• Flags ({len(flags)}): " + "; ".join(f"{f['rule_id']} ({f['severity']}): {f['explanation']}" for f in flags))
    else:
        lines.append("• Flags: none.")
    reading = ""
    if weakest and (weakest["unreadable"] or weakest["confidence"] != "high"):
        where = f" from {weakest['document_id']}" + (f" page {weakest['page']}" if weakest["page"] else "")
        reading = (f"; weakest reading: {weakest['field']} unreadable{where}" if weakest["unreadable"]
                   else f"; weakest reading: {weakest['field']} = {weakest['value']} ({weakest['confidence']}){where}")
    lines.append(f"• Extraction confidence: {detail['confidence']} ({_n(detail['readings'], 'reading')}, {detail['unreadable']} unreadable){reading}.")
    if detail["decision"] == "pending":
        lines.append("• Decision: pending, awaiting an explicit human decision on the Review screen.")
    else:
        reason = f". Reason: {detail['rejection_reason'].rstrip('.')}" if detail["rejection_reason"] else ""
        lines.append(f"• Decision: {detail['decision']} by {detail['decided_by']} at {detail['decided_at']}{reason}.")
    return "\n".join(lines)


def compose(plan: Plan, result: QueryResult) -> str:
    lang = "ur" if plan.language is AssistantLanguage.URDU else "en"
    data = result.data
    intent = plan.intent

    if intent is AssistantIntent.HELP:
        return _HELP[lang]
    if intent is AssistantIntent.UNSUPPORTED:
        return _UNSUPPORTED[lang]
    if intent is AssistantIntent.UNKNOWN:
        return _REFUSAL_ON_TOPIC[lang] if plan.hint == "audit" else _REFUSAL[lang]
    if not result.grounded:
        # A workspace question with no workspace loaded: nothing was computed,
        # so there is nothing to word. Refuse rather than guess.
        return _REFUSAL[lang]

    if intent is AssistantIntent.SUMMARY:
        if lang == "ur":
            text = (
                f"اس کیس میں {data['total_items']} لیجر قطاریں ہیں: {data['matched']} مماثل، {data['partial']} جزوی، {data['unmatched']} غیر مماثل۔ "
                f"فیصلے: {data['approved']} منظور، {data['rejected']} مسترد، {data['pending']} زیر التوا۔ "
                f"کل {data['total_flags']} نشانیاں {data['flagged_items']} آئٹمز پر: {data['high']} زیادہ، {data['medium']} درمیانی، {data['low']} کم شدت۔ "
                f"لیجر قطاروں کا مجموعہ {_m(data['total_amount'], data['currency'])}۔ "
                "ہر زیر التوا آئٹم کو رپورٹ سے پہلے واضح انسانی فیصلہ درکار ہے۔"
            )
        else:
            text = (
                f"{data['total_items']} ledger rows: {data['matched']} matched, {data['partial']} partial, {data['unmatched']} unmatched. "
                f"Decisions: {data['approved']} approved, {data['rejected']} rejected, {data['pending']} pending. "
                f"{data['total_flags']} flags on {data['flagged_items']} items: {data['high']} high, {data['medium']} medium, {data['low']} low severity. "
                f"The ledger rows total {_m(data['total_amount'], data['currency'])}. "
                "Every pending item needs an explicit human decision before the report is complete."
            )
        return text

    if intent is AssistantIntent.MATCHES:
        rows = data["rows"]
        status = data["status"]
        currency = data["currency"]
        lines = []
        for row in rows:
            if lang == "ur":
                lines.append(f"• {row['party']}، {_m(row['amount'], row['currency'])}، {_d(row['date'])} ({row['review_item_id']}): {_status(row['status'], lang)} ({_level(row['strength'], lang)}) اصول {row['rule_id']} سے، {_counterpart(row, lang)}۔ {row['reason']}")
            else:
                lines.append(f"• {row['party']}, {_m(row['amount'], row['currency'])} on {_d(row['date'])} ({row['review_item_id']}): {row['status']} ({row['strength']}) by {row['rule_id']}, with {_counterpart(row, lang)}. {row['reason']}")
        body = "\n".join(lines) + _more(data["more"], lang)
        if status is not None:
            if not rows:
                return (f"اس کیس میں کوئی قطار {_status(status, lang)} نہیں۔" if lang == "ur"
                        else f"No row in this case is {status}.")
            if lang == "ur":
                return f"{data['count']} {_status(status, lang)} قطاریں، مجموعی {_m(data['total'], currency)}:\n\n{body}"
            return f"{_n(data['count'], status + ' row')}, totalling {_m(data['total'], currency)}:\n\n{body}"
        if lang == "ur":
            return (
                f"{data['total_items']} لیجر قطاروں کا ملاپ: {data['matched']} مماثل، {data['partial']} جزوی، {data['unmatched']} غیر مماثل؛ "
                f"میچ کی مضبوطی {data['high']} زیادہ، {data['medium']} درمیانی، {data['low']} کم۔ قطاروں کا مجموعہ {_m(data['total'], currency)}۔\n\n{body}\n\n"
                "میچ متعین کوڈ کا نتیجہ ہے: وہی قطاریں ہمیشہ ویسے ہی ملتی ہیں، اور ہر قطار کا فیصلہ کرنے والا اصول نام سے درج ہے۔ ہر قطار کا فیصلہ آپ کا ہے۔"
            )
        return (
            f"How the {data['total_items']} ledger rows reconciled: {data['matched']} matched, {data['partial']} partial, {data['unmatched']} unmatched; "
            f"match strength {data['high']} high, {data['medium']} medium, {data['low']} low. The rows total {_m(data['total'], currency)}.\n\n{body}\n\n"
            "Matching is deterministic code: the same rows always reconcile the same way, and the rule that decided each row is named. "
            "The decision on each row stays yours."
        )

    if intent is AssistantIntent.ITEM:
        hits = data["hits"]
        label = data["label"]
        if not hits:
            if lang == "ur":
                return (
                    f"اس کیس میں کوئی آئٹم \"{label}\" کے حوالے سے نہیں ملا۔ میں جائزہ آئٹم (RI-0005)، لیجر قطار (LED-0014 یا \"قطار 16\")، "
                    "بینک لائن (BNK-0051)، انوائس نمبر (INV-2026-0087 یا \"انوائس 0087\")، یا نشانی (FLG-0009) تلاش کر سکتا ہوں۔"
                )
            return (
                f"No item in this case carries the reference \"{label}\". I can look up a review item (RI-0005), a ledger row "
                "(LED-0014 or \"row 16\"), a bank line (BNK-0051), an invoice number (INV-2026-0087 or \"invoice 0087\"), "
                "or a flag (FLG-0009)."
            )
        if len(hits) > 3:
            lines = []
            for row in hits:
                if lang == "ur":
                    lines.append(f"• {row['party']}، {_m(row['amount'], row['currency'])}، {_d(row['date'])} ({row['review_item_id']}): {_status(row['status'], lang)}، فیصلہ {_decision(row['decision'], lang)}")
                else:
                    lines.append(f"• {row['party']}, {_m(row['amount'], row['currency'])} on {_d(row['date'])} ({row['review_item_id']}): {row['status']}, decision {row['decision']}")
            body = "\n".join(lines)
            if lang == "ur":
                return f"{len(hits)} آئٹم \"{label}\" کا حوالہ رکھتے ہیں:\n\n{body}\n\nکسی ایک کی پوری تفصیل کے لیے اس کا نمبر لکھیں۔"
            return f"{len(hits)} items reference \"{label}\":\n\n{body}\n\nName one of them for its full detail."
        cards = "\n\n".join(_item_card(detail, lang) for detail in hits)
        if len(hits) > 1:
            intro = (f"\"{label}\" {len(hits)} آئٹمز پر ملتا ہے:\n\n" if lang == "ur"
                     else f"\"{label}\" matches {len(hits)} items:\n\n")
            return intro + cards
        return cards

    if intent is AssistantIntent.INVOICES:
        rows = data["rows"]
        currency = data["currency"]
        if not rows:
            if lang == "ur":
                return (f"اس کیس کی کسی لیجر قطار کے ساتھ انوائس منسلک نہیں: {data['without']} قطاروں کے پیچھے صرف بینک لائن ہے یا کچھ نہیں۔ "
                        "فہرست کے لیے پوچھیں: \"کون سی قطاریں ثبوت سے خالی ہیں؟\"")
            return (f"No invoice is attached to any ledger row in this case: all {data['without']} rows have a bank line only, or nothing at all. "
                    "Ask \"which rows are missing evidence?\" for the list.")
        lines = []
        for row in rows:
            if lang == "ur":
                settled = "، ".join(f"{p['review_item_id']} ({_d(p['date'])}، {_status(p['status'], lang)}، {_decision(p['decision'], lang)})" for p in row["paid_by"])
                twice = "؛ ایک ہی انوائس دو بار ادا ہوئی" if len(row["paid_by"]) > 1 else ""
                lines.append(f"• {row['number']}: {row['party']}، {_m(row['amount'], row['currency'])}، {_d(row['date'])} (دستاویز {row['document_id']}، صفحہ {row['page'] or '-'})؛ {len(row['paid_by'])} لیجر قطار سے ادا: {settled}{twice}")
            else:
                settled = ", ".join(f"{p['review_item_id']} on {_d(p['date'])} ({p['status']}, {p['decision']})" for p in row["paid_by"])
                twice = "; the same invoice paid more than once" if len(row["paid_by"]) > 1 else ""
                lines.append(f"• {row['number']}: {row['party']}, {_m(row['amount'], row['currency'])}, dated {_d(row['date'])} (document {row['document_id']}, page {row['page'] or '-'}); settled by {_n(len(row['paid_by']), 'ledger row')}: {settled}{twice}")
        body = "\n".join(lines) + _more(data["more"], lang)
        if lang == "ur":
            return (
                f"ثبوت میں {data['count']} انوائسز ہیں، مجموعی {_m(data['total'], currency)}؛ {data['without']} لیجر قطاروں کے پیچھے کوئی انوائس نہیں:\n\n{body}\n\n"
                "کسی انوائس کی پوری میچ تفصیل کے لیے اس کا نمبر لکھیں۔"
            )
        return (
            f"{_n(data['count'], 'invoice')} in the evidence, totalling {_m(data['total'], currency)}; "
            f"{_n(data['without'], 'ledger row')} {'has' if data['without'] == 1 else 'have'} no invoice behind {'it' if data['without'] == 1 else 'them'}:\n\n{body}\n\n"
            "Name an invoice by its number for the full match detail behind it."
        )

    if intent is AssistantIntent.BANK:
        rows = data["rows"]
        currency = data["currency"]
        if not rows:
            return ("اس کیس کی کسی لیجر قطار سے کوئی بینک لائن نہیں ملی۔" if lang == "ur"
                    else "No bank statement line is matched to any ledger row in this case.")
        pages = ", ".join(str(page) for page in data["pages"]) or "-"
        lines = []
        for row in rows:
            balance = (f"، بقایا {_m(row['balance'], row['currency'])}" if lang == "ur" else f", balance {_m(row['balance'], row['currency'])}") if row["balance"] is not None else ""
            if lang == "ur":
                pays = "، ".join(f"{p['review_item_id']} {p['party']}" for p in row["pays"])
                lines.append(f"• {row['bank_row_id']}: {_d(row['date'])}، {_m(row['amount'], row['currency'])}، \"{row['description']}\" (صفحہ {row['page'] or '-'}{balance}) → {pays} کی ادائیگی")
            else:
                pays = ", ".join(f"{p['review_item_id']} {p['party']}" for p in row["pays"])
                lines.append(f"• {row['bank_row_id']}: {_d(row['date'])}, {_m(row['amount'], row['currency'])}, \"{row['description']}\" (page {row['page'] or '-'}{balance}) → pays {pays}")
        body = "\n".join(lines) + _more(data["more"], lang)
        read = ""
        if data["lines_read"] is not None:
            read = (f" ماڈل نے اسٹیٹمنٹ سے کل {data['lines_read']} قطاریں پڑھیں۔" if lang == "ur"
                    else f" The vision model read {data['lines_read']} lines from the statement in all.")
        if lang == "ur":
            return (
                f"بینک اسٹیٹمنٹ کی {data['count']} قطاریں لیجر قطاروں سے ملی ہیں، مجموعی {_m(data['total'], currency)}، صفحات {pages} پر؛ "
                f"{data['without']} لیجر قطاروں کی کوئی بینک لائن نہیں۔{read}\n\n{body}\n\n"
                "اسٹیٹمنٹ وژن ماڈل پڑھتا ہے اور ہر قطار اپنا صفحہ ساتھ رکھتی ہے۔ یہاں صرف وہ قطاریں ہیں جو کسی لیجر قطار سے ملیں۔ پوری اسٹیٹمنٹ دستاویزات کی اسکرین پر ہے۔"
            )
        return (
            f"{_n(data['count'], 'bank statement line')} {'is' if data['count'] == 1 else 'are'} matched to ledger rows, totalling {_m(data['total'], currency)}, "
            f"on page(s) {pages}; {_n(data['without'], 'ledger row')} {'has' if data['without'] == 1 else 'have'} no bank line.{read}\n\n{body}\n\n"
            "The statement is read by the vision model, and every line keeps the page it came from. Only lines matched to a ledger row are listed here. "
            "The Documents screen shows the whole statement."
        )

    if intent is AssistantIntent.LEDGER:
        rows = data["rows"]
        currency = data["currency"]
        if not rows:
            return ("لیجر میں کوئی قطار نہیں۔" if lang == "ur" else "The ledger has no rows.")
        lines = []
        for row in rows:
            flags = ""
            if row["flag_count"]:
                flags = f"، {row['flag_count']} نشانیاں" if lang == "ur" else f", {_n(row['flag_count'], 'flag')}"
            if lang == "ur":
                lines.append(f"• {_d(row['date'])}، {row['party']}، {_m(row['amount'], row['currency'])} ({row['review_item_id']}، شیٹ قطار {row['row_number'] or '-'}): {_status(row['status'], lang)}، {_decision(row['decision'], lang)}{flags}، \"{row['description'] or '-'}\"")
            else:
                lines.append(f"• {_d(row['date'])}, {row['party']}, {_m(row['amount'], row['currency'])} ({row['review_item_id']}, sheet row {row['row_number'] or '-'}): {row['status']}, {row['decision']}{flags}, \"{row['description'] or '-'}\"")
        body = "\n".join(lines) + _more(data["more"], lang)
        if lang == "ur":
            return (
                f"لیجر میں {data['count']} قطاریں ہیں، مجموعی {_m(data['total'], currency)}، {_d(data['period_start'])} سے {_d(data['period_end'])} تک، {data['parties']} فریقوں کو:\n\n{body}\n\n"
                "لیجر کلائنٹ کا اپنا ریکارڈ ہے، اسپریڈ شیٹ کوڈ سے پڑھا گیا؛ اوپر کی ہر قطار بینک اسٹیٹمنٹ اور انوائسز سے جانچی گئی ہے۔ ہر قطار کے ملاپ کے لیے پوچھیں: \"میچ کے نتائج\"۔"
            )
        return (
            f"The ledger has {_n(data['count'], 'row')} totalling {_m(data['total'], currency)}, dated {_d(data['period_start'])} to {_d(data['period_end'])}, "
            f"to {_n(data['parties'], 'party', 'parties')}:\n\n{body}\n\n"
            "The ledger is the client's own record, read by spreadsheet code; every row above was checked against the bank statement and the invoices. "
            "Ask \"match results\" for how each one reconciled."
        )

    if intent is AssistantIntent.SEARCH_DATE:
        day: date = data["day"]
        if data["granularity"] == "month":
            label = f"{_MONTHS_UR[day.month - 1]} {day.year}" if lang == "ur" else f"{_MONTHS_EN[day.month - 1]} {day.year}"
        else:
            label = day.isoformat()
        ledger, bank, invoices, decided = data["ledger"], data["bank"], data["invoices"], data["decided"]
        currency = data["currency"]
        if not ledger and not bank and not invoices and not decided:
            span = f"{_d(data['period_start'])} سے {_d(data['period_end'])} تک" if lang == "ur" else f"{_d(data['period_start'])} to {_d(data['period_end'])}"
            if lang == "ur":
                return f"اس کیس میں {label} کی کوئی چیز نہیں: نہ لیجر قطار، نہ بینک لائن، نہ انوائس، نہ فیصلہ۔ لیجر {span} ہے۔"
            return f"Nothing in this case is dated {label}: no ledger row, bank line, invoice, or decision. The ledger runs from {span}."
        parts = []
        if lang == "ur":
            parts.append(f"{label}: {len(ledger)} لیجر قطاریں مجموعی {_m(data['total'], currency)}، {len(bank)} بینک لائنیں، {len(invoices)} انوائسز اس تاریخ کی، {len(decided)} فیصلے۔")
            if ledger:
                parts.append("لیجر قطاریں:\n" + "\n".join(f"• {r['party']}، {_m(r['amount'], r['currency'])} ({r['review_item_id']}): {_status(r['status'], lang)}، فیصلہ {_decision(r['decision'], lang)}۔ {r['reason']}" for r in ledger))
            if bank:
                parts.append("بینک لائنیں:\n" + "\n".join(f"• {r['bank']['bank_row_id']}: {_m(r['bank']['amount'], r['bank']['currency'])}، \"{r['bank']['description']}\" (صفحہ {r['bank']['page'] or '-'}) → {r['review_item_id']} {r['party']}" for r in bank))
            if invoices:
                parts.append("انوائسز:\n" + "\n".join(f"• {r['invoice']['number']}: {_m(r['invoice']['amount'], r['invoice']['currency'])}، {r['invoice']['party']} → {r['review_item_id']}" for r in invoices))
            if decided:
                parts.append("فیصلے:\n" + "\n".join(f"• {r['review_item_id']}: {_decision(r['decision'], lang)}، {r['decided_by']} نے {r['decided_at']} پر" + (f"۔ وجہ: {r['rejection_reason']}" if r['rejection_reason'] else "") for r in decided))
            return "\n\n".join(parts)
        when = "In" if data["granularity"] == "month" else "On"
        parts.append(f"{when} {label}: {_n(len(ledger), 'ledger row')} totalling {_m(data['total'], currency)}, {_n(len(bank), 'bank line')}, {_n(len(invoices), 'invoice')} dated then, {_n(len(decided), 'decision')} taken.")
        if ledger:
            parts.append("Ledger rows:\n" + "\n".join(f"• {r['party']}, {_m(r['amount'], r['currency'])} ({r['review_item_id']}): {r['status']}, decision {r['decision']}. {r['reason']}" for r in ledger))
        if bank:
            parts.append("Bank lines:\n" + "\n".join(f"• {r['bank']['bank_row_id']}: {_m(r['bank']['amount'], r['bank']['currency'])}, \"{r['bank']['description']}\" (page {r['bank']['page'] or '-'}) → pays {r['review_item_id']} {r['party']}" for r in bank))
        if invoices:
            parts.append("Invoices:\n" + "\n".join(f"• {r['invoice']['number']}: {_m(r['invoice']['amount'], r['invoice']['currency'])}, {r['invoice']['party']} → settled by {r['review_item_id']}" for r in invoices))
        if decided:
            parts.append("Decisions:\n" + "\n".join(f"• {r['review_item_id']}: {r['decision']} by {r['decided_by']} at {r['decided_at']}" + (f". Reason: {r['rejection_reason']}" if r['rejection_reason'] else "") for r in decided))
        return "\n\n".join(parts)

    if intent is AssistantIntent.CASE_INFO:
        status = data["status"].replace("_", " ")
        currency = data["currency"]
        period = ""
        if data["period_start"] and data["period_end"]:
            derived = (" (لیجر قطاروں سے لیا گیا؛ کیس ریکارڈ میں مدت درج نہیں)" if lang == "ur" else " (taken from the ledger rows; the case record sets no period)") if data["period_derived"] else ""
            period = (f" مدت {_d(data['period_start'])} سے {_d(data['period_end'])} تک{derived}۔" if lang == "ur"
                      else f" Period {_d(data['period_start'])} to {_d(data['period_end'])}{derived}.")
        record = ""
        if data["documents"] is not None:
            docs = data["documents"]
            counts = ", ".join(f"{count} {kind.replace('_', ' ')}" for kind, count in sorted(docs.items())) or ("کوئی نہیں" if lang == "ur" else "none")
            record = (f" دستاویزات: {sum(docs.values())} ({counts})۔ رپورٹیں بنیں: {data['reports']}۔" if lang == "ur"
                      else f" Documents: {sum(docs.values())} ({counts}). Reports generated: {data['reports']}.")
        detail = f" ({data['status_detail']})" if data["status_detail"] else ""
        if lang == "ur":
            return (
                f"{data['client']}: کیس {data['case_id']}، حیثیت {status}{detail}۔ {_d(data['created'])} کو {data['created_by']} نے بنایا۔{period} "
                f"{data['items']} لیجر قطاریں، مجموعی {_m(data['total'], currency)}، {data['parties']} فریقوں کو: {data['matched']} مماثل، {data['partial']} جزوی، {data['unmatched']} غیر مماثل؛ "
                f"{data['approved']} منظور، {data['rejected']} مسترد، {data['pending']} زیر التوا؛ {data['flags']} نشانیاں۔{record}"
            )
        return (
            f"{data['client']}: case {data['case_id']}, status {status}{detail}. Created {_d(data['created'])} by {data['created_by']}.{period} "
            f"{_n(data['items'], 'ledger row')} totalling {_m(data['total'], currency)} across {_n(data['parties'], 'party', 'parties')}: "
            f"{data['matched']} matched, {data['partial']} partial, {data['unmatched']} unmatched; "
            f"{data['approved']} approved, {data['rejected']} rejected, {data['pending']} pending; {_n(data['flags'], 'flag')}.{record}"
        )

    if intent is AssistantIntent.CONFIDENCE:
        rows = data["rows"]
        if not rows and data["unreadable"] == 0:
            return (f"تمام {data['total']} آئٹمز زیادہ اعتماد سے پڑھے گئے، اور کوئی ماخذ قدر ناقابلِ مطالعہ نہیں تھی۔" if lang == "ur"
                    else f"Every one of the {data['total']} items was read with high confidence, and no source value was unreadable.")
        lines = []
        for row in rows:
            weakest = row["weakest"]
            if weakest is None:
                reading = "کوئی پڑھائی نہیں" if lang == "ur" else "no reading recorded"
            elif weakest["unreadable"]:
                reading = (f"{weakest['field']} ناقابلِ مطالعہ ({weakest['document_id']})" if lang == "ur"
                           else f"{weakest['field']} unreadable in {weakest['document_id']}")
            else:
                where = f"{weakest['document_id']}" + (f" page {weakest['page']}" if weakest["page"] else "")
                reading = (f"{weakest['field']} = {weakest['value']} ({_level(weakest['confidence'], lang)})، {where}" if lang == "ur"
                           else f"{weakest['field']} = {weakest['value']} ({weakest['confidence']}) from {where}")
            if lang == "ur":
                lines.append(f"• {row['party']}، {_m(row['amount'], row['currency'])}، {_d(row['date'])} ({row['review_item_id']}): {_level(row['confidence'], lang)} اعتماد؛ کمزور ترین پڑھائی: {reading}")
            else:
                lines.append(f"• {row['party']}, {_m(row['amount'], row['currency'])} on {_d(row['date'])} ({row['review_item_id']}): {row['confidence']} confidence; weakest reading: {reading}")
        body = ("\n".join(lines) + _more(data["more"], lang)) if lines else ""
        if lang == "ur":
            head = f"{data['total']} آئٹمز میں نکاسی کا اعتماد: {data['high']} زیادہ، {data['medium']} درمیانی، {data['low']} کم؛ {data['unreadable']} ماخذ قدریں ناقابلِ مطالعہ۔"
            middle = f"\n\nزیادہ اعتماد سے نیچے کے {len(rows)} آئٹم:\n\n{body}" if body else ""
            return (
                f"{head}{middle}\n\n"
                "اعتماد وژن ماڈل کا اپنا ہے، ہر قطار کے پیچھے کی کمزور ترین پڑھائی کے حساب سے؛ میچ کی مضبوطی الگ، متعین پیمانہ ہے۔ کم اعتماد صفحہ کھول کر دیکھنے کی وجہ ہے، فیصلہ نہیں۔"
            )
        head = f"Extraction confidence across {data['total']} items: {data['high']} high, {data['medium']} medium, {data['low']} low; {_n(data['unreadable'], 'source value')} unreadable."
        middle = f"\n\nThe {_n(len(rows), 'item')} below high confidence:\n\n{body}" if body else ""
        return (
            f"{head}{middle}\n\n"
            "Confidence is the vision model's own, rolled up as the weakest reading behind each row; match strength is a separate, deterministic score. "
            "A low-confidence reading is a reason to open the page, not a verdict."
        )

    if intent is AssistantIntent.UNMATCHED:
        rows = data["rows"]
        if not rows:
            return ("ہر لیجر اندراج کو بینک یا انوائس میں ہم منصب مل گیا۔" if lang == "ur"
                    else "Every ledger entry in this case found a bank or invoice counterpart.")
        if lang == "ur":
            return (
                f"{len(rows)} لیجر اندراج کو بینک اسٹیٹمنٹ یا انوائسز میں کچھ نہیں ملا (مجموعی {_m(data['total'], data['currency'])}):\n\n"
                f"{_list(rows, data['currency'], lang)}\n\n"
                "جس اندراج کے پیچھے نہ ادائیگی ہو نہ انوائس، وہ فرضی وینڈر کا کلاسک نمونہ ہے؛ پہلے اسی کا سراغ لگائیں۔"
            )
        return (
            f"{len(rows)} ledger {'entry' if len(rows) == 1 else 'entries'} matched nothing in the bank statement or invoices, totalling {_m(data['total'], data['currency'])}:\n\n"
            f"{_list(rows, data['currency'], lang)}\n\n"
            "An entry with no payment and no invoice behind it is the classic fictitious-vendor pattern, worth tracing first."
        )

    if intent is AssistantIntent.MISSING_EVIDENCE:
        rows = data["rows"]
        if not rows:
            return ("ہر قطار کے پیچھے آزاد ثبوت موجود ہے اور کوئی ماخذ قدر ناقابلِ مطالعہ نہیں۔" if lang == "ur"
                    else "Every row has independent evidence behind it, and no source value was unreadable.")
        lines = "\n".join(
            (f"• {row['party']}، {_m(row['amount'], row['currency'])}، {_d(row['date'])} ({row['review_item_id']}): {row['gap']}" if lang == "ur"
             else f"• {row['party']}, {_m(row['amount'], row['currency'])} on {_d(row['date'])} ({row['review_item_id']}): {row['gap']}")
            for row in rows
        )
        if lang == "ur":
            return (
                f"{len(rows)} قطاروں کے ثبوت میں کمی ہے: {data['no_counterpart']} کے پیچھے نہ بینک ادائیگی نہ انوائس، {data['invoice_only']} کے پاس انوائس تو ہے مگر بینک ادائیگی نہیں، اور {data['unreadable']} میں کوئی ماخذ قدر ناقابلِ مطالعہ تھی:\n\n{lines}\n\n"
                "کلائنٹ سے رسید، وینڈر کی تصدیق، یا واضح اسکین مانگیں؛ فیصلہ آپ کا ہے۔"
            )
        return (
            f"{len(rows)} rows are short of evidence: {data['no_counterpart']} with no bank payment and no invoice, {data['invoice_only']} with an invoice but no bank payment, and {data['unreadable']} with an unreadable value in the source:\n\n{lines}\n\n"
            "Ask the client for the receipt, a vendor confirmation, or a clearer scan; the decision on each stays yours."
        )

    if intent is AssistantIntent.FLAGS:
        if data["total_flags"] == 0:
            return ("اس کیس میں کوئی اصول نہیں چلا۔" if lang == "ur" else "No rule fired on this case.")
        rules = ", ".join(f"{rule} ({count})" for rule, count in data["rules"].items())
        top = _list(data["top"], "PKR", lang)
        if lang == "ur":
            return (
                f"{data['flagged_items']} آئٹمز پر {data['total_flags']} نشانیاں: {data['high']} زیادہ، {data['medium']} درمیانی، {data['low']} کم شدت۔ "
                f"چلنے والے اصول: {rules}۔ سب سے اہم:\n\n{top}\n\n{_DECIDE['ur']}"
            )
        return (
            f"{data['total_flags']} flags across {data['flagged_items']} items: {data['high']} high, {data['medium']} medium, {data['low']} low severity. "
            f"Rules that fired: {rules}. The most severe first:\n\n{top}\n\n{_DECIDE['en']}"
        )

    if intent is AssistantIntent.RULE:
        rule_id = data["rule_id"]
        description = RULE_DESCRIPTIONS.get(rule_id, {}).get(lang) or RULE_DESCRIPTIONS.get(rule_id, {}).get("en", rule_id)
        rows = data["rows"]
        if not rows:
            return (f"{description} اس کیس میں یہ اصول کسی آئٹم پر نہیں چلا۔" if lang == "ur"
                    else f"{description} In this case the {rule_id} rule did not fire on any item.")
        listed = _list(rows, "PKR", lang)
        if lang == "ur":
            return f"{description}\n\nاس کیس میں ({len(rows)} آئٹم):\n\n{listed}\n\n{_DECIDE['ur']}"
        return f"{description}\n\nIn this case ({len(rows)} item{'s' if len(rows) != 1 else ''}):\n\n{listed}\n\n{_DECIDE['en']}"

    if intent is AssistantIntent.DUPLICATES:
        rows = data["rows"]
        if not rows:
            return ("متعین اصولوں کو کوئی دوہری ادائیگی یا دوہری انوائس نہیں ملی۔" if lang == "ur"
                    else "The deterministic rules found no duplicate payment and no duplicate invoice.")
        if lang == "ur":
            return f"دوہری ادائیگیاں جو متعین اصولوں نے پکڑیں ({len(rows)} نشانیاں):\n\n{_list(rows, 'PKR', lang)}\n\n{_DECIDE['ur']}"
        return f"Duplicate payments found by the deterministic rules ({len(rows)} flag{'s' if len(rows) != 1 else ''}):\n\n{_list(rows, 'PKR', lang)}\n\n{_DECIDE['en']}"

    if intent is AssistantIntent.PARTY:
        rows = data["rows"]
        party = data["party"]
        if not rows:
            return (f"لیجر میں {party} کو کوئی ادائیگی درج نہیں۔" if lang == "ur"
                    else f"The ledger records no payment to {party}.")
        lines = []
        for row in rows:
            flags = (", ".join(row["flags"]) if row["flags"] else ("کوئی نشان نہیں" if lang == "ur" else "no flags"))
            if lang == "ur":
                lines.append(f"• {_m(row['amount'], row['currency'])}، {_d(row['date'])} ({row['review_item_id']}): {row['status']} ({row['strength']} مضبوطی)، فیصلہ {row['decision']}؛ نشانیاں: {flags}۔ {row['reason']}")
            else:
                lines.append(f"• {_m(row['amount'], row['currency'])} on {_d(row['date'])} ({row['review_item_id']}): {row['status']} ({row['strength']} strength), decision {row['decision']}; flags: {flags}. {row['reason']}")
        body = "\n".join(lines)
        if lang == "ur":
            return f"{party}: {len(rows)} ادائیگیاں، مجموعی {_m(data['total'], data['currency'])}۔\n\n{body}"
        return f"{party}: {len(rows)} payment{'s' if len(rows) != 1 else ''} totalling {_m(data['total'], data['currency'])}.\n\n{body}"

    if intent is AssistantIntent.TOTALS:
        if data["count"] == 0:
            return ("لیجر میں کوئی قطار نہیں۔" if lang == "ur" else "The ledger has no rows.")
        largest = data["largest"]
        if lang == "ur":
            return (
                f"لیجر کی {data['count']} قطاروں کا مجموعہ {_m(data['total'], data['currency'])} ہے، {_d(data['period_start'])} سے {_d(data['period_end'])} تک۔ "
                f"مماثل قطاریں {_m(data['matched_total'], data['currency'])}، جزوی {_m(data['partial_total'], data['currency'])}، غیر مماثل {_m(data['unmatched_total'], data['currency'])}۔ "
                f"سب سے بڑی قطار {_m(largest['amount'], largest['currency'])} {largest['party']} کو ({largest['review_item_id']})۔ "
                "یہ لیجر میں درج ادائیگیاں ہیں؛ لیجر آمدنی یا منافع درج نہیں کرتا۔"
            )
        return (
            f"The {data['count']} ledger rows total {_m(data['total'], data['currency'])}, from {_d(data['period_start'])} to {_d(data['period_end'])}. "
            f"Matched rows account for {_m(data['matched_total'], data['currency'])}, partial matches {_m(data['partial_total'], data['currency'])}, and unmatched rows {_m(data['unmatched_total'], data['currency'])}. "
            f"The largest single row is {_m(largest['amount'], largest['currency'])} to {largest['party']} ({largest['review_item_id']}). "
            "These are payments as recorded in the ledger; the ledger carries no income or profit figures."
        )

    if intent is AssistantIntent.TOP_VENDORS:
        rows = data["rows"]
        if not rows:
            return ("لیجر میں کوئی فریق نہیں۔" if lang == "ur" else "The ledger names no parties.")
        lines = "\n".join(
            (f"• {row['party']}: {_m(row['total'], data['currency'])}، {row['count']} ادائیگیاں، کل کا {row['share']:.1f}%" if lang == "ur"
             else f"• {row['party']}: {_m(row['total'], data['currency'])} over {row['count']} payment{'s' if row['count'] != 1 else ''}, {row['share']:.1f}% of the total")
            for row in rows
        )
        if lang == "ur":
            return f"{data['vendors']} فریقوں میں سے ادائیگی کے لحاظ سے سب سے بڑے (کل {_m(data['grand_total'], data['currency'])}):\n\n{lines}"
        return f"The largest parties by amount paid, out of {data['vendors']} (total {_m(data['grand_total'], data['currency'])}):\n\n{lines}"

    if intent is AssistantIntent.LARGEST:
        rows = data["rows"]
        if not rows:
            return ("لیجر میں کوئی قطار نہیں۔" if lang == "ur" else "The ledger has no rows.")
        lines = "\n".join(
            (f"• {_m(row['amount'], row['currency'])} {row['party']} کو، {_d(row['date'])} ({row['review_item_id']}): {row['status']}، فیصلہ {row['decision']}" if lang == "ur"
             else f"• {_m(row['amount'], row['currency'])} to {row['party']} on {_d(row['date'])} ({row['review_item_id']}): {row['status']}, decision {row['decision']}")
            for row in rows
        )
        if lang == "ur":
            return f"لیجر کی سب سے بڑی {len(rows)} ادائیگیاں:\n\n{lines}"
        return f"The {len(rows)} largest payments in the ledger:\n\n{lines}"

    if intent is AssistantIntent.COMPARE_MONTHS:
        rows = data["rows"]
        if not rows:
            return ("لیجر میں کوئی قطار نہیں۔" if lang == "ur" else "The ledger has no rows.")
        lines = []
        for row in rows:
            change = ""
            if row["change"] is not None:
                sign = "+" if row["change"] >= 0 else "-"
                change = (f"، پچھلے مہینے سے {sign}{_m(abs(row['change']), data['currency'])}" if lang == "ur"
                          else f", {sign}{_m(abs(row['change']), data['currency'])} on the month before")
            if lang == "ur":
                lines.append(f"• {row['month']}: {_m(row['total'], data['currency'])}، {row['count']} قطاریں، {row['unmatched']} غیر مماثل، {row['flagged']} نشان زدہ{change}")
            else:
                lines.append(f"• {row['month']}: {_m(row['total'], data['currency'])} over {row['count']} row{'s' if row['count'] != 1 else ''}, {row['unmatched']} unmatched, {row['flagged']} flagged{change}")
        body = "\n".join(lines)
        if len(rows) == 1:
            return ((f"اپ لوڈ شدہ لیجر صرف ایک مہینہ ({rows[0]['month']}) رکھتا ہے، اس لیے موازنہ ممکن نہیں:\n\n{body}") if lang == "ur"
                    else f"The uploaded ledger covers only one month ({rows[0]['month']}), so there is nothing to compare it against:\n\n{body}")
        return (f"مہینہ بہ مہینہ:\n\n{body}" if lang == "ur" else f"Month by month:\n\n{body}")

    if intent is AssistantIntent.SEARCH_AMOUNT:
        amount = _m(data["amount"], data["currency"])
        exact, near, bank = data["exact"], data["near"], data["bank"]
        if not exact and not near and not bank:
            return (f"لیجر یا بینک اسٹیٹمنٹ میں {amount} کی کوئی ادائیگی نہیں، نہ ہی 1% کے اندر کوئی رقم۔" if lang == "ur"
                    else f"No payment of {amount} appears in the ledger or the bank statement, and nothing within 1% of it.")
        parts = []
        if exact:
            parts.append((f"{amount} کی بالکل یہی رقم ({len(exact)}):\n{_list(exact, data['currency'], lang)}" if lang == "ur"
                          else f"Exactly {amount} ({len(exact)}):\n{_list(exact, data['currency'], lang)}"))
        if near:
            parts.append((f"1% کے اندر ({len(near)}):\n{_list(near, data['currency'], lang)}" if lang == "ur"
                          else f"Within 1% ({len(near)}):\n{_list(near, data['currency'], lang)}"))
        if bank:
            parts.append((f"بینک اسٹیٹمنٹ میں یہ رقم ان قطاروں پر ({len(bank)}):\n{_list(bank, data['currency'], lang)}" if lang == "ur"
                          else f"The bank statement shows that amount on these rows ({len(bank)}):\n{_list(bank, data['currency'], lang)}"))
        return "\n\n".join(parts)

    if intent is AssistantIntent.BENFORD:
        if not data.get("available"):
            return ("اس کیس کے لیے بینفورڈ تجزیہ ابھی نہیں ہوا۔" if lang == "ur"
                    else "Benford analysis has not been computed for this case yet.")
        verdict_en = ("the distribution deviates significantly, which is worth attention" if data["deviates"]
                      else "no significant deviation")
        verdict_ur = ("تقسیم نمایاں طور پر منحرف ہے، جو توجہ کے لائق ہے" if data["deviates"] else "کوئی نمایاں انحراف نہیں")
        caveat_en = " With a sample this small the test is indicative, not conclusive; it never decides anything on its own." if data["small_sample"] else " The test flags a pattern; it never decides anything on its own."
        caveat_ur = " اتنے چھوٹے نمونے پر یہ ٹیسٹ اشارہ ہے، حتمی نہیں؛ یہ خود کچھ طے نہیں کرتا۔" if data["small_sample"] else " یہ ٹیسٹ نمونہ دکھاتا ہے؛ خود کچھ طے نہیں کرتا۔"
        if lang == "ur":
            return (
                f"بینفورڈ قانون {data['sample_size']} رقموں کے پہلے ہندسوں کا ان کی فطری تقسیم سے موازنہ کرتا ہے۔ "
                f"کائی اسکوائر {data['chi_square']:.2f} ہے {data['degrees_of_freedom']} درجاتِ آزادی پر: {verdict_ur}۔ "
                f"توقع سے سب سے دور ہندسہ {data['worst_digit']} ہے (مشاہدہ {data['worst_observed'] * 100:.1f}% بمقابلہ متوقع {data['worst_expected'] * 100:.1f}%)۔{caveat_ur}"
            )
        return (
            f"Benford's law compares the first digits of the {data['sample_size']} amounts against their natural distribution. "
            f"Chi-square is {data['chi_square']:.2f} on {data['degrees_of_freedom']} degrees of freedom: {verdict_en}. "
            f"The digit furthest from expectation is {data['worst_digit']} (observed {data['worst_observed'] * 100:.1f}% vs expected {data['worst_expected'] * 100:.1f}%).{caveat_en}"
        )

    if intent is AssistantIntent.CASES:
        rows = data["rows"]
        if not rows:
            return ("اس تنظیم میں ابھی کوئی کیس نہیں۔" if lang == "ur"
                    else "Your organization holds no engagements yet.")
        lines = []
        for row in rows:
            active = (" (فعلی کیس)" if lang == "ur" else " (active case)") if row["active"] else ""
            if lang == "ur":
                lines.append(
                    f"• {row['client']} ({row['case_id']}){active}: {row['items']} آئٹم، {row['pending']} زیر التوا، "
                    f"{row['flags']} نشانیاں؛ {row['status']}، {row['created']} کو بنی"
                )
            else:
                lines.append(
                    f"• {row['client']} ({row['case_id']}){active}: {row['items']} items, {row['pending']} pending, "
                    f"{row['flags']} flags; {row['status']}, created {row['created']}"
                )
        body = "\n".join(lines)
        if lang == "ur":
            return (
                f"آپ کی تنظیم میں {data['count']} کیس ہیں:\n\n{body}\n\n"
                "فعلی کیس نشان زد ہے اور میرے باقی جوابات اسی کے بارے میں ہیں؛ ہیڈر سے کیس بدل کر کسی دوسرے میں جائیں۔"
            )
        return (
            f"Your organization holds {data['count']} engagement{'s' if data['count'] != 1 else ''}:\n\n{body}\n\n"
            "The active case is marked, and every other answer I give is about it. "
            "Switch cases from the header to work inside another engagement."
        )

    if intent is AssistantIntent.DOCUMENTS:
        rows = data["rows"]
        if not rows:
            return ("اس کیس میں ابھی کوئی دستاویز نہیں۔" if lang == "ur"
                    else "This case holds no documents yet.")
        lines = []
        for row in rows:
            review = ("؛ دو پاسوں میں اختلاف، انسانی نظر درکار" if lang == "ur"
                      else "; the two passes disagreed, needs human review") if row["needs_human_review"] else ""
            if row["extracted"]:
                if lang == "ur":
                    lines.append(f"• {row['filename']}: {row['type']}، {row['size']}؛ {row['model']} نے {row['pages']} صفحے پڑھے، {row['values']} قدر{review}")
                else:
                    lines.append(f"• {row['filename']}: {row['type']}, {row['size']}; read by {row['model']} over {row['pages']} page(s), {row['values']} values{review}")
            else:
                if lang == "ur":
                    lines.append(f"• {row['filename']}: {row['type']}، {row['size']}؛ ابھی نہیں پڑھی گئی")
                else:
                    lines.append(f"• {row['filename']}: {row['type']}, {row['size']}; not extracted yet")
        body = "\n".join(lines)
        if lang == "ur":
            return (
                f"اس کیس میں {data['count']} دستاویزات ہیں، جن میں سے {data['extracted']} نکاسی سلگھی ہے:\n\n{body}\n\n"
                "دستاویز اپ لوڈ کے وقت ایک بار پڑھی جاتی ہے۔ ماڈل کی پڑھی ہر قدر اپنا صفحہ اور اقتباس ساتھ رکھتی ہے۔ دستاویزات کی اسکرین پر دیکھیں۔"
            )
        return (
            f"This case holds {data['count']} document{'s' if data['count'] != 1 else ''}, {data['extracted']} of them read by the extraction pipeline:\n\n{body}\n\n"
            "Documents are read once, at upload. Every value the model produced keeps the page and snippet it came from. "
            "The Documents screen shows each one."
        )

    if intent is AssistantIntent.EXTRACTIONS:
        rows = data["rows"]
        if not rows:
            return ("اس کیس کے لیے ابھی کچھ بھی نہیں پڑھا گیا۔" if lang == "ur"
                    else "Nothing has been read from documents for this case yet.")
        lines = []
        for row in rows:
            if lang == "ur":
                lines.append(
                    f"• {row['filename']} ({row['type']}): {row['pages']} صفحوں سے {row['values']} قدر: "
                    f"{row['high']} زیادہ، {row['medium']} درمیانی، {row['low']} کم اعتماد، {row['unreadable']} ناقابلِ مطالعہ ({row['model']})"
                )
            else:
                lines.append(
                    f"• {row['filename']} ({row['type']}): {row['values']} values over {row['pages']} page(s): "
                    f"{row['high']} high, {row['medium']} medium, {row['low']} low confidence, {row['unreadable']} unreadable (read by {row['model']})"
                )
            for notable in row["notable"]:
                if notable["unreadable"]:
                    value = ("ناقابلِ مطالعہ" if lang == "ur" else "unreadable")
                else:
                    value = f"{notable['value']}"
                lines.append(f"  – {notable['field']}: {value} ({notable['confidence']})")
            if row["second_opinion"] == "disagrees":
                lines.append(("  – دوسری پاس سے اختلاف؛ انسانی نظر درکار" if lang == "ur"
                              else "  – the second pass disagrees; needs human review"))
        body = "\n".join(lines)
        if lang == "ur":
            return (
                f"ماڈل نے اس کیس کی دستاویزات سے کیا پڑھا:\n\n{body}\n\n"
                "ماڈل جو قدر نہ پڑھ سکے وہ ناقابلِ مطالعہ درج ہوتی ہے، کبھی گھڑی نہیں جاتی۔ ہر پڑھائی اپنا صفحہ اور اقتباس رکھتی ہے۔ نیچے کے حوالے اسی طرف لے جاتے ہیں۔"
            )
        return (
            f"What the model read from this case's documents:\n\n{body}\n\n"
            "A field the model could not read is recorded as unreadable, never guessed. "
            "Every reading keeps the page and snippet it came from; the citations below lead to them."
        )

    if intent is AssistantIntent.DECISIONS:
        rows = data["rows"]
        if data["decided"] == 0:
            return ("ابھی کوئی فیصلہ نہیں ہوا۔ ہر آئٹم انسانی فیصلے کا منتظر ہے۔ جائزہ اسکرین پر فیصلہ کریں۔" if lang == "ur"
                    else "Nothing has been decided yet: every item is still waiting for a human decision, taken on the Review screen.")
        lines = []
        for row in rows:
            reason = f". Reason: {row['rejection_reason']}" if row["rejection_reason"] else ""
            if lang == "ur":
                reason = f"۔ وجہ: {row['rejection_reason']}" if row["rejection_reason"] else ""
                lines.append(f"• {row['review_item_id']}: {row['party']}، {_m(row['amount'], row['currency'])}؛ {row['decision']}، {row['decided_by']} نے {row['decided_at']} پر{reason}")
            else:
                lines.append(f"• {row['review_item_id']}: {row['party']}, {_m(row['amount'], row['currency'])}; {row['decision']} by {row['decided_by']} at {row['decided_at']}{reason}")
        body = "\n".join(lines)
        if lang == "ur":
            return (
                f"اب تک {data['total']} میں سے {data['approved']} آئٹم منظور اور {data['rejected']} مسترد ہوئے؛ {data['pending']} ابھی زیر التوا ہیں:\n\n{body}\n\n"
                "ہر فیصلہ آڈیٹر کا اپنا ہے اور ٹریل میں درج ہے؛ اسسٹنٹ کبھی منظور یا مسترد نہیں کرتا۔"
            )
        return (
            f"So far {data['approved']} item{'s' if data['approved'] != 1 else ''} approved and {data['rejected']} rejected, out of {data['total']}; {data['pending']} still pending:\n\n{body}\n\n"
            "Every decision is the auditor's own and is recorded in the trail; the assistant never approves or rejects anything."
        )

    if intent is AssistantIntent.REPORTS:
        rows = data["rows"]
        if not rows:
            return ("اس کیس کے لیے ابھی کوئی رپورٹ نہیں بنی۔ جب آئٹمز کے فیصلے ہو جائیں تو رپورٹس اسکرین سے بنائیں۔ وہ ٹریل میں درج ہوتی ہے اور بعد میں نہیں بدلتی۔" if lang == "ur"
                    else "No report has been generated for this case yet. Once the items have their decisions, generate one from the Reports screen. It is recorded in the trail and never changes afterwards.")
        lines = []
        for row in rows:
            if lang == "ur":
                lines.append(
                    f"• {row['report_id']}، {row['generated_at']} کو {row['generated_by']} نے بنائی: {row['items']} آئٹم "
                    f"({row['approved']} منظور، {row['rejected']} مسترد، {row['pending']} زیر التوا)، {row['flags']} نشانیاں، {row['trail_records']} ٹریل اندراجات"
                )
            else:
                lines.append(
                    f"• {row['report_id']}, generated {row['generated_at']} by {row['generated_by']}: {row['items']} items "
                    f"({row['approved']} approved, {row['rejected']} rejected, {row['pending']} pending), {row['flags']} flags, {row['trail_records']} trail records"
                )
        body = "\n".join(lines)
        if lang == "ur":
            reports_word = "رپورٹ موجود ہے" if data["count"] == 1 else "رپورٹیں موجود ہیں"
            return (
                f"اس کیس کے لیے {data['count']} {reports_word}:\n\n{body}\n\n"
                "رپورٹیں صرف جمع ہونے والا ثبوت ہیں: دوبارہ بنانا نیا ریکارڈ بناتا ہے، اور پرانی فائل اپنے ہضم کے ساتھ ڈاؤن لوڈ قابل رہتی ہے۔"
            )
        return (
            f"{data['count']} report{'s' if data['count'] != 1 else ''} "
            f"{'exists' if data['count'] == 1 else 'exist'} for this case:\n\n{body}\n\n"
            "Reports are append-only evidence: regenerating creates a new record, and the old file stays downloadable with its digest."
        )

    if intent is AssistantIntent.HISTORY:
        rows = data["rows"]
        if data["total"] == 0:
            return ("اس کیس کا ٹریل خالی ہے۔" if lang == "ur" else "The trail for this case is empty.")
        lines = []
        for row in rows:
            detail = f": {row['detail']}" if row["detail"] else ""
            if lang == "ur":
                lines.append(f"• {row['when']}، {row['action']} ({row['actor']}){detail}")
            else:
                lines.append(f"• {row['when']}, {row['action']} by {row['actor']}{detail}")
        body = "\n".join(lines)
        if lang == "ur":
            return (
                f"اس کیس کے ٹریل میں {data['total']} اندراج ہیں۔ حال ہی کے:\n\n{body}\n\n"
                "ٹریل صرف جمع ہونے والا ہے: کوئی اندراج کسی کے ہاتھوں نہیں بدل سکتا، نہ مٹ سکتا، نہ آپ کے، نہ سسٹم کے۔"
            )
        return (
            f"The trail records {data['total']} event{'s' if data['total'] != 1 else ''} for this case. Most recent:\n\n{body}\n\n"
            "The trail is append-only: no entry can be edited or removed, by anyone, including this system."
        )

    if intent is AssistantIntent.CONCEPT:
        text = data["ur"] if lang == "ur" else data["en"]
        if not text:
            return _REFUSAL[lang]
        if lang == "ur":
            return (
                f"{text}\n\n"
                "یہ ترازو کی اپنی لغت سے ہے، کوڈ میں لکھی اور جانچی گئی، مشین سے تخلیق نہیں۔ "
                "اب اپنے کیس کے بارے میں پوچھیں، مثلاً \"کون سے آئٹم غیر مماثل ہیں؟\" یا \"اس کیس میں کیا ہوا؟\"، تاکہ یہ تصور اپنے ہی اعداد میں دکھے۔"
            )
        return (
            f"{text}\n\n"
            "That is from Tarazu's built-in glossary, written and reviewed in code, not generated. "
            "Ask about your own case next, for example \"which items are unmatched?\" or \"what happened in this case?\", "
            "to see the idea at work in your data."
        )

    return _REFUSAL[lang]
