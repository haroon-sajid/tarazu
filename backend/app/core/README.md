# backend/app/core/

**Purpose:** Cross-cutting infrastructure shared by all modules: configuration
loading, access-token verification, API-key minting and recognition, the two
`CaseRepository` implementations (Supabase Postgres and Storage; local SQLite and
the filesystem), the background job runner behind `POST /v1/upload?background=true`,
and the append-only audit-trail writer.

**Inputs:** Environment variables (names listed in `.env.example`) and incoming
request auth headers.

**Outputs:** Config objects, verified auth context, repository and document-store
instances, and audit-trail write functions, consumed by `app/api/` and the modules.

**Tenancy:** a tenant is one accounting firm. Every tenant-scoped repository
method takes `org_id` as its first argument and puts it in the query, so a row
belonging to another firm is *not found* rather than *refused*. Which
organization a request acts inside is decided once, in
`app/api/deps.py::get_current_org`, from the caller's `user_id`, never from
anything the client sends. See
[ADR 0003](../../../docs/decisions/0003-tenancy-is-an-org-id-column-and-two-enforcement-layers.md).

**Does not belong here:**

- Business logic of any kind. No extraction, matching, rules, chat, or report code.
- AI or LLM clients; those live inside `modules/extraction/` and `modules/assistant/` only.
- Module-specific config, which belongs to the module and is prefixed per `.env.example`.
- Any code that updates or deletes audit-trail records. The trail is append-only.
- Any repository read or write that does not filter by `org_id`. The single
  exception is `find_api_key_by_hash`, which is what *establishes* the org for a
  request carrying a key, and is documented as such in `repository.py`.
- Any code that stores, logs, or echoes a raw API key. Only its prefix and its
  SHA-256 digest are ever persisted; `api_keys.py` is the only place a whole key
  exists, and only for the duration of the call that mints it.
