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
| [0004](0004-tarazu-is-an-audit-layer-not-a-system-of-record.md) | Tarazu is an audit layer, not a system of record |
| [0005](0005-recurring-clients-and-periods-replace-one-off-cases.md) | Recurring clients and periods replace one-off cases (proposed; Phase 1) |
| [0006](0006-ask-tarazu-computes-in-code-and-the-model-only-phrases.md) | Ask Tarazu computes in code; the model only phrases |
