# modules/reports/

**Purpose:** Generates the final deliverables: PDF and Excel audit reports plus
a client-friendly summary, assembled from human-approved results and the audit
trail.

**Inputs:** Approved and rejected items, match results, flags, and audit-trail
records for a case (`app/shared/` schemas).

**Outputs:** PDF and Excel files stored in Supabase Storage, and
report-generation events in the audit trail.

**Public interface:** `service.py` only. Other modules import nothing else from
this package.

**Must never do:**

- Never call an AI model. Reports are deterministic templating over approved data. If AI-written summaries are ever added, they must arrive pre-generated and human-approved via `assistant/`.
- Never include items that lack an explicit human approve or reject decision.
- Never recompute or "fix" numbers. This module renders exactly what the deterministic modules produced and humans approved.
- Never omit the audit trail or provenance from the full report.
