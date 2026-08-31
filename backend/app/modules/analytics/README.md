# modules/analytics/

**Purpose:** Deterministic sales analytics over a client's sales export: pandas
reads the spreadsheet, and the readout — revenue by month, product, and region,
the top customers, and anomaly findings — is sums and counts over `Decimal`
money. This module uses no AI. The export is already structured; a model could
only misread a number that is sitting right there in a cell.

**Inputs:** A `sales_data` document's bytes (`read_sales_data`), or the
`SalesRecord` rows of every sales document in a case (`analyze_sales`).

**Outputs:** `SalesRecord` rows with spreadsheet-row provenance, and one
`SalesAnalyticsResult` per case. The breakdowns partition the records — by
month and by product they sum back to `total_revenue` and count back to
`record_count` — and the schema rejects a result where that stops being true.

**Public interface:** `service.py` only. Other modules import nothing else from
this package.

## The anomalies

Emitted in this order, numbered `ANM-0001…` within the readout. All of them are
findings for a human, exactly like flags: never verdicts, never suppressed.

| `kind` | Fires when |
|---|---|
| `negative-amount` | a sale's amount is below zero — a refund, a correction, or a sign error |
| `duplicate-transaction` | the same date, customer, product, and amount appears more than once; `related_row_ids` names the whole group |
| `revenue-spike` | with at least 3 months, a month's revenue is more than double the median month, or under half of it |
| `large-transaction` | with at least 10 sales, one sale is more than 10× the median sale |

The comparisons are against medians, not means, so one enormous month or sale
cannot lift the bar against its own detection; the minimum sample sizes keep
small cases from being handed verdicts made from nothing.

## The reader

Header aliases are resolved the way the ledger reader resolves its own (`Sale
Date`/`Txn Date`…, `Amount`/`Total`/`Line Total`…), money is parsed the same
way (`Rs. 45,900/-`; accounting parentheses are negative), and ambiguous dates
are day-first, the Pakistani convention. A CSV whose rows are wider than its
header is refused with instructions — an amount containing the delimiter must
be quoted, `"Rs. 45,900"` — because pandas would otherwise shift every column
or drop the extra field silently, and a silent misread is the one failure an
audit layer must never have. Rows missing the date, amount, customer, or
product are skipped as blanks and counted in a log line, never silently.

**Must never do:**

- **Never call an AI model and never import any AI client.** The analysis is
  deterministic code only. `test_analytics.py` checks the imports.
- Never turn an anomaly into a verdict, and never suppress one. Findings go to
  a human, who weighs them.
- Never import another module — not even another module's `service.py`. The
  package is self-contained beside `app.shared/`; `test_analytics.py` checks
  this too.
- Never touch the network, the stores, or the filesystem. It receives bytes
  and records, and returns schemas.
