# infra/

**Purpose:** Deployment configuration and infrastructure-as-code placeholders:
container orchestration, environments, CI/CD definitions, and Supabase project
configuration.

**Inputs:** The frontend and backend Dockerfiles and their environment
requirements (variable names in `.env.example`).

**Outputs:** Deployable environment definitions for two deployables:
`frontend/` and the `backend/` modular monolith. If a module is later extracted
into its own service, it gets its own deployment definition here.

**Does not belong here:** Application code, secrets or filled-in credentials
(names only; values come from a secret manager), and local-only development
scripts (`scripts/`).

Empty for now. This folder will be filled in once deployment targets are chosen
(see `docs/decisions/`).
