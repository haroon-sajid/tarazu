Dash cleanup — all pages read naturally now
Every em dash in user-visible text is gone — rewritten into normal punctuation (periods, commas, colons, or parentheses), not just swapped for another dash. That covered 60+ visible strings: page descriptions, tooltips, dialog copy, empty states, the assistant's canned replies (English and Urdu), error messages, and the one backend-served string ("Save this key now: it is shown once…"). Also:

Date ranges now read "01 Jun 2026 to 30 Jun 2026" instead of using a dash.
Empty table cells show a simple "-" instead of the long "—".
The login page's principles list uses "•" bullets.
The only survivors are the official brand title "Tarazu — AI Audit Assistant" (browser tab + logo tooltip, which CLAUDE.md's naming convention mandates) and invisible code comments. A final scan confirmed zero non-comment occurrences beyond those.
Profile extended with the template's content — same design as ours
I took the sections from that template and mapped them to what an audit product should actually hold, using only our existing components (Inputs, a new matching Select, and a live Toggle styled identically to the existing switches):

Settings → Profile now has four grouped sections in the same style:

Identity — full name, email (read-only)
Personal — gender, date of birth, location, phone (two-column grid)
Professional — job title, license / membership number (ICAP/ACCA — the audit-world equivalent of the template's domain section)
Preferences — explanation language (English / اردو) and three working notification toggles (case ready, high-severity flag, weekly summary), honestly noted as "saved now, activate when email delivery ships"
Your profile page shows the same data as read-only fact rows in its existing Section style, plus a notifications summary line.

Backend is real, not cosmetic: all fields live in GET/PUT /v1/profile with validation (language must be en/ur, dates must parse, sensible toggle defaults), stored in both SQLite and Supabase — including an additive column migration so your existing database upgraded in place, which I proved live: saved name/location/license/Urdu/DOB/digest through the API, read them back correctly, then reset it clean for you. All 281 backend tests pass, frontend typechecks, both pages serve.

d:\New folder\tarazu\backend\app\dashboard_metrics.py
now let me know where i can deploy this freely because our database is already supabase and we are using that locally as well
Here's the free deployment stack that fits this project exactly, since you're already on Supabase:

Recommended: Vercel + Render + Supabase (all free)
Piece	Where	Free tier reality
frontend/ (Next.js 15)	Vercel (Hobby)	Genuinely free, fast, zero config for Next.js
backend/ (FastAPI)	Render (free web service)	Free 750 hrs/month, but sleeps after ~15 min idle — first request after sleep takes 30–60 s to wake
Postgres + auth + storage	Supabase (you have it)	Free projects pause after ~7 days of inactivity — one click in the dashboard restores them
This split works because your architecture already matches it: the frontend only talks to NEXT_PUBLIC_TARAZU_API_URL, and the backend flips to Supabase mode purely from env vars.

Concrete steps for this repo
1. Prepare Supabase (one time) — in the SQL editor, run in order: infra/supabase/schema.sql, 0002-organizations.sql, 0003-api-keys.sql, 0004-user-profiles.sql, 0005-org-invitations.sql. Then seed from your machine with the Supabase vars temporarily uncommented in .env: python scripts/seed_demo_user.py then python scripts/seed_demo_case.py (they auto-pick Supabase when SUPABASE_URL is set).

2. Render (backend) — new Web Service from your GitHub repo: root directory backend, build pip install -r requirements.txt, start uvicorn app.main:app --host 0.0.0.0 --port $PORT. Environment variables: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET, SUPABASE_STORAGE_BUCKET, DEMO_MODE=true, DEFAULT_ORG_ID/DEFAULT_ORG_NAME, and — important — BACKEND_ALLOWED_ORIGINS=https://your-app.vercel.app (CORS will silently break the frontend if you forget this). Never set SUPABASE_DB_URL there; only the schema script needs it, and only locally.

3. Vercel (frontend) — import the repo, set root directory to frontend, add one env var: NEXT_PUBLIC_TARAZU_API_URL=https://your-service.onrender.com. Done.

4. The sleep workaround — for a demo/judging day, ping the backend's /health every ~10 minutes with a free monitor (UptimeRobot or cron-job.org) so it never cold-starts on stage.

Alternatives, honestly rated
Hugging Face Spaces (Docker space) — a solid free FastAPI host with no card required; sleeps after long inactivity. Good backup if Render annoys you.
Google Cloud Run — the best free tier technically (scale-to-zero, ~2M requests/month, tiny cold starts), but requires a credit card and a Dockerfile.
Koyeb — one free small service, scale-to-zero; fine.
Avoid assuming free: Railway (trial credit only) and Fly.io (no free tier for new accounts anymore).
One caution before you push: your repo's .env with the real service-role key is gitignored — verify the repo you connect to Render/Vercel is clean (git ls-files | findstr .env should show only .env.example files). If that key was ever committed historically, rotate it in Supabase first.

If you want, I can prep the deploy files (render.yaml, a backend Dockerfile for the Cloud Run/HF option, and a deployment section in the README) so it's a two-click setup — say the word.