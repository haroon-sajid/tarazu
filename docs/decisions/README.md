# docs/decisions/ — Architecture Decision Records

**Purpose:** One file per significant architectural decision, numbered and
immutable once accepted. To change an accepted decision, write a new ADR that
supersedes it instead of editing the original.

**Format:** `NNNN-short-kebab-title.md` (for example
`0001-use-qwen-vl-for-extraction.md`) with four sections: Context, Decision,
Consequences, and Status.

**Does not belong here:** General documentation (`docs/`), API contracts
(`docs/api-contracts.md`), meeting notes, or code.

## Recorded

| # | Decision |
|---|---|
| [0001](0001-http-routers-live-in-app-api.md) | HTTP routers live in `app/api/`, not inside the modules |
| [0002](0002-two-backing-stores-behind-one-repository.md) | Two backing stores behind one repository interface |
| [0003](0003-tenancy-is-an-org-id-column-and-two-enforcement-layers.md) | Tenancy is an `org_id` column, enforced twice |
