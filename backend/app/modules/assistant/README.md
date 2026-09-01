# modules/assistant/

**Purpose:** Ask Tarazu: grounded answers about one case, in English and
Urdu, computed from the case's persisted results and worded with citations
and the computed facts shown. Anything the audit holds is answerable: the
results as a whole, one row, invoice, bank line, or flag by its identifier,
the evidence behind the rows, a day or a month, the case itself, and the
engagement's wider record. A Qwen model, when configured, may choose *which*
of the fixed queries runs for a question the keywords miss (under checks),
and may rephrase the wording, nothing else. See ADR 0006.

**Inputs:** The question, the case, its review items, its Benford result,
and a `WorkspaceContext` carrying every case, document, extraction, decision,
report, and audit-trail record in the organization (`app/shared/` schemas).
Never the documents themselves.

**Outputs:** An `AssistantAnswer`: text, `answer_confidence`, `grounded`,
citations into the documents behind the items involved, the `facts` the text
was written from, the `intent`, and `composed_by`. The route appends both the
question and the answer to the audit trail.

**Public interface:** `service.py` only. Other modules import nothing else from
this package.

## Layout

| File | Role |
|---|---|
| `service.py` | `answer_question(...)`: runs the five steps below. |
| `planner.py` | Step 1–2: deterministic keyword routing (EN/UR) to an intent and its parameters: a rule, a party, an amount, an identifier (`RI-0005`, `invoice 0087`, `row 16`), a day or month. Unplaceable questions are refused, in words that say whether they read as being about the audit. |
| `classifier.py` | Step 1b, only with a model: for a question the keywords could not place, asks the model *which* fixed query it is asking for. Every parameter it names is checked against the question and the case (a party the ledger names; an amount, date, or identifier written in the question); a reply that fails leaves the question refused. Never answers. |
| `queries.py` | Step 3: the deterministic queries: `Decimal` counts, sums, groupings by party and month, amount and date search, one item's full detail, the invoices and bank lines, every row, confidence readout, Benford readout, the case record. Produces the facts. |
| `composer.py` | Step 4: templates in both languages over the computed values. Works with no model. |
| `qwen_chat.py` | The optional text-only client used by the classifier and to rephrase the template. Owned here, not shared with `extraction/`. |
| `concepts.py` | Beginner glossary: 15 audit topics with EN/UR definitions, keyword vocabularies, and `DEDICATED_TOPICS`. Shared verbatim with the frontend fixture router. |
| `settings.py` | `ASSISTANT_*` configuration. |

## The pipeline

1. Understand the intent, by keywords; when they fail and a key is set,
the classifier may choose the query, and the answer then carries the fact
`Question understood by: <model>` with its confidence one step lower.
2. Plan the query. 3. Run the calculation in code. 4. Word the result, and,
if a key is set and `DEMO_MODE` is off, ask the model to rephrase it given
the facts, then **check** that every number in the reply already appears in
the facts or the template; otherwise the template stands. 5. Show the sources.

Question types today. The results: summary, match results (all, or one
status), unmatched items, missing evidence, flags, one rule explained,
duplicates, Benford, extraction confidence; the data: one item by any
identifier it carries (review item, ledger row or sheet row, bank line,
invoice number, flag, document), the invoices, the bank statement lines,
every ledger row, a party by name, a day or month, an amount, totals, top
vendors, largest payments, month comparison; the record: the case itself,
cases, documents, extractions, decisions, reports, history; and the concept
glossary and help. "Can I ask…?" is answered yes, with the shapes that work.
Sales, revenue, income, and profit are declined with the reason: the ledger
records payments only.

## Configuration

| Variable | Meaning |
|---|---|
| `ASSISTANT_QWEN_API_KEY` (or `DASHSCOPE_API_KEY`) | Enables model phrasing. Without it every answer is the template. |
| `ASSISTANT_QWEN_MODEL` | Default `qwen-plus`. |
| `ASSISTANT_QWEN_API_BASE_URL` | Model Studio, OpenAI-compatible mode. |
| `ASSISTANT_MODEL_PHRASING` | `false` keeps the template even with a key. |
| `ASSISTANT_REQUEST_TIMEOUT_SECONDS` | Default 30. |
| `DEMO_MODE` | `true` never calls the model. |

**Must never do:**

- **Never answer from external or world knowledge.** Answers come only from the case's persisted results. If the data does not contain the answer, say so.
- **Never let the model compute.** The model receives the question, the computed facts, and the template (never a document) and may only rephrase. A reply that introduces a number is discarded.
- **Never let the model answer by choosing.** The classifier may pick which fixed query runs; it cannot name a party the ledger lacks, or an amount, date, or identifier the question does not contain. Anything it names is checked, and a failed check is a refusal.
- Never approve, reject, or modify any item. The assistant explains; humans decide.
- Never emit an answer without `answer_confidence`, and never cite a document on an answer that is not grounded (the schema refuses it).
- Never send client data anywhere except the configured Qwen API, and never opt into provider-side training or retention.
