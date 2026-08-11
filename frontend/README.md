# frontend/

**Purpose:** The Next.js and TypeScript web app for auditors. Screens: document
upload, the human review screen (approve or reject every item), the evidence
viewer (source document and extracted value side by side), the dashboard, and
the reports UI.

**Inputs:** User interactions, data from the `backend/` FastAPI app (the only
backend it talks to), and the Supabase auth session.

**Outputs:** HTTP requests to the backend API, file uploads to Supabase Storage,
and the rendered UI.

**Must never do:**

- Never call backend module internals or the Qwen API directly. All backend access goes through the backend's public `/v1/...` API.
- Never perform matching, math, or fraud-rule logic client-side. The UI only displays server results.
- Never auto-approve items. Every approve or reject is an explicit user click.
- Never hold secrets beyond `NEXT_PUBLIC_*` variables.
