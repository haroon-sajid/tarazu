# modules/extraction/

**Purpose:** Reads uploaded documents (bank statement PDFs, invoice PDFs and
images, ledger Excel and CSV files) using Qwen VL via Alibaba Model Studio.
Produces structured data with per-field confidence scores (high, medium, or
low) and runs an AI second-opinion check to cross-validate low-confidence
extractions.

**Inputs:** Document references (Supabase Storage paths).

**Outputs:** Structured extraction results (`app/shared/` schemas) in which
every value carries the value itself, a confidence level, and source provenance
(document id, page, region). Writes extraction events to the immutable audit
trail.

**Public interface:** `service.py` only. Other modules import nothing else from
this package.

**Must never do:**

- Never perform matching, reconciliation, or any cross-document math. This module extracts only; computation belongs to `matching/`.
- Never emit a value without a confidence level and source provenance.
- Never silently overwrite or "correct" extracted values after human review has started.
- Never send client documents to any endpoint other than the configured Qwen API, and never opt into provider-side training or retention.
- Never fabricate values for unreadable fields. Return low confidence or mark the field unreadable instead.
