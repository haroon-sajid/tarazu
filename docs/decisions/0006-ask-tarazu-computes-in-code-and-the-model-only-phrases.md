# 6. Ask Tarazu computes in code; the model only phrases

Date: 2026-08-29

Status: Accepted — implemented in `backend/app/modules/assistant/`.
Amended 2026-08-31: the model-assisted intent classifier anticipated below
is implemented (`classifier.py`), under the checks described in the
amendment at the end.

## Context

Reliability rule 7 says the assistant answers only from the uploaded
documents; rule 2 says no model may produce or influence a numeric result.
The obvious way to build a chat assistant — hand the model the case data and
let it answer — breaks both: the model can misread, mis-add, or invent, and
there is no way to show a reader which of its sentences rest on which figures.

The hackathon build kept the assistant honest by composing answers in the
browser from the review items, with no model at all. That proved the posture
but could not be recorded in the audit trail, could not be reached by an API
key, and could not be extended with a model without re-deciding the question
of what the model is allowed to do.

See [docs/product-plan.md](../product-plan.md), section 6.

## Decision

**Every answer is produced by a five-step pipeline in which the model, if
used at all, touches only the wording.**

1. **Intent** — `planner.plan`: deterministic keyword routing, English and
   Urdu. A question the planner cannot place is refused, not guessed.
2. **Plan** — the intent names exactly one deterministic query.
3. **Compute** — `queries.execute`: Python `Decimal` over the persisted review
   items and the stored Benford result. Counts, sums, groupings by party and
   month, amount search. The result carries the structured values *and* a
   list of `AssistantFact`s (label, value) the answer will be written from.
4. **Compose** — `composer.compose`: templates in the answer's language, over
   the computed values. This is the floor: it works with no model and no
   network. When a Qwen key is configured and `DEMO_MODE` is off, the model is
   asked to rephrase the template given the facts, under instructions to add
   no number and compute nothing — and its reply is **checked**: every number
   in it must already appear in the facts or the template, or the template
   stands. The answer records what worded it (`composed_by`).
5. **Sources** — citations into the documents behind the items involved, and
   the facts, shown beside the answer so a reader can check prose against
   arithmetic.

Structurally: `AssistantAnswer` carries `answer_confidence` (never a field
called `confidence`, which the schema tests reserve), `grounded`, `citations`
(which the schema refuses on an ungrounded answer), `facts`, `intent`, and
`composed_by`. Both the question and the answer are appended to the audit
trail as `assistant_question_asked` and `assistant_answered`, the latter
attributed to the deterministic composer or to the model that phrased it.

The model never receives a document. It receives the question, the facts,
and the template.

## Consequences

- The assistant is testable as arithmetic: every test asserts exact figures
  from the sample case, and one proves the number guard discards a model
  reply that introduced a figure.
- A question the ledger cannot answer — sales, profit, income — is declined
  with the reason ("the uploaded ledger records payments only") rather than
  answered from world knowledge. Those become answerable when the normalized
  transactions table of ADR 0005 carries direction.
- Adding a question type means adding a query function and a template, not
  a prompt. Adding a language means adding templates.
- A model-assisted intent classifier can be added later for questions the
  keywords miss, under the same rule: it may choose *which* query runs, never
  what the answer says. (Done — see the amendment.)
- Cost is bounded: with no key the assistant makes no network calls at all;
  with a key, one small text call per answer to phrase it, plus one to
  choose the query for a question the keywords could not place — and no
  phrasing call for a refusal.

## Alternatives considered

- **Retrieval-augmented generation over the documents.** Rejected: the model
  would read numbers from page images and add them; rule 2 forbids exactly
  that, and provenance for a generated sentence cannot be shown.
- **The model writes SQL over the case.** Rejected for now: it moves
  computation into code the model authored per request, which is neither
  deterministic nor reviewable. The planner's fixed set of queries is.
- **Keep the frontend composer.** Rejected: it could not be logged, keyed,
  or shared with the Business view, and every new screen would need its own.

## Amendment (2026-08-31): the model may choose the query

The first release refused every question its keywords could not place —
including "can I ask you one specific invoice match result?", which names two
things the case holds. Two changes, both inside the decision above:

1. **The planner answers from the data, not only about it.** New fixed
   queries: the match results row by row (`matches`), one row, invoice, bank
   line, or flag by any identifier it carries (`item`), the invoices and the
   bank statement lines (`invoices`, `bank`), every ledger row (`ledger`), a
   day or month (`search_date`), extraction confidence per row
   (`confidence`), and the case record (`case_info`). A "may I ask…?"
   question is answered yes, with the shapes that work; a question that uses
   the audit's own words but names no query is refused in words that say so.
2. **The classifier.** When the keywords fail and a key is configured, the
   model is shown the question, the list of query names, the ledger's party
   names, the rule ids, and the glossary topics, and asked for one JSON
   object naming a query and its parameters. Its reply is checked: the intent
   must be one of the fixed set; a party must be one the ledger names; an
   amount, date, or identifier must be written in the question; a rule id or
   topic must be one the module ships. A failed check is a refusal. The
   chosen plan runs the same deterministic query as a keyword-placed one; the
   answer carries the fact `Question understood by: <model>` and a confidence
   one step lower, so the interpretation is visible. The model never sees a
   document and never words the answer at that step.

Rule 7 is unchanged: an answer still comes only from the case's persisted
results. What changed is how many questions reach them.
