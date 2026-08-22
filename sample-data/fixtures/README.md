# sample-data/fixtures/

**Purpose:** Hand-written, entirely synthetic API responses that let `frontend/`
be built and demoed before the backend pipeline exists. The backend serves these
today via `app/api/fixtures.py`; the response shapes are final, only the data
source changes.

**These files are contracts, not scratch data.** They are parsed through the
real Pydantic models on every app start and in `backend/tests/test_fixtures.py`.
Edit one into a shape the backend cannot produce and the tests fail — which is
the point.

| File | Schema | Serves |
|---|---|---|
| `review-items.json` | `ReviewItemsResponse` | `GET /v1/review-items` |
| `dashboard.json` | `DashboardSummary` | `GET /v1/dashboard` |
| `extraction-result.json` | `ExtractionResult` | The evidence viewer and second-opinion flow |

## The sample case

`CASE-2026-06-STX` — a June 2026 audit of **Sethi Textiles (Pvt) Ltd**, a
fictional Karachi textile firm. Ten review items, all amounts in PKR, all
company names invented. **No real client data belongs in this folder, ever.**

Documents referenced:

| Document id | File | Read by |
|---|---|---|
| `DOC-LED-001` | `sethi-textiles-ledger-june-2026.xlsx` | pandas — no AI |
| `DOC-BNK-001` | `hbl-statement-june-2026.pdf` (3 pages) | Qwen VL |
| `DOC-INV-0087` | `karachi-packaging-inv-0087.pdf` | Qwen VL |
| `DOC-INV-0431` | `sialkot-metal-works-inv-0431-photo.jpg` | Qwen VL |

## The five planted errors

Every one maps to a rule, so each reveal in the demo lands on something real.
This table is the test oracle *and* the demo script.

| # | Error | Rows | Surfaces as |
|---|---|---|---|
| 1 | Ledger entry with no bank payment and no invoice — the fictitious-vendor story | `LED-0031` (RI-0010) | `status: unmatched` |
| 2 | Transposition: ledger says 45,900, bank says 49,500 | `LED-0012` (RI-0004) | `status: partial`, amount mismatch |
| 3 | Invoice `INV-2026-0087` paid twice, 11 days apart | `LED-0007`, `LED-0023` | `duplicate-invoice`, severity high |
| 4 | Two payments of 49,500 to one party on one day, under a 50,000 limit | `LED-0014`, `LED-0015` | `structuring` + `near-limit`, severity high |
| 5 | 1,500,000 round payment posted on Sunday 2026-06-14 | `LED-0019` (RI-0007) | `weekend-entry` + `round-number` |

Save **structuring** for last on camera. It is the only one a human reviewer
would plausibly miss, and it is the strongest thing in the demo.

## Two things the fixtures deliberately demonstrate

**Extraction confidence and match strength are independent.** RI-0009 (Sialkot
Metal Works) carries `extraction_confidence: "low"` — it is a phone photo — while
its `match_strength` is `"medium"`, computed by pandas from the amount and date.
Neither number influenced the other, and the review table shows them as two
columns.

**The AI never resolves its own disagreement.** `extraction-result.json` is that
same invoice: the first pass read `312,880` and the verification pass read
`312,860`, so `second_opinion.agrees` is `false` and `needs_human_review` is
`true`. There is no field in the schema where the AI could record a winner.

## Keeping them honest

`review-items.json` and `dashboard.json` describe the same ten items, and the
tests assert it: status counts, decision counts, confidence counts, flag counts
by severity, and the Benford first-digit distribution are all recomputed from
the review queue and compared.

The three derived figures are checked the same way — `audit_readiness_score`,
`data_confidence`, and `next_best_actions` in `dashboard.json` are compared
against what `app/dashboard_metrics.py` actually computes from
`review-items.json`. A hand-edited breakdown that the code would not produce
fails the build.

**If you edit one file, run `pytest` before you push** — a dashboard that
disagrees with the queue would teach the frontend a lie.
