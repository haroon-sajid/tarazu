-- Tarazu — AI Audit Assistant: organization invitations.
-- Run after 0002-organizations.sql. Idempotent.
--
-- An open door into one organization: the owner cuts a single-use code;
-- whoever presents it at POST /v1/auth/signup joins that org with the
-- invitation's role instead of founding a new firm. `accepted_at` closes
-- the door; deleting the row revokes it.
--
-- Backend-only, like api_keys and user_profiles: browser-facing roles get
-- nothing, and RLS with no policies keeps it that way.

create table if not exists public.org_invitations (
  invite_id   text primary key,
  org_id      uuid not null references public.organizations (org_id) on delete cascade,
  email       text not null,
  role        text not null default 'member' check (role in ('owner', 'member')),
  code        text not null unique,
  created_by  uuid not null,
  created_at  timestamptz not null,
  accepted_at timestamptz,
  accepted_by uuid
);

create index if not exists org_invitations_org_idx
  on public.org_invitations (org_id, created_at desc);

revoke all on public.org_invitations from anon, authenticated;

alter table public.org_invitations enable row level security;
-- No policies on purpose: only the service role (which bypasses RLS) reads
-- or writes invitations.
