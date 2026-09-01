# modules/extraction/

**Purpose:** Reads uploaded documents (bank statement PDFs, invoice PDFs and
images, ledger Excel and CSV files). Documents go to Qwen VL via Alibaba Model
Studio and come back as structured data with per-field confidence and source
provenance; the ledger goes to pandas and never touches a model. Low-confidence
fields get a verification pass that reports agreement and never resolves it.

**Inputs:** Document references (Supabase Storage paths) or raw bytes.

**Outputs:** Structured extraction results (`app/shared/` schemas) in which
every value carries the value itself, a confidence level, and source provenance
(document id, page, region). Writes extraction events to the immutable audit
trail.

**Public interface:** `service.py` only. Other modules import nothing else from
this package.

## Layout

| File | Role |
|---|---|
| `service.py` | The public interface. Everything below is an implementation detail. |
| `page_images.py` | PDF → PNG pages with PyMuPDF. No poppler on the deploy box. |
| `qwen_client.py` | HTTP to Model Studio: retries, backoff, JSON parsing. |
| `prompts.py` | The prompts and the JSON shapes the model must answer in. |
| `ledger_reader.py` | pandas → `LedgerEntry`. **Imports no AI client.** |
| `demo_mode.py` | `DEMO_MODE`: replay cached results instead of calling Qwen. |
| `settings.py` | Module config from the environment. |

## The public functions

```python
pdf_to_page_images(content, dpi=200)            -> list[PageImage]
extract_page(image, document_id, ...)           -> list[ExtractedField]
verify_page(image, fields, ...)                 -> VerificationOutcome
read_ledger(document_id, filename, content)     -> list[LedgerEntry]
extract_document(document_id, type, name, data) -> ExtractionResult
```

`extract_document` is the normal entry point. `read_ledger` is a **separate**
entry point on purpose: `extract_document` raises if handed a ledger, so the
spreadsheet path cannot drift into the model path by accident.

## Two paths, and why they are separate

**Documents go to Qwen VL.** A bank statement PDF or a photo of an invoice needs
a model. Every field comes back with `extraction_confidence` and a `Provenance`
naming the page and the region; that provenance is what the evidence viewer
highlights, and a field without it is dropped rather than emitted.

**The ledger goes to pandas.** An Excel file is already structured. Sending it to
a vision model would add cost, latency, and a chance of misreading a number
sitting in a cell. `ledger_reader.py` imports pandas and the shared schemas and
nothing else; its provenance is the spreadsheet row.

## The verifier is a checker, not a second guesser

`verify_page` is shown the image **and** the first reading, and asked whether
they match. Two design choices make the escalation guarantee real rather than
aspirational:

- It reports agreement per field and stops. `VerificationOutcome` has no field
  in which a winner could be recorded.
- `VerificationOutcome` **fails validation** if a monetary field disagrees and
  `needs_human_review` is not `True`. The escalation cannot be forgotten or
  switched off from calling code.

It runs only on fields at or below `EXTRACTION_CONFIDENCE_THRESHOLD`
(default `low`), because verification doubles a page's token cost.

## Failure behaviour

| Situation | What happens |
|---|---|
| Timeout, 429, or 5xx | Retried with exponential backoff, honouring `Retry-After` |
| 401, 403, 422 | Raised immediately; retrying will not fix a bad key |
| Unparseable JSON | One repair round-trip, then `QwenResponseError` |
| Unusable or missing bbox | Falls back to page + `text_snippet` |
| No provenance at all | The field is dropped, not emitted |
| Unrecognised confidence word | Treated as `low`; "unknown" must never read as "high" |
| Model reports a value it could not read | Forced to `unreadable=True`, `value=None` |

## Must never do

- Never perform matching, reconciliation, or any cross-document math. This module extracts only; computation belongs to `matching/`.
- Never emit a value without a confidence level and source provenance.
- Never silently overwrite or "correct" extracted values after human review has started.
- Never send client documents to any endpoint other than the configured Qwen API, and never opt into provider-side training or retention.
- Never fabricate values for unreadable fields. Return low confidence or mark the field unreadable instead.
- Never let the verifier pick a winner between two readings. Disagreement escalates to a human, always.
