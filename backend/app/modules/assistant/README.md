# modules/assistant/

**Purpose:** Grounded chat with the uploaded documents and plain-language
explanations of extractions, matches, and flags, in both English and Urdu. Uses
Qwen models via their direct API.

**Inputs:** User questions plus the case's uploaded documents, extracted data,
and match and flag results (`app/shared/` schemas).

**Outputs:** Answers and explanations, each with a confidence level and
citations to the source documents (document id and page). Writes chat events to
the audit trail.

**Public interface:** `service.py` only. Other modules import nothing else from
this package.

**Must never do:**

- **Never answer from external or world knowledge.** Answers come only from the case's uploaded documents and derived results. If the documents do not contain the answer, say so.
- Never perform or restate math it computed itself. All numbers must come from `matching/` and `rules/` output or from extracted data.
- Never approve, reject, or modify any item. The assistant explains; humans decide.
- Never emit an answer without a confidence level.
- Never send client data anywhere except the configured Qwen API, and never opt into provider-side training or retention.
