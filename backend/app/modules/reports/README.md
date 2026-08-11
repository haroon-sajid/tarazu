# modules/reports/

**Purpose:** Generates final deliverables: PDF and Excel audit reports plus a
client-friendly summary, assembled from human-approved results and the audit trail.

**Inputs:** Approved/rejected items, match results, flags, and audit-trail records
for a case (`app/shared/` schemas).
**Outputs:** PDF/Excel files stored in Supabase Storage; report-generation events
in the audit trail.

**Public interface:** `service.py` only — other modules import nothing else from here.

**Must NEVER do:**
- Never call an AI model — reports are deterministic templating over approved data. (AI-written summaries, if ever added, must come pre-generated and human-approved via `assistant/`.)
- Never include items that lack an explicit human approve/reject decision.
- Never recompute or "fix" numbers — it renders exactly what the deterministic modules produced and humans approved.
- Never omit the audit trail or provenance from the full report.
