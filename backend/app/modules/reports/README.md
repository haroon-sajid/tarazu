# modules/reports/

**Purpose:** Generates the final deliverables: a PDF and an Excel workbook
assembled from human-decided results and the audit trail.

**Inputs:** The case, its review items (decided and pending), its audit-trail
records, and its Benford result (`app/shared/` schemas).

**Outputs:** The two files as bytes and a `ReportRecord` describing them: the
storage paths the caller writes them to, SHA-256 digests of exactly those
bytes, and the counts at the moment of generation. The route stores the files,
saves the record, and appends `report_generated` to the audit trail.

**Public interface:** `service.py` only. Other modules import nothing else from
this package.

## Layout

| File | Role |
|---|---|
| `service.py` | `generate_report(...)` and `report_content(...)`. |
| `content.py` | Turns persisted results into a `ReportContent`: a summary and titled tables of strings. Both renderers walk it, so the two files cannot disagree. |
| `pdf.py` | reportlab rendering, landscape A4, every page footed with the report id. |
| `excel.py` | openpyxl rendering, one sheet per section, byte-reproducible (timestamps set to the report's own time). |

## What a report contains

1. A summary block: client, case, period, counts, who generated it and when,
   the report id.
2. **Decided items**: every ledger row carrying an explicit human decision,
   with its match result and the decision. Pending items are counted and named
   as pending in the note and are not listed.
3. **Red flags on decided items.**
4. **Provenance**, for every figure behind a decided item: the document, the
   page or spreadsheet row, and the characters as printed.
5. **Benford's law** table, when the case has one.
6. **The audit trail**, complete, oldest first, as it stood at generation.

## Reports are immutable

A report is evidence of what the firm delivered on a date. The `reports` table
refuses UPDATE and DELETE in both stores (SQLite triggers; Postgres REVOKE, RLS
without update or delete policies, and triggers, `infra/supabase/0006`), and
the repository has no method that could try. Regenerating after more decisions
produces a new record; the old file stays downloadable and its digest stays on
record.

**Must never do:**

- Never call an AI model. Reports are deterministic templating over approved data. If AI-written summaries are ever added, they must arrive pre-generated and human-approved via `assistant/`.
- Never list an item that lacks an explicit human approve or reject decision as a finding. Pending items are counted and named as pending, nothing more.
- Never recompute or "fix" numbers. This module renders exactly what the deterministic modules produced and humans approved.
- Never omit the audit trail or provenance from the full report.
