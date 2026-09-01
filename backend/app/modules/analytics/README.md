# modules/analytics/

**Purpose:** Deterministic sales analytics over a client's sales exports:
pandas reads the file — in whatever shape the client's software produced it —
cleans it the way an auditor would by hand while saying exactly what it did,
and the readout (revenue by month, product, and region, the top customers, and
anomaly findings) is sums and counts over `Decimal` money. The saved readout
can leave the product as an Excel workbook. This module uses no AI. The export
is already structured; a model could only misread a number that is sitting
right there in a cell.

**Inputs:** A sales export's bytes and filename (`read_sales_export`), the
`SalesRecord` rows of every export in a case plus their read reports
(`analyze_sales`), or a saved `SalesAnalyticsResult` (`export_workbook`).

**Outputs:** `SalesRecord` rows with spreadsheet-row provenance and one
`SourceReadReport` per file; one `SalesAnalyticsResult` per case, carrying the
reports as `data_quality`; workbook bytes. The breakdowns partition the
records — by month and by product they sum back to `total_revenue` and count
back to `record_count` — and the schema rejects a result where that stops
being true.

**Public interface:** `service.py` only. Other modules import nothing else from
this package.

## The reader

Accepts `.csv`, `.tsv`, `.txt` (any of `, ; tab |`, sniffed), `.xlsx`, `.xlsm`,
`.xls`, `.ods`, and `.json` (a list of objects, or an object holding one under
`data` / `rows` / `records` / `items` / `sales`). Text is decoded as UTF-8
(with or without Excel's BOM), UTF-16 when its byte-order mark says so, then
Windows-1252, then Latin-1.

What it does with the table, in order, all of it reported:

1. **Finds the header.** The first thirty rows are scanned for the row that
   names the most known fields, provided it names a date and an amount (or a
   quantity and a unit price). Title blocks and blank lines above it are
   skipped; `header_row` in the report says where it was. In a workbook, every
   sheet is tried in order and the first one with a usable table wins; the
   others are named in `warnings`.
2. **Maps the columns.** Exact header aliases first (`Sale Date` / `Txn Date`
   / `Invoice Date`…, `Amount` / `Total` / `Net Amount` / `Line Total`…,
   `Customer` / `Party` / `Client`…, `Product` / `Item` / `SKU` /
   `Description`…, `Region` / `City` / `Province` / `Branch`…), then substring
   hints for what is left — and a money-looking hint never lands on a tax,
   discount, cost, or balance column. `columns` in the report names the
   client's own header behind each field.
3. **Reads the money and the dates.** `Rs. 45,900/-` is 45900; accounting
   parentheses are negative; a bare `-` before the digits is negative; a
   trailing `/-` is not. Ambiguous dates are day-first, the Pakistani
   convention; ISO dates are taken as written; Excel serials that lost their
   format are converted. With no amount column, the amount is quantity × unit
   price in Decimal, row by row, and `amount_derived` is true.
4. **Skips what is not a sale, and counts it.** Blank rows, total and subtotal
   lines, rows with no readable date, rows with no readable amount — each
   under its reason in `skipped`. A delimited row wider than its header is
   refused outright with instructions (an amount containing the delimiter must
   be quoted), because pandas would otherwise shift every column or drop the
   extra field silently, and a silent misread is the one failure an audit
   layer must never have.
5. **Never drops a row for a missing dimension.** A row with no customer or
   no product still counts toward revenue, under "Unspecified"; how many is in
   `filled_defaults`. A row with no region simply does not appear in the
   region breakdown.

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

## The export

`export_workbook` renders a saved readout as one workbook: Summary, Monthly
revenue, By product, By region, Top customers, Anomalies, and Data quality
(one row per export). Every cell is copied from the readout; nothing is
recomputed on the way out.

**Must never do:**

- **Never call an AI model and never import any AI client.** The analysis is
  deterministic code only. `test_analytics.py` checks the imports.
- Never turn an anomaly into a verdict, and never suppress one. Findings go to
  a human, who weighs them.
- Never clean silently. Every skipped row, every guessed column, every derived
  amount is in the `SourceReadReport`.
- Never import another module — not even another module's `service.py`. The
  package is self-contained beside `app.shared/`; `test_analytics.py` checks
  this too.
- Never touch the network, the stores, or the filesystem. It receives bytes
  and records, and returns schemas and bytes.
