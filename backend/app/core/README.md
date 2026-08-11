# backend/app/core/

**Purpose:** Cross-cutting infrastructure shared by all modules: configuration
loading, Supabase JWT auth verification, the Supabase client (Postgres, Storage),
and the append-only audit-trail writer.

**Inputs:** Environment variables (names in `.env.example`); incoming request auth
headers.
**Outputs:** Config objects, verified auth context, Supabase client instances,
audit-trail write functions — consumed by `main.py` and modules.

**Does NOT belong here:**
- Business logic of any kind — no extraction, matching, rules, chat, or report code.
- AI/LLM clients (those live inside `modules/extraction/` and `modules/assistant/` only).
- Module-specific config (belongs to the module, prefixed per `.env.example`).
- Any code that updates or deletes audit-trail records — the trail is append-only.
