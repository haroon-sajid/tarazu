# infra/

**Purpose:** Deployment configuration and Infrastructure-as-Code placeholders:
container orchestration, environments, CI/CD definitions, Supabase project config.

**Inputs:** The frontend and backend Dockerfiles and env requirements (names in
`.env.example`).
**Outputs:** Deployable environment definitions for two deployables: `frontend/`
and the `backend/` modular monolith. If a module is later extracted into its own
service, it gets its own deployment definition here.

**Does NOT belong here:** Application code, secrets or filled-in credentials
(names only, values come from a secret manager), local-only dev scripts (→ `scripts/`).

Empty for now — to be filled when deployment targets are chosen (see `docs/decisions/`).
