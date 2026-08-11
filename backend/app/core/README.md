# backend/app/core/

**Purpose:** Cross-cutting infrastructure shared by all modules: configuration
loading, Supabase JWT verification, the Supabase client (Postgres and Storage),
and the append-only audit-trail writer.

**Inputs:** Environment variables (names listed in `.env.example`) and incoming
request auth headers.

**Outputs:** Config objects, verified auth context, Supabase client instances,
and audit-trail write functions, consumed by `main.py` and the modules.

**Does not belong here:**

- Business logic of any kind. No extraction, matching, rules, chat, or report code.
- AI or LLM clients; those live inside `modules/extraction/` and `modules/assistant/` only.
- Module-specific config, which belongs to the module and is prefixed per `.env.example`.
- Any code that updates or deletes audit-trail records. The trail is append-only.
