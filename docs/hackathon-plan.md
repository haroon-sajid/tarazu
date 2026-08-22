# Tarazu — AI Audit Assistant: Hackathon Build Plan

**Team:** Lead (Haroon) · Dev-D (deterministic backend) · Dev-F (frontend)

This document supersedes the first draft plan. Read it with [CLAUDE.md](../CLAUDE.md)
open — the 7 reliability rules and the module rules are not negotiable, including
under time pressure.

The plan is a sequence of six steps. Each step has **exit criteria**: do not start
the next step until the current one passes them. The steps are ordered by
dependency, not by calendar.

---

## 0. Before anything else: verify these yourself

The hackathon facts in the original plan came from the team's own research, not
from an independent check. **Lead: spend twenty minutes on the official portal
and confirm each line, then tick it here.** Getting one of these wrong costs the
whole build.

| Fact to confirm | Status |
|---|---|
| Submission deadline — date **and** time, in PKT | ☐ |
| Track list and each track's written description | ☐ |
| Required deliverables (video length, repo, licence, diagram, description) | ☐ |
| Is *hosting* on Alibaba Cloud required, or is using Model Studio enough? | ☐ |
| Live round format — demo? pitch? Q&A? how long? | ☐ |
| Team size limit and registration cut-off | ☐ |

**Why this is item zero:** the biggest single unknown is whether the backend must
be *hosted* on Alibaba Cloud or whether calling Qwen via Model Studio satisfies
the requirement. That answer changes a meaningful chunk of work (see §1.7).

---

## 1. Verdict on the original plan

**The shape is right. The sequencing will hurt you.**

What the draft gets right, keep it: the pandas-is-correct call, the "small tool
that works perfectly" rule, the human-in-the-loop framing, the feature cut-list,
the per-person prompt packs, and the decision to plant deliberate errors in the
sample data. Those are good instincts.

Nine things need to change. Ranked by how much damage they do if ignored.

### 1.1 The repo has no runnable code — the first step is bigger than the plan admits

The draft opens with cloud setup plus Qwen extraction. But the current repo is
scaffolding and documentation only:

- [backend/app/main.py](../backend/app/main.py) is a docstring — there is no `app = FastAPI()`.
- [backend/app/shared/](../backend/app/shared/) contains a README and **zero schema files**.
- Every `service.py` is an empty docstring.
- There is no `requirements.txt`, no `pyproject.toml`, and no `__init__.py` anywhere.
- `frontend/` is a README. There is no Next.js app, no `package.json`.
- There is no `LICENSE` file — and the hackathon requires an open-source licence.
- [docker-compose.yml](../docker-compose.yml) is commented out entirely.

None of that is a problem — the scaffold is unusually well thought through and it
will pay for itself throughout. But "make the thing boot" is real work the draft
does not budget for.

### 1.2 Contract-first, or two people sit idle

This is the most important change in this document.

The draft has Dev-F building static UI until integration and Dev-D waiting on the
Lead's extraction output. That is a large block of wasted parallelism per person.

**Fix: before writing any feature code, the Lead freezes the data contracts.**

1. Write the Pydantic schemas into `backend/app/shared/` — `ExtractedField`,
   `Provenance`, `Confidence`, `LedgerEntry`, `BankTransaction`, `Invoice`,
   `MatchResult`, `Flag`, `AuditRecord`, `ReviewItem`.
2. Fill in [docs/api-contracts.md](api-contracts.md) with the five endpoints and their exact
   request/response JSON.
3. Commit `sample-data/fixtures/review-items.json`, `dashboard.json`, and
   `extraction-result.json` — realistic, hand-written fake responses.

After that commit: Dev-F builds the entire UI against the fixtures and is never
blocked. Dev-D writes matching against the fixture shapes and is never blocked.
Integration becomes "swap the fixture URL for the real one" instead of "discover
our shapes don't line up."

**Standing rule: if the contract changes, it changes in `app/shared/` and
`docs/api-contracts.md` in the same commit, and it gets announced in team chat.**
CLAUDE.md already requires this.

### 1.3 `run_matching_and_rules()` breaks the module boundary

The draft asks Dev-D for a single function spanning both modules, and asks them
to wrap it in FastAPI themselves. Both violate CLAUDE.md.

`matching/` and `rules/` are separate bounded modules. Each exposes exactly one
public interface file, `service.py`, and neither owns HTTP routing.

```python
# backend/app/modules/matching/service.py
def run_matching(ledger, bank, invoices) -> list[MatchResult]: ...

# backend/app/modules/rules/service.py
def evaluate_flags(ledger, matches, config) -> list[Flag]: ...
```

The Lead orchestrates both from the route layer. Dev-D writes **pure functions
that take and return `app/shared/` objects and nothing else** — no FastAPI, no
Supabase, no file I/O. That is easier for a beginner, trivially unit-testable,
and it is the boundary that lets you claim "microservice-extractable" to judges
with a straight face.

### 1.4 The extraction prompt drops provenance — which kills your best feature

The draft's Qwen prompt is *"Extract date, amount, party_name, invoice_number…
return JSON."* That output has no source location, which:

- violates **Rule 3** (every extracted number traceable to document, page, and location), and
- makes the side-by-side evidence viewer — the feature the draft itself calls the
  standout — impossible to build, because there is nothing to highlight.

Every extracted field must come back as a value **plus** its provenance:

```json
{
  "field": "amount",
  "value": 49500.00,
  "confidence": "high",
  "source": {
    "document_id": "inv-0007",
    "page": 1,
    "bbox": [0.62, 0.41, 0.88, 0.46]
  }
}
```

Ask Qwen VL for normalised `[x0, y0, x1, y1]` coordinates in 0–1 space. Vision
models are imperfect at bounding boxes — if the boxes come back unusable, fall
back to **page-level provenance plus a text snippet**, and have the viewer
highlight the matching text on the rendered page. Settle this in Step 1, not
halfway through the build.

### 1.5 "Confidence" means two different things — name them apart

The draft uses one word for two unrelated concepts, and this will bite you in the
judges' Q&A:

- **Extraction confidence** — how sure the AI is that it read the number correctly. Required by Rule 4.
- **Match strength** — how well a ledger row lines up with a bank row. Computed by deterministic pandas.

If both are labelled "confidence," it looks like the AI is scoring your matches,
which contradicts **Rule 2** — your central claim. Name them
`extraction_confidence` and `match_strength` in the schemas, the UI, and the
pitch. Then the sentence "no AI value has ever touched the match score" is
verifiable in the code, on stage.

### 1.6 An append-only function is not an append-only table

"Write a function that only inserts" is not immutability — it is a convention any
future line of code can break. Enforce it in Postgres:

```sql
revoke update, delete on public.audit_trail from anon, authenticated, service_role;
-- plus an RLS policy allowing insert + select only
```

Ten minutes of work, and it turns Rule 5 from a claim into a demonstrable fact.
**Put that SQL on a slide.** "We didn't just promise the trail is immutable, we
revoked the permission" is exactly the kind of detail that separates a demo from
a product.

### 1.7 Deploying last is how teams miss submissions

Deployment always breaks, and Alibaba Cloud account verification (identity,
payment method, sometimes a manual review) can take a long time on a new
international account. Two changes:

- **Start the Alibaba Cloud account verification as the very first action of
  Step 1.** It runs in the background while you code. If it stalls, you find out
  early, when you still have options.
- **Ship a "hello world" FastAPI to Alibaba Cloud in Step 2** — a URL you can
  curl. Not the real app, just the pipe. Then redeploy the real app on every step
  and deployment is never a surprise.

### 1.8 The HTTPS trap that kills demos

The draft puts the frontend on Vercel and the backend on Alibaba Cloud. Vercel
serves over `https://`. A fresh Alibaba ECS gives you `http://<ip>:8000`.
**Every browser will silently block every request as mixed content**, and your
demo shows an empty table.

Pick one in **Step 2**, not at the end:

| Option | Effort | Notes |
|---|---|---|
| Domain + Caddy/nginx + Let's Encrypt on the ECS box | ~2 h | Cleanest. Caddy does TLS automatically. Needs a domain. |
| Deploy the frontend on Alibaba too, same origin | ~2 h | Also strengthens the "runs on Alibaba Cloud" claim. |
| Vercel rewrite proxying `/api/*` to the HTTP backend | ~30 min | Fastest. Server-side call, so no mixed content. Fine for a hackathon. |

Recommended: the **Vercel rewrite proxy** for speed, with TLS on the ECS box if
you get slack later. But if §0 confirms hosting on Alibaba is mandatory, prefer
option 2 so the whole stack is visibly Alibaba-hosted.

### 1.9 Urdu is your differentiator and it is untested until far too late

The draft treats Urdu as a late task, yet the pitch leans on it as the thing no
global competitor offers. If Qwen VL reads Urdu invoices poorly, you learn this
with no time to re-frame.

**In Step 1, before anything else is built, run a 30-minute spike:** send one
Urdu invoice image to Qwen VL and look at the output. There are two separable
claims, and the second is far safer than the first:

- **Urdu document reading** (OCR of Urdu/Nastaliq text) — genuinely hard, may disappoint.
- **Urdu explanations** (findings explained in Urdu to a client) — text generation, will almost certainly work well.

If reading works: lead with it. If it doesn't: lead with Urdu explanations, still
truthful, still a real edge, and no one on stage knows you changed plans. **Make
this call in Step 1.**

---

## 2. Two more things worth changing

### 2.1 Add Benford's Law — it is the cheapest credibility you can buy

Your rule set (round numbers, weekends, duplicates, near-limit) is fine but
generic. **Benford's Law first-digit analysis is the canonical fraud-analytics
test**, it is pure arithmetic (fully Rule 2 compliant), it is about 30 lines of
pandas, and it produces a chart that looks fantastic on the dashboard.

To a judge who knows audit, seeing Benford's says "these people actually
researched the domain." To a judge who doesn't, it looks like real analytics.
Best effort-to-impression ratio on the board. It belongs in Step 3, once matching
passes.

### 2.2 Tighten the red-flag rules — the draft's version will drown you in noise

| Rule | Problem with the draft | Fix |
|---|---|---|
| Round numbers | "ends in 0000" flags every legitimate salary, rent, and round transfer in PKR | Require ≥ 3 trailing zeros **and** amount above a floor; severity **low / informational**. Never the headline flag. |
| Midnight entries | Excel ledgers and PDF statements usually carry no time component at all | Skip unless your sample data genuinely has timestamps. Do not promise it in the demo. |
| Near-limit | One hardcoded threshold | Config list, e.g. `RULES_APPROVAL_LIMITS=50000,100000,500000`, flag within 2% below any of them |
| Duplicates | Invoice number only | Also flag same party + same amount + within 3 days — that catches duplicate payments where the invoice number differs |
| **New: structuring** | — | Two or more payments to the same party on the same day that individually sit under a limit but together exceed it. **This is your best on-camera reveal.** |
| **New: invoice sequence gaps** | — | Missing numbers in a vendor's invoice sequence. Cheap, and audit-real. |

---

## 3. The build sequence

Six steps, gated by exit criteria. Do not move on until the criteria pass.

**Working rhythm, every session:**
- **Start:** short standup — what I did, what I'm doing, what's blocking me.
- **End:** integration merge. Everyone pushes; the Lead merges to `main` and confirms it still runs.
- **Before you stop:** cut check — what didn't finish, and does it get dropped or moved?

---

### Step 1 — Contracts, spikes, and a booting app

**The theme: de-risk everything unknown, and unblock the other two people.**

**Lead**

1. Start Alibaba Cloud account verification. It runs in the background from here on. Claim Model Studio free credits.
2. **Urdu spike** (§1.9). One Urdu invoice → Qwen VL. Decide: reading vs explanations. Post the answer in team chat.
3. **Provenance spike** (§1.4). One English invoice → Qwen VL asking for bboxes. Are they usable? Decide bbox vs page+snippet.
4. Add `LICENSE` (MIT), make the repo public. *Five minutes, hackathon requirement, do not forget this.*
5. **Freeze the contracts** (§1.2): `app/shared/` schemas + `docs/api-contracts.md` + `sample-data/fixtures/*.json`. **This is the highest-priority deliverable in the whole plan — the other two are blocked until it lands.**
6. Make the app boot: `requirements.txt`, `__init__.py`s, real `app = FastAPI()`, `/health`, CORS, all five routers returning fixture data.
7. Supabase project. Tables + the `revoke update, delete` on `audit_trail` (§1.6).
8. Real Qwen VL extraction for one invoice → schema-valid output with provenance.

**Dev-D**

1. Environment: Python, VS Code, `pip install pandas openpyxl rapidfuzz pytest`. Get a Jupyter notebook running.
2. Pandas fundamentals — read Excel/CSV, filter, merge, groupby, `to_datetime`. Prompt 1 in §5.
3. **Build the sample dataset** (§4). This is your main deliverable for this step, and it is genuinely important work — the whole demo runs on it.
4. Load all three files into DataFrames, clean them (types, dates, whitespace), print them. No matching yet.

**Dev-F**

1. `npx create-next-app@latest` — TypeScript, Tailwind, App Router. Add shadcn/ui. Push it.
2. Layout shell: sidebar, header, four routes (`/upload`, `/review`, `/dashboard`, `/report`).
3. Upload page — three drop zones, file validation, disabled-until-complete button.
4. Once the Lead pushes fixtures: wire a typed `api.ts` client that reads from `sample-data/fixtures/`. Start the review table.

**Exit criteria:**
- [ ] `curl http://localhost:8000/v1/review-items` returns fixture JSON
- [ ] `npm run dev` shows the upload page
- [ ] Sample dataset exists with all planted errors documented
- [ ] Urdu question answered: reading or explanations?
- [ ] Repo is public with a LICENSE
- [ ] Alibaba account status known

---

### Step 2 — The deterministic core, and a live URL

**Lead**

1. Extraction for all document types: multi-page PDF → images (PyMuPDF — no poppler system dependency, unlike pdf2image) → Qwen VL → schema objects.
2. **The ledger does not go through AI.** Excel/CSV is already structured; pandas reads it directly. Say this out loud in the pitch — "we use AI only where AI is needed" is a strong line.
3. Wire the pipeline: upload → extract → `matching.service` → `rules.service` → response. Use Dev-D's stubs if they aren't done.
4. **Ship "hello world" to Alibaba Cloud** (§1.7). A URL you can curl.
5. **Decide the HTTPS approach** (§1.8) and implement it.

**Dev-D — the most important work of your build**

1. `matching/service.py`: `run_matching(ledger, bank, invoices) -> list[MatchResult]`.
2. Amount exact + date exact + party similar → `matched`, strength `high`.
   Amount exact + date within 3 days → `matched`, strength `medium`.
   Amount within tolerance, party similar → `partial`, strength `low`.
   Nothing found → `unmatched`.
3. Use **rapidfuzz** (faster and better than difflib) with a party-name normaliser first: lowercase, strip `pvt`, `(pvt)`, `ltd`, `limited`, `&`/`and`, punctuation, extra whitespace. **For Pakistani entity names, that normaliser will improve match quality more than any clever algorithm.**
4. Every result carries a human-readable `reason` string. The UI shows it verbatim, so write it for an auditor: *"Amount matches exactly; bank date is 2 days later than ledger date."*

**Dev-F**

1. Review table against fixtures: date, amount, party, status badge, match strength, extraction confidence, actions.
2. Filter tabs: All / Matched / Partial / Unmatched / Flagged.
3. Approve and Reject buttons with optimistic UI and a rejection-reason prompt.

**Exit criteria — the hard checkpoint:**
- [ ] **Alibaba Cloud URL responds to curl**
- [ ] **HTTPS approach decided and working**
- [ ] `pytest` passes on matching against the sample data — all planted errors correctly classified
- [ ] Review table renders and filters fixture data

> **⚠️ Kill-switch:** if matching is not passing tests by the end of this step,
> the **Lead takes over `matching/`** (it is a couple of hours of pandas for
> someone fluent) and Dev-D moves to `rules/`, which is simpler and fully
> independent. This is not a failure — it is the plan. Agree it now, out loud, so
> it isn't awkward later.

---

### Step 3 — Integration

**Everyone, together, in one call for the first stretch.** Integration is when
contract mismatches surface, and they surface fastest with all three people
looking.

**Lead**

1. Real endpoints replacing fixtures: `POST /v1/upload`, `GET /v1/review-items`,
   `POST /v1/review-items/{id}/approve`, `/reject`, `GET /v1/dashboard`.
2. Supabase Storage for uploads. Audit-trail writes on every mutating call.
3. Auth: **one seeded demo user, email + password, no signup flow.** Enough for a
   real `user_id` in the audit trail; skip everything else. Full auth is a large
   block of work no judge will see.
   *(Superseded: `POST /v1/auth/signup` exists, and each signup creates the
   organization its user owns. The seeded demo auditor still works, in the
   default organization.)*

**Dev-D**

1. `rules/service.py` with the tightened rule set from §2.2, including structuring.
2. **Benford's Law** (§2.1) — returns the 1–9 digit distribution plus expected values so Dev-F can chart it.
3. Every flag carries `rule_id`, `severity`, `explanation`, and the source provenance.

**Dev-F**

1. Point `api.ts` at the real backend. Fix whatever breaks.
2. Approve/reject round-trip working end to end.
3. Start the evidence viewer: slide-over, ledger row left, document page right.

**Exit criteria:**
- [ ] Full flow works on real data: upload → extract → match → flag → review table
- [ ] An approve click lands a row in Supabase `audit_trail`
- [ ] All planted errors visible in the UI

---

### Step 4 — The evidence viewer and the second opinion

**Lead**

1. Evidence-viewer API: given an item, return the document URL, page number, and highlight region.
2. **AI second opinion — but built as a *verifier*, not a second guesser.** The draft's approach runs two unrelated prompts and compares; different tasks produce noisy disagreement. Instead: pass Qwen the image **and** the first extraction, and ask *"verify each of these values against the image; correct any that are wrong."* That is a checker, it is more reliable, and it is a better story: *"the AI checks its own work, and any disagreement is escalated to a human — never resolved by the AI."*
3. Run it only on low-confidence fields. It doubles token cost.

**Dev-D**

1. Edge cases: negative amounts, credit vs debit, blank party names, mixed date formats (`31/01/2026` vs `01/31/2026` — pick a convention and enforce it), duplicate ledger rows, empty files.
2. Write the tests that prove each planted error is caught. **These tests are your evidence to the judges that the matching is deterministic** — they pass identically on every run.

**Dev-F**

1. Finish the evidence viewer with highlighting.
2. Dashboard: stat cards, Benford's chart, audit-readiness score, hours-saved counter.
3. Show the `reason` string prominently — it is what makes the tool feel intelligent rather than mechanical.

**Exit criteria:**
- [ ] Clicking an item opens the source document at the right page with the value highlighted
- [ ] Low-confidence extractions get verified and disagreements are escalated, never auto-resolved
- [ ] Dashboard renders real numbers

---

### Step 5 — Reports, Urdu, demo mode, and a rough-cut video

**Lead**

1. PDF report (ReportLab or WeasyPrint) + Excel report (openpyxl). Include the audit trail as an appendix — that is the differentiator, so make it visible.
2. Urdu, per the Step 1 decision.
3. **Build `DEMO_MODE`** (see §6). Do not skip this.
4. **Record a rough-cut video.** Not the final one. The rough cut tells you which parts of the demo are slow, confusing, or broken — while there is still time to fix them. Teams that first record at submission time always discover something ugly.

**Dev-D**

1. Verify every number in the generated report against the source data by hand. **You are the last line of defence on correctness** — a wrong number on stage is fatal.
2. Freeze the sample data. No changes after this step.

**Dev-F**

1. Report page, download buttons, loading and empty states.
2. Polish. Desktop-first — do not spend time on mobile, you are demoing on a laptop.
3. **Every screen needs a non-embarrassing loading and error state.** Live demos hit slow networks.

**Exit criteria:**
- [ ] PDF and Excel reports download and every number in them is verified correct
- [ ] `DEMO_MODE` serves the full flow with no network dependency
- [ ] A rough-cut video exists and you have watched it together
- [ ] Sample data is frozen

---

### Step 6 — Deploy, record, submit

**Submit well before the deadline, not at it.** Portals get slow and crash in the
final hours, and the live round comes right after.

**Lead**

1. Final deploy, both frontend and backend. Run the full flow on production three times.
2. Architecture diagram (Excalidraw). Written description.
3. Work the submission checklist (§8) and **submit with hours to spare**.

**Dev-F**

1. Final polish pass on production. Check every screen on the actual demo machine.

**Dev-D**

1. Verify production output matches local. Same numbers, same flags.

**All**

1. Record the final video (§7). Multiple takes, pick the best.
2. Rehearse the live pitch. Prepare answers to the Q&A in §9.

**Exit criteria:**
- [ ] Everything in the submission checklist ticked
- [ ] Submitted
- [ ] Live pitch rehearsed end to end at least twice

---

## 4. The sample dataset — treat it as a product, not a fixture

Your demo *is* this dataset. It deserves real care, and it is Dev-D's Step 1 job.

**Volume:** one bank statement (2–3 pages, ~40 transactions), 8–10 invoices,
one ledger (~50 rows). Small enough that extraction finishes fast on camera —
Qwen VL takes seconds per page, and a 20-page statement will kill your demo pacing.

**Realism:** Pakistani company names, PKR amounts, a plausible month of trading,
mixed invoice quality (a clean PDF, a phone photo, a slightly skewed scan, one
Urdu invoice). The photo and the skewed scan matter — they show the vision model
earning its place.

**Five planted errors, each mapping to a rule so every reveal lands:**

| # | Error | Should surface as |
|---|---|---|
| 1 | Ledger entry with no bank payment and no invoice | **Unmatched** — the fictitious-vendor story |
| 2 | Transposition: ledger says 45,900; bank says 49,500 | **Partial match**, amount mismatch — the classic human error |
| 3 | Same invoice number paid twice, 11 days apart | **Duplicate flag** |
| 4 | Two payments of 49,500 to one party, same day, limit is 50,000 | **Structuring flag** — save this one for last on camera |
| 5 | Large round payment entered on a Sunday | **Round-number + weekend flags** |

Document these in `sample-data/README.md` with the expected outcome for each.
That file becomes both your test oracle and your demo script.

---

## 5. Prompt packs (revised)

The draft's prompts were good. These are the corrected ones — the changes matter.

**Dev-D · matching engine**
> I'm building a deterministic audit matching engine in Python with pandas. I have three DataFrames — `ledger`, `bank`, `invoices` — each with columns `date`, `amount`, `party_name`, plus `invoice_number` on invoices. For each ledger row, find the best candidate in bank or invoices. Exact amount + exact date + party similarity ≥ 85 → matched/high. Exact amount + date within 3 days → matched/medium. Amount within 1% + party similar → partial/low. Nothing → unmatched. Use rapidfuzz for party similarity, and normalise names first (lowercase, strip "pvt", "(pvt)", "ltd", "limited", punctuation, extra whitespace). Return a list of dicts with `ledger_row`, `matched_row`, `status`, `match_strength`, and a human-readable `reason` string an auditor would understand. **Pure pandas and standard library only — no AI, no LLM, no network calls, no FastAPI, no database. Just a function that takes DataFrames and returns a list.**

**Dev-D · rules**
> Write a Python function taking a pandas DataFrame of ledger entries and returning a list of red flags. Rules: (1) amount has ≥3 trailing zeros AND is above 10,000 — severity low; (2) date falls on Saturday or Sunday — severity medium; (3) the same `invoice_number` appears more than once — severity high; (4) amount is within 2% below any value in a configurable `approval_limits` list — severity high; (5) **structuring** — two or more payments to the same party on the same date that are each under a limit but sum to over it — severity high. Each flag returns `rule_id`, `severity`, `explanation` (plain English, auditor-readable), and the row index. Pure pandas, no AI.

**Dev-D · Benford's Law**
> Write a pandas function that runs a Benford's Law first-digit test on a column of amounts. Return the observed frequency of leading digits 1–9, the expected Benford frequency, the deviation per digit, and a chi-square statistic. Include a boolean flag for whether the distribution deviates significantly. Add a docstring explaining what the test means for an auditor. Pure math, no AI.

**Lead · Qwen VL extraction with provenance**
> Write a Python function that sends a document page image to Alibaba Cloud Model Studio's Qwen VL API and extracts invoice fields. **For every extracted field, the model must return the value, a confidence level of high/medium/low, and the source location as a normalised bounding box `[x0, y0, x1, y1]` in 0–1 coordinates, plus the verbatim text snippet it read.** Enforce a strict JSON schema and retry once on a parse failure. Handle timeouts and rate limits with backoff. Return typed objects, never raw dicts.

**Lead · second opinion as a verifier**
> Write a Python function that verifies an existing extraction. Input: the page image and the previously extracted fields. Prompt Qwen VL to check each value against the image and report, per field, whether it agrees, and its own reading if it disagrees. If any field with a monetary value disagrees, return `needs_human_review=True` with both readings. **The function must never pick a winner between the two readings — disagreement always escalates to a human.**

**Dev-F · review table**
> Build a TypeScript data table in Next.js with shadcn/ui. Columns: Date, Amount (right-aligned, PKR formatted), Party, Status badge (Matched green / Partial amber / Unmatched red / Flagged purple), Match Strength, Extraction Confidence, Reason (truncated with tooltip), Actions. **Match strength and extraction confidence are two distinct columns with distinct meanings — do not merge them.** Actions: Approve (green), Reject (red, opens a reason prompt), View Evidence. Filter tabs above. Empty state, loading skeleton, and error state all required.

**Dev-F · evidence viewer**
> Build a slide-over evidence viewer in Next.js. Left panel: the ledger entry and the matched document row, with differing fields highlighted. Right panel: a PDF or image viewer (react-pdf) that jumps to a given page and draws a highlight rectangle from normalised `[x0,y0,x1,y1]` coordinates scaled to the rendered page size. Props: `documentUrl`, `page`, `bbox`, `textSnippet`. **If bbox is null, fall back to highlighting the text snippet instead.**

---

## 6. Demo mode — the insurance policy the draft is missing

On demo day, on venue wifi, one of these *will* happen: the Qwen API is slow, you
hit a rate limit, your credits ran out, or the wifi drops.

**Build `DEMO_MODE=true`** in Step 5. When enabled, the backend serves cached
extraction results for the frozen sample dataset instead of calling Qwen — same
schemas, same code path downstream, roughly 200 ms instead of 30 seconds.

Three things this buys you:
1. The live demo never depends on the network.
2. Your video records at a watchable pace.
3. Dev-F can develop without burning API credits.

Record the video on the **real** path so it is honest. Arm demo mode for the
**live** round. And if a judge asks: "demo mode replays cached extractions of our
sample data so the demo doesn't depend on venue wifi — here's the same flow
hitting the live API." That answer is a strength, not an admission.

---

## 7. The 3-minute video

The draft's structure is good. Two changes: open on the reveal, and save
structuring for last.

| Time | Content |
|---|---|
| 0:00–0:20 | **Open with the catch, not the problem.** Show the structuring flag firing: "Tarazu found two payments of 49,500 to the same vendor on the same day, structured to stay under a 50,000 approval limit. A human missed it. It took Tarazu four seconds." |
| 0:20–0:40 | Now the problem. Auditors reconcile thousands of rows by hand; Pakistani SME audits are priced so tightly the work gets rushed. |
| 0:40–1:20 | Live upload. AI reads the documents. **Show a value's provenance** — click through to the highlighted region on the source page. This is the trust moment. |
| 1:20–1:50 | The results table. Unmatched entry. Transposition error. Duplicate. |
| 1:50–2:20 | **Human decides.** Approve one, reject one. Show the audit-trail row appearing. Say the line: *"the AI suggests, the human decides — there is no auto-approve path in this system."* |
| 2:20–2:40 | Urdu — reading or explanation, per your Step 1 call. |
| 2:40–3:00 | One-click report with the audit trail attached. Close on hours saved. |

**Record clean audio.** Bad audio makes a good product look amateur, and a phone
in a quiet room beats a laptop mic in a busy one.

---

## 8. Submission checklist

- [ ] Repo public, `LICENSE` present (MIT)
- [ ] `README.md` with setup instructions that work on a clean clone
- [ ] Architecture diagram exported as PNG
- [ ] **A file or README section that explicitly points to where Alibaba Cloud is used** — judges look for this, do not make them hunt
- [ ] 3-minute video uploaded and the link tested in an incognito window
- [ ] Deployed backend URL live and responding
- [ ] Deployed frontend URL live
- [ ] Written description mentioning: human-in-the-loop, deterministic math, provenance, immutable audit trail, no training on client data
- [ ] Demo credentials in the submission if the judges need to log in
- [ ] Submitted with **hours of buffer**, not minutes

---

## 9. Judge Q&A — prepare these answers

Rehearse these in Step 6. The first three will almost certainly be asked.

**"How do you know the AI got the numbers right?"**
> We don't trust it — we make it prove it. Every extracted value carries its source page and location, one click shows you the original document with the number highlighted, and low-confidence extractions get a second verification pass. When the two passes disagree, it goes to a human. The AI is never the final word.

**"What if the AI hallucinates an amount?"**
> Then a human catches it, because nothing is finalised without an explicit approval click, and the source is one click away. And the hallucination can't propagate into the totals — the AI never does arithmetic. All matching and math is pandas. [Show the test suite.]

**"How is this different from existing audit software?"**
> Existing tools work on clean, structured data that's already in a system. Real Pakistani SME audits arrive as PDF bank statements, phone photos of invoices, and an Excel file. Tarazu starts from the messy documents. And it reads Urdu.

**"Is this just a wrapper around an LLM?"**
> The LLM does one job — turning pixels into text. Everything that matters after that is deterministic code: the matching, the fraud rules, the Benford's analysis, the audit trail. You could swap the vision model out tomorrow and the audit logic wouldn't change by a single line.

**"Is client data used to train the model?"**
> Never. Inference call only — no telemetry, no fine-tuning, no feedback loop. That's a hard architectural rule in our codebase, not a policy page.

---

## 10. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Alibaba Cloud account verification stalls | Medium | High | Started as the first action of Step 1. Fallback: Model Studio via API key only, host the backend elsewhere, and be upfront about it. |
| Dev-D's matching slips past Step 2 | Medium | High | Kill-switch: Lead takes matching, Dev-D takes rules. Agreed in advance. |
| Qwen VL bounding boxes unusable | Medium | Medium | Fall back to page + text-snippet highlighting. Decided in Step 1. |
| Urdu OCR disappoints | Medium | Medium | Pivot the claim to Urdu explanations. Decided in Step 1. |
| Mixed content blocks the frontend | High if unaddressed | Fatal | Resolved in Step 2 (§1.8). |
| API rate limits or dead credits during the demo | Medium | Fatal | `DEMO_MODE` (§6). |
| Merge conflicts eat a large block of time | Medium | Medium | Strict file ownership: Dev-D owns `matching/` + `rules/` + their tests. Dev-F owns `frontend/`. Lead owns everything else. Merge at the end of every session. |
| Scope creep | **High** | High | The cut list below is final. |

---

## 11. The cut list — final, not aspirational

**Cut for the hackathon. Mention as roadmap in the pitch; do not build.**

- The `assistant/` chat module. The module boundary stays in the repo as an
  architectural statement, but no chat UI, no chat endpoint. This is the single
  biggest time saver in the plan. *(Urdu explanations, if you ship them, come
  from a single templated call — not a chat interface.)*
- Real-time processing status via websockets. Poll every 2 seconds instead.
- ~~Multi-user auth, signup, roles, permissions. One demo user.~~ **Uncut.**
  Signup, organizations, and owner/member roles were built; see
  [ADR 0003](decisions/0003-tenancy-is-an-org-id-column-and-two-enforcement-layers.md).
- Mobile responsive.
- Risk heatmaps and advanced visualisations. The Benford chart is enough.
- ~~Multi-tenant client management.~~ **Uncut**, in the same change: a tenant is
  one accounting firm, and every row carries its `org_id`.
- Holiday calendars (Pakistani holidays for the weekend rule). Nice, not now.

**If you finish early — and you probably won't — the order is:** Urdu
explanations first, then the assistant chat, then real-time status.

---

## 12. Answering the original plan's open questions

**Is pandas right for production?** Yes, and the draft's reasoning was sound.
Pandas is the standard for deterministic financial data processing, the audit
domain runs on it, and your beginner teammate can be productive in it quickly. If
you ever hit millions of rows per audit, Polars is a mostly mechanical migration —
the logic doesn't change. Not a hackathon concern.

**Which track?** The draft's "Financial Inclusion" pick is a stretch worth
examining. Financial inclusion usually means unbanked and underserved
*individuals*; Tarazu is B2B tooling for accounting firms. A judge who takes the
track definition seriously could mark you down on fit.

Use this decision rule when you read the actual track descriptions in §0:

- If **Financial Inclusion** explicitly mentions SMEs or business access to finance → take it, and pitch it as: *"SMEs can't get formal credit without audited accounts. Audits are too expensive because they're manual. Cheaper, faster audits mean more SMEs in the formal financial system."* That is a genuine and defensible chain.
- Else if **Urdu & Regional Tech** is real *and* your Step 1 Urdu spike succeeded → take it. Your Urdu capability is the least contestable claim you have.
- Else → **Open Innovation.** Never lose on track fit for a product that's strong on its merits.

**Is the scope realistic?** Yes, with the cut list held and the contract-first
change made. Without contract-first, you lose a large block of parallel work to
waiting. Without the cut list, you finish nothing.

---

## 13. A note to the Lead

Your hardest job is not the Qwen integration. It is **staying
unblocked-unblocking**: your teammates' throughput depends on artefacts only you
can produce — the contracts in Step 1, the deploy in Step 2, the endpoints in
Step 3. Every hour you spend heads-down on your own feature while someone is
waiting on you costs the team more than it gains.

Ship the contracts first. Everything else follows from that.

And hold the line on CLAUDE.md's seven rules even when you are tired and behind —
they are not overhead, they are the product. The reason Tarazu is defensible is
precisely that it refuses to let AI touch the numbers. Any shortcut that blurs
that boundary doesn't just break a rule, it deletes your pitch.
