# frontend/

**Purpose:** The Next.js and TypeScript web app for auditors — Tarazu — AI Audit
Assistant. Screens: document upload, the human review screen (approve or reject
every item), the evidence viewer (source document and extracted value side by
side), the dashboard, and the reports UI.

**Stack:** Next.js (App Router) + TypeScript + Tailwind CSS v4 + Recharts.
Desktop only by decision — no mobile styles.

## Running it

```bash
npm install
npm run dev        # http://localhost:3000
```

With no configuration the app runs in **fixture mode**: every screen is served
from `src/lib/fixtures/` (copies of `sample-data/fixtures/`, which the backend
validates against the real Pydantic schemas). Approve/reject mutate an
in-memory store, so the whole flow demos offline.

To switch to the live backend, set one line in `.env.local`
(see `.env.example`):

```
NEXT_PUBLIC_TARAZU_API_URL=http://localhost:8000
```

## Where things live

| Path | What |
|---|---|
| `src/lib/api.ts` | The one typed API client. Every screen calls this and nothing else; components never fetch. |
| `src/lib/types.ts` | TypeScript mirrors of `backend/app/shared/schemas.py` / `docs/api-contracts.md`. |
| `src/lib/fixtures/` | Copies of `sample-data/fixtures/`. If the contract changes, recopy them. |
| `src/app/{upload,review,dashboard,report}` | The four routes. |
| `src/components/review/evidence-viewer.tsx` | The slide-over: comparison, provenance highlight, flags, audit history. |

**Match Strength and Extraction Confidence are two different columns** with two
different renderings (dot meter vs. "AI:" pill). Match strength comes from the
deterministic matcher; extraction confidence from the AI reading step. Never
merge them — this separation is the core of the product.

**Inputs:** User interactions, data from the `backend/` FastAPI app (the only
backend it talks to), and the Supabase auth session.

**Outputs:** HTTP requests to the backend API, file uploads to Supabase Storage,
and the rendered UI.

**Must never do:**

- Never call backend module internals or the Qwen API directly. All backend access goes through the backend's public `/v1/...` API.
- Never perform matching, math, or fraud-rule logic client-side. The UI only displays server results.
- Never auto-approve items. Every approve or reject is an explicit user click.
- Never hold secrets beyond `NEXT_PUBLIC_*` variables.
