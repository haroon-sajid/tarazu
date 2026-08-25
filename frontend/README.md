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
in-memory store, so the whole flow demos offline — the login screen pre-fills
demo credentials that sign in the seeded auditor.

To switch to the live backend, set one line in `.env.local`
(see `.env.example`) and restart the dev server:

```
NEXT_PUBLIC_TARAZU_API_URL=http://localhost:8000
```

In live mode, sign up a firm (or sign in) on `/signup` / `/login`; the session
token is held in localStorage and sent on every request. A 401 mid-session
(token expired or revoked) signs you out and returns you to the login screen.

## Where things live

| Path | What |
|---|---|
| `src/lib/api.ts` | The one typed API client. Every screen calls this and nothing else; components never fetch. |
| `src/lib/types.ts` | TypeScript mirrors of `backend/app/shared/schemas.py` / `docs/api-contracts.md`. |
| `src/lib/fixtures/` | Copies of `sample-data/fixtures/`. If the contract changes, recopy them. |
| `src/lib/auth.tsx`, `src/lib/auth-storage.ts` | Session context and persistence. All HTTP still goes through `api.ts`. |
| `src/app/(auth)/{login,signup}` | Signed-out screens. Signup creates the firm and its owner in one step. |
| `src/app/(app)/{upload,review,dashboard,report,settings,profile}` | The signed-in app. The group layout redirects anonymous visitors to `/login`. |
| `src/app/(app)/settings` | API keys: create (raw key shown exactly once), list, revoke — mirroring `/v1/api-keys`. |
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
