"""The prompts and the JSON shapes Qwen VL must answer in.

Kept in one file because these are the part of the module most likely to be
tuned against real documents, and tuning them should not mean touching the
client or the service.
"""

from __future__ import annotations

import json

__all__ = [
    "EXTRACTION_FIELDS",
    "EXTRACTION_SCHEMA",
    "STATEMENT_FIELDS",
    "STATEMENT_SCHEMA",
    "VERIFICATION_SCHEMA",
    "extraction_messages",
    "repair_messages",
    "statement_messages",
    "verification_messages",
]

#: The fields we ask for on an invoice or a statement line.
EXTRACTION_FIELDS = ("date", "amount", "party_name", "invoice_number")

#: The columns of one bank-statement transaction.
STATEMENT_FIELDS = ("date", "amount", "description", "balance")

EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["fields"],
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "field",
                    "value",
                    "extraction_confidence",
                    "bbox",
                    "text_snippet",
                    "unreadable",
                ],
                "properties": {
                    "field": {"type": "string", "enum": list(EXTRACTION_FIELDS)},
                    "value": {"type": ["string", "number", "null"]},
                    "extraction_confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "bbox": {
                        "type": ["array", "null"],
                        "items": {"type": "number"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                    "text_snippet": {"type": ["string", "null"]},
                    "unreadable": {"type": "boolean"},
                },
            },
        }
    },
}

#: A bank statement is a table, not a form: one page holds many transactions,
#: so it is read row by row rather than as a set of document-level values.
STATEMENT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["transactions"],
    "properties": {
        "transactions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "date",
                    "amount",
                    "description",
                    "balance",
                    "extraction_confidence",
                    "bbox",
                    "text_snippet",
                ],
                "properties": {
                    "date": {"type": ["string", "null"]},
                    "amount": {"type": ["string", "number", "null"]},
                    "description": {"type": ["string", "null"]},
                    "balance": {"type": ["string", "number", "null"]},
                    "extraction_confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "bbox": {
                        "type": ["array", "null"],
                        "items": {"type": "number"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                    "text_snippet": {"type": ["string", "null"]},
                },
            },
        }
    },
}

VERIFICATION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["checks"],
    "properties": {
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["field", "agrees", "reading"],
                "properties": {
                    "field": {"type": "string"},
                    "agrees": {"type": "boolean"},
                    "reading": {"type": ["string", "number", "null"]},
                },
            },
        }
    },
}

_EXTRACTION_SYSTEM = """\
You are a document reader for an audit tool. You read financial documents and \
report exactly what is printed on them.

Rules you must follow:
- Report only what you can see. Never infer, complete, or guess a value from \
context or from what a document of this kind usually contains.
- If a field is absent or unreadable, set "unreadable": true and "value": null. \
Never invent a placeholder.
- Do not do arithmetic. Do not total, convert, or reconcile anything. Report \
figures exactly as printed.
- For every field, give the source location as "bbox": [x0, y0, x1, y1], \
normalised to the range 0 to 1, with the origin at the TOP-LEFT of the page \
image. x is horizontal, y is vertical.
- Also give "text_snippet": the characters you actually read, verbatim, \
including any separators and currency marks. If you cannot give a bbox, the \
snippet is required.
- "extraction_confidence" is your own certainty that you READ the characters \
correctly. Use "low" freely for blurred, skewed, handwritten, or cropped text. \
Under-confidence is cheap; over-confidence is not.

Answer with JSON only. No prose, no markdown fences.
"""

_VERIFICATION_SYSTEM = """\
You are checking another reader's work against the same document image.

For each field you are given, look at the image and decide whether the value \
you are shown matches what is printed. Report:
- "agrees": true if the printed value matches what you were shown, false if it \
does not.
- "reading": what YOU read for that field, exactly as printed.

Rules:
- Judge only against the image. Do not reason about which value is more \
plausible, more likely, or better formed.
- Do not resolve a conflict, do not pick a winner, and do not suggest one. \
Report what you see and stop.
- If you cannot read the field at all, set "agrees": false and "reading": null.

Answer with JSON only. No prose, no markdown fences.
"""


def _user_content(data_url: str, text: str) -> list[dict]:
    return [
        {"type": "image_url", "image_url": {"url": data_url}},
        {"type": "text", "text": text},
    ]


def extraction_messages(data_url: str, page: int, page_count: int) -> list[dict]:
    """The first-pass extraction request for one page image."""
    instruction = (
        f"This is page {page} of {page_count} of a financial document.\n\n"
        f"Extract these fields: {', '.join(EXTRACTION_FIELDS)}.\n\n"
        "Return one entry per field, even for fields you cannot read (with "
        '"unreadable": true).\n\n'
        "Respond with JSON matching exactly this schema:\n"
        f"{json.dumps(EXTRACTION_SCHEMA, indent=2)}"
    )
    return [
        {"role": "system", "content": _EXTRACTION_SYSTEM},
        {"role": "user", "content": _user_content(data_url, instruction)},
    ]


def statement_messages(data_url: str, page: int, page_count: int) -> list[dict]:
    """Read one bank-statement page as a table of transactions."""
    instruction = (
        f"This is page {page} of {page_count} of a bank statement.\n\n"
        "Read every transaction row in the table, top to bottom, in the order "
        "they appear. One entry per row. Do not merge rows, do not skip rows, "
        "and do not include the opening or closing balance summary lines as "
        "transactions.\n\n"
        "For each row give the date, the transaction amount as printed, the "
        "description or narration, and the running balance if the statement "
        "shows one. Use null for anything the row does not have.\n\n"
        "The bbox and text_snippet locate the row's AMOUNT, which is the value "
        "an auditor will want to see highlighted.\n\n"
        "Respond with JSON matching exactly this schema:\n"
        f"{json.dumps(STATEMENT_SCHEMA, indent=2)}"
    )
    return [
        {"role": "system", "content": _EXTRACTION_SYSTEM},
        {"role": "user", "content": _user_content(data_url, instruction)},
    ]


def repair_messages(previous: list[dict], bad_output: str, error: str) -> list[dict]:
    """Follow-up that asks the model to fix output we could not parse.

    Sent once. If the repair also fails to parse, the page is reported as a
    failure rather than retried forever.
    """
    return [
        *previous,
        {"role": "assistant", "content": bad_output},
        {
            "role": "user",
            "content": (
                f"That response could not be parsed: {error}\n\n"
                "Reply again with the same findings as raw JSON only. No prose, "
                "no markdown fences, no trailing commas. Every required key must "
                "be present."
            ),
        },
    ]


def verification_messages(data_url: str, fields: list[dict]) -> list[dict]:
    """The verification request: the image plus the readings to check."""
    listing = "\n".join(
        f"- {entry['field']}: {entry['value']!r}"
        + (f"  (read as {entry['text_snippet']!r})" if entry.get("text_snippet") else "")
        for entry in fields
    )
    instruction = (
        "Another reader reported these values from this image:\n\n"
        f"{listing}\n\n"
        "Check each one against the image.\n\n"
        "Respond with JSON matching exactly this schema:\n"
        f"{json.dumps(VERIFICATION_SCHEMA, indent=2)}"
    )
    return [
        {"role": "system", "content": _VERIFICATION_SYSTEM},
        {"role": "user", "content": _user_content(data_url, instruction)},
    ]
