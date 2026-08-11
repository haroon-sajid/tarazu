# modules/assistant/

**Purpose:** Grounded chat with the uploaded documents and plain-language
explanations of extractions, matches, and flags — in English and Urdu. Uses Qwen
models via direct API.

**Inputs:** User questions + the case's uploaded documents / extracted data /
match & flag results (`app/shared/` schemas).
**Outputs:** Answers and explanations, each with a confidence level and citations
to the source documents (document id, page). Writes chat events to the audit trail.

**Public interface:** `service.py` only — other modules import nothing else from here.

**Must NEVER do:**
- **Never answer from external/world knowledge — only from the case's uploaded documents and derived results. If the documents don't contain the answer, say so.**
- Never perform or restate math it computed itself — all numbers must come from `matching/` / `rules/` output or extracted data.
- Never approve, reject, or modify any item — it explains, humans decide.
- Never emit an answer without a confidence level.
- Never send client data anywhere except the configured Qwen API; never opt into provider-side training/retention.
