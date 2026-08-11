# modules/extraction/

**Purpose:** Reads uploaded documents (bank statement PDFs, invoice PDFs/images,
ledger Excel/CSV) using Qwen VL via Alibaba Model Studio. Produces structured data
with per-field confidence scores (high/medium/low) and runs an AI second-opinion
check to cross-validate low-confidence extractions.

**Inputs:** Document references (Supabase Storage paths).
**Outputs:** Structured extraction results (`app/shared/` schemas) where EVERY
value carries: value + confidence level + source provenance (document id, page,
region). Writes extraction events to the immutable audit trail.

**Public interface:** `service.py` only — other modules import nothing else from here.

**Must NEVER do:**
- Never perform matching, reconciliation, or any cross-document math — extraction only. Computation belongs to `matching/`.
- Never emit a value without confidence level and source provenance.
- Never silently overwrite or "correct" extracted values after human review has started.
- Never send client documents to any endpoint other than the configured Qwen API, and never opt into provider-side training/retention.
- Never fabricate values for unreadable fields — return low confidence / unreadable instead.
