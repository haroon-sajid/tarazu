# frontend/

**Purpose:** The Next.js and TypeScript web app for auditors. It is the only
client of the `backend/` FastAPI app: upload, the human review screen, the
evidence viewer, the dashboard, analytics, sampling, the assistant, reports, and
settings.

**Stack:** Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS v4,
Recharts, lucide-react.

## Running it

```bash
npm install
npm run dev        # http://localhost:3000
```

With no configuration the app runs in **fixture mode**: every screen is served
from `src/lib/fixtures/` (copies of `sample-data/fixtures/`, which the backend
validates against the real Pydantic schemas). Approve and reject mutate an
in-memory store, so the whole flow demos offline, and the login screen pre-fills
demo credentials that sign in the seeded auditor.

To switch to the live backend, set one line in `.env.local`
(see `.env.example`) and restart the dev server:

```
NEXT_PUBLIC_TARAZU_API_URL=http://localhost:8000
```

In live mode, sign up a firm (or sign in) on `/signup` or `/login`; the session
token is held in localStorage and sent on every request. A 401 mid-session
(token expired or revoked) signs you out and returns you to the login screen.

**Type check and build:**

```bash
npx tsc --noEmit
npm run build      # stop the dev server first: both use .next/
```

## UI conventions

These are project rules, not preferences. The full list is in
[CLAUDE.md](../CLAUDE.md).

- **The UI never computes.** Every number on screen is one the backend
  computed. No summing, averaging, or deriving in the browser.
- **No transform-based motion.** Hover, focus, and press feedback is colour,
  border, shadow, or opacity only: no `hover:scale-*`, no `hover:-translate-*`,
  no tilt or entry animation. An audit tool should feel still. Positional
  transforms that are not effects (a drawer sliding, a toggle knob, centring
  with `-translate-x-1/2`) are fine, as are spinners and opacity pulses.
- **Mobile first, and responsive throughout.** Every screen works from 360px up.
  Wide content (tables, charts, diagrams) scrolls inside its own
  `overflow-x-auto`; the page body never scrolls horizontally.
- **Match strength and extraction confidence are two different columns** with
  two different renderings (a dot meter against an "AI:" pill). Match strength
  comes from the deterministic matcher; extraction confidence from the AI
  reading step. Never merge them: this separation is the core of the product.

## Where things live

### Library

| Path | What |
|---|---|
| `src/lib/api.ts` | The one typed API client. Every screen calls this and nothing else; components never fetch. |
| `src/lib/types.ts` | TypeScript mirrors of `backend/app/shared/schemas.py` and `docs/api-contracts.md`. |
| `src/lib/fixtures/` | Copies of `sample-data/fixtures/`. If the contract changes, recopy them. |
| `src/lib/assistant.ts` | The fixture-mode assistant (keyword routing over the fixture items). Live mode calls `POST /v1/assistant/chat` instead. |
| `src/lib/auth.tsx`, `src/lib/auth-storage.ts` | Session context and persistence. All HTTP still goes through `api.ts`. |
| `src/lib/use-active-case.ts` | The active case, a localStorage selection every screen passes as `?case_id=`. |
| `src/lib/format.ts`, `src/lib/utils.ts` | Money, date, and class-name helpers. Formatting only, never arithmetic. |
| `src/lib/speech.ts` | Browser speech input for the assistant. Optional and progressively enhanced. |

### Screens

| Path | What |
|---|---|
| `src/app/page.tsx`, `src/app/demo/` | The public landing page and the `/demo` playground, rendered from fixtures with no backend call. |
| `src/app/(auth)/{login,signup}` | Signed-out screens. Signup creates the firm and its owner in one step. |
| `src/app/(app)/` | The signed-in app. The group layout redirects anonymous visitors to `/login`. |
| `(app)/upload` | Opens a period and uploads the documents. Progress is the background job's own `progress` and `step`, polled from `/v1/jobs/{id}`. |
| `(app)/review` | The human review queue: approve or reject each item, with the evidence viewer beside it. |
| `(app)/documents` | Side-by-side audit: the real page (`/v1/documents/{id}/pages/{n}`) with every extracted value boxed at its provenance. |
| `(app)/dashboard` | Case summary, status and confidence counts, and the Benford distribution. |
| `(app)/analytics` | Sales analytics: upload the client's sales export in any supported format, then the deterministic readout (monthly revenue, product and region breakdowns, top customers, anomalies) with the data-quality report and a workbook download. |
| `(app)/assistant` | Ask Tarazu: grounded answers with confidence, citations, and the computed facts behind them. |
| `(app)/sampling` | Draw a reproducible sample (random, monetary unit, high value) for substantive testing. |
| `(app)/cases`, `(app)/clients`, `(app)/clients/[clientId]` | The case list, the firm's recurring clients, and one client with its periods and rule thresholds. |
| `(app)/report` (aliased as `/reports`) | Generate the PDF and Excel report and browse the append-only history of generations (`/v1/reports`). |
| `(app)/audit-trail` | The case-wide trail, filterable by actor and action. |
| `(app)/queries` | Evidence requests: ask the client, record the response, resolve or cancel. |
| `(app)/insights`, `(app)/compare` | The firm across all its cases, and two periods side by side. |
| `(app)/business` | The owner-facing plain-language view of one engagement. |
| `(app)/profile` | The identity every decision is recorded against, with the working record. |
| `(app)/settings/*` | `general`, `profile`, `account`, `api-keys`, `members`, `branding`, `compliance`, `environment`, plus `webhooks`, `notifications`, and `integrations`, which are static "planned" copy for the deferred Phase 3. |

### Components

| Path | What |
|---|---|
| `src/components/ui/` | The primitives: button, card, badge, input, dialog, tooltip, skeleton, and the empty, loading, and error states. |
| `src/components/layout/` | Sidebar, header, notifications, profile menu, and the workspace shell. |
| `src/components/review/evidence-viewer.tsx` | The slide-over: comparison, provenance highlight on the real page, flags, audit history. |
| `src/components/documents/schematic-page.tsx` | `DocumentPage` (real page image with bbox overlays, schematic fallback) and `SchematicSheet` (the ledger as rows). |
| `src/components/analytics/` | Revenue, product, and region charts, the customer table, summary cards, and the anomaly list. |
| `src/components/dashboard/` | The Benford chart and the first-run checklist. |
| `src/components/demo/` | The `/demo` playground: its own dashboard, review queue, evidence panel, and the boundary that keeps it backend-free. |
| `src/components/upload/drop-zone.tsx` | The file picker used by upload and by the analytics sales-data upload. |

**Inputs:** User interactions, data from the `backend/` FastAPI app (the only
backend it talks to), and the Supabase auth session.

**Outputs:** HTTP requests to the backend API and the rendered UI.

**Must never do:**

- Never call backend module internals or the Qwen API directly. All backend access goes through the backend's public `/v1/...` API.
- Never perform matching, math, or red-flag rule logic client-side. The UI only displays server results.
- Never auto-approve items. Every approve or reject is an explicit user click.
- Never hold secrets beyond `NEXT_PUBLIC_*` variables.
