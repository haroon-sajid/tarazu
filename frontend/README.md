# frontend/

**Purpose:** Next.js + TypeScript web app for auditors. Screens: document upload,
human review screen (approve/reject every item), evidence viewer (side-by-side
source document + extracted value), dashboard, and reports UI.

**Inputs:** User interactions; data from the `backend/` FastAPI app (the ONLY
backend it talks to); Supabase auth session.
**Outputs:** HTTP requests to the backend API; file uploads to Supabase Storage;
rendered UI.

**Does NOT belong here / must NEVER do:**
- Never call backend module internals or the Qwen API directly — all backend access goes through the backend's public `/v1/...` API.
- Never perform matching, math, or fraud-rule logic client-side; the UI only displays server results.
- Never auto-approve items — every approve/reject is an explicit user click.
- No secrets beyond `NEXT_PUBLIC_*` variables.
