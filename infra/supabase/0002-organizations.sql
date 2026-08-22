-- Tarazu — AI Audit Assistant: multi-tenancy migration.
--
-- Run this once, after `schema.sql`, in the Supabase SQL editor.
-- It is idempotent, like `schema.sql`: re-running it is safe.
--
-- What it does:
--   1. Adds `organizations` and `organization_members`. A tenant is one
--      accounting firm; membership is the only thing that grants access.
--   2. Adds `org_id` to every tenant-owned table and backfills existing rows
--      into a default organization owned by the current demo user.
--   3. Replaces the "any authenticated user" row-level security policies with
--      membership-scoped ones.
--
-- What it deliberately does NOT do: weaken the audit trail. `audit_trail` gains
-- a tenant column and a narrower SELECT policy, and nothing else changes. The
-- REVOKE stands, there is still no UPDATE policy and no DELETE policy, and the
-- `before update or delete` trigger from `schema.sql` is left exactly as it is.
-- Note that the backfill below uses `add column ... default`, never an UPDATE:
-- an UPDATE on that table is refused by its own trigger, correctly, and this
-- migration does not ask for an exemption from it.

begin;

-- ---------------------------------------------------------------------------
-- 1. The tenancy tables
-- ---------------------------------------------------------------------------

create table if not exists public.organizations (
  org_id     uuid primary key default gen_random_uuid(),
  name       text        not null check (length(trim(name)) > 0),
  created_at timestamptz not null default now()
);

create table if not exists public.organization_members (
  org_id     uuid        not null references public.organizations (org_id) on delete cascade,
  user_id    uuid        not null references auth.users (id) on delete cascade,
  role       text        not null default 'member' check (role in ('owner', 'member')),
  created_at timestamptz not null default now(),
  primary key (org_id, user_id)
);

create index if not exists organization_members_user_idx
  on public.organization_members (user_id, created_at);

-- A user's organizations, as a set. Every policy below is written against this
-- rather than against a join, so "can this caller see this row" is one
-- definition in one place and reads the same on every table.
--
-- SECURITY DEFINER so the lookup itself is not subject to the RLS policy on
-- `organization_members` — without it the membership policy would have to
-- consult itself to decide whether you may consult it.
create or replace function public.current_user_org_ids()
returns setof uuid
language sql
stable
security definer
set search_path = public
as $$
  select org_id from public.organization_members where user_id = auth.uid();
$$;

revoke all on function public.current_user_org_ids() from public;
grant execute on function public.current_user_org_ids() to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 2. The default organization, and the backfill
--
-- The same id as `DEFAULT_ORG_ID` in backend/app/core/config.py. Existing rows
-- predate tenancy, so they all belong to the one firm that has been using this
-- database: the demo auditor's.
-- ---------------------------------------------------------------------------

insert into public.organizations (org_id, name)
values ('00000000-0000-4000-8000-0000000000d0', 'Tarazu Demo Firm')
on conflict (org_id) do nothing;

-- Everyone who has created a case so far owns the default organization.
insert into public.organization_members (org_id, user_id, role)
select distinct '00000000-0000-4000-8000-0000000000d0'::uuid, created_by, 'owner'
from public.cases
on conflict (org_id, user_id) do nothing;

-- `add column ... default` fills the existing rows as DDL, without issuing a
-- row UPDATE. That matters for `audit_trail`, whose trigger refuses UPDATE for
-- every role including the owner; it is used on the other tables too so the
-- backfill is one statement per table rather than two.
do $$
declare
  target text;
begin
  foreach target in array array['cases', 'documents', 'extractions',
                                'review_items', 'flags', 'benford_results',
                                'audit_trail']
  loop
    execute format(
      'alter table public.%I add column if not exists org_id uuid not null '
      'default ''00000000-0000-4000-8000-0000000000d0''::uuid', target);
    -- New rows must say which firm they belong to. Dropping the default after
    -- the backfill is what turns "defaults to the demo firm" into "must be
    -- stated", so a future insert that forgets `org_id` fails loudly.
    execute format('alter table public.%I alter column org_id drop default', target);
    execute format('create index if not exists %I on public.%I (org_id)',
                   target || '_org_idx', target);
  end loop;
end;
$$;

-- Point the new column at a real organization. Deliberately not on
-- `audit_trail`: that table has no foreign keys at all, so that nothing it
-- describes can be deleted out from under it, and so it can outlive the case,
-- the firm, and the account it records.
do $$
declare
  target text;
begin
  foreach target in array array['cases', 'documents', 'extractions',
                                'review_items', 'flags', 'benford_results']
  loop
    if not exists (
      select 1 from pg_constraint
      where conrelid = format('public.%I', target)::regclass
        and conname = target || '_org_fkey'
    ) then
      execute format(
        'alter table public.%I add constraint %I foreign key (org_id) '
        'references public.organizations (org_id)', target, target || '_org_fkey');
    end if;
  end loop;
end;
$$;

-- `flags.flag_id` is minted by `rules/`, which numbers flags within the case it
-- was given, so it is unique per case and no wider. As a bare primary key it
-- would let one firm's upload replace a row belonging to another firm that
-- happened to raise its first flag too — a cross-tenant write, through a table
-- nobody reads. Widen the key to the tenant and the case.
do $$
begin
  if exists (
    select 1
    from pg_constraint
    where conrelid = 'public.flags'::regclass
      and contype = 'p'
      and conname = 'flags_pkey'
      and array_length(conkey, 1) = 1
  ) then
    alter table public.flags drop constraint flags_pkey;
    alter table public.flags add constraint flags_pkey
      primary key (org_id, case_id, flag_id);
  end if;
end;
$$;

alter table public.organizations        enable row level security;
alter table public.organization_members enable row level security;

-- ---------------------------------------------------------------------------
-- 3. Row-level security, scoped to membership
--
-- Replaces the `%I_authenticated` policies from schema.sql, which granted every
-- authenticated user every row. A row whose `org_id` is not in your
-- `organization_members` is now invisible rather than forbidden — no policy
-- returns it, so a cross-tenant read finds nothing and the API answers 404.
-- ---------------------------------------------------------------------------

do $$
declare
  target text;
begin
  foreach target in array array['cases', 'documents', 'extractions',
                                'review_items', 'flags', 'benford_results']
  loop
    -- The permissive hackathon policy. Gone.
    execute format('drop policy if exists %I on public.%I',
                   target || '_authenticated', target);
    execute format('drop policy if exists %I on public.%I',
                   target || '_org_members', target);
    execute format(
      'create policy %I on public.%I for all to authenticated '
      'using (org_id in (select public.current_user_org_ids())) '
      'with check (org_id in (select public.current_user_org_ids()))',
      target || '_org_members', target);
  end loop;
end;
$$;

-- Your own organization, and the members of it.

drop policy if exists organizations_own on public.organizations;
create policy organizations_own
  on public.organizations
  for select
  to authenticated
  using (org_id in (select public.current_user_org_ids()));

drop policy if exists organization_members_own on public.organization_members;
create policy organization_members_own
  on public.organization_members
  for select
  to authenticated
  using (org_id in (select public.current_user_org_ids()));

-- Creating an organization and joining a user to it is what `POST
-- /v1/auth/signup` does, through the backend and the service role. There is
-- deliberately no insert policy for `authenticated`: a browser must not be able
-- to add itself to a firm.

-- ===========================================================================
-- 4. audit_trail — narrower to read, unchanged in every other respect
--
-- Re-stated in full so this file can be read on its own and so nothing here can
-- be mistaken for a relaxation. Compare against the hardening section of
-- schema.sql: the REVOKE is identical, the trigger is untouched, and the set of
-- policies still contains no UPDATE and no DELETE.
-- ===========================================================================

-- Unchanged, and re-asserted because it is the layer that matters most:
-- `service_role` bypasses RLS but does not bypass table privileges.
revoke update, delete on public.audit_trail from anon, authenticated, service_role;
grant insert, select on public.audit_trail to authenticated, service_role;

alter table public.audit_trail enable row level security;
alter table public.audit_trail force  row level security;

-- INSERT stays open to any member: writing to the trail must never be the thing
-- that fails, and the backend supplies the org_id from the caller's membership.
drop policy if exists audit_trail_insert_only on public.audit_trail;
create policy audit_trail_insert_only
  on public.audit_trail
  for insert
  to authenticated, service_role
  with check (true);

-- SELECT is now scoped: you read your own firm's trail, not everyone's.
drop policy if exists audit_trail_select_only on public.audit_trail;
create policy audit_trail_select_only
  on public.audit_trail
  for select
  to authenticated
  using (org_id in (select public.current_user_org_ids()));

-- The backend reads the trail on behalf of a caller it has already scoped, and
-- the service role bypasses RLS in any case; this policy is stated so that the
-- table's policy set is complete and explicit rather than partly implicit.
drop policy if exists audit_trail_select_service on public.audit_trail;
create policy audit_trail_select_service
  on public.audit_trail
  for select
  to service_role
  using (true);

-- Deliberately absent, here as in schema.sql, and must stay absent:
--   create policy ... for update ...
--   create policy ... for delete ...
--
-- The trigger `audit_trail_no_update_or_delete` from schema.sql is not dropped,
-- not replaced, and not disabled by this migration.

commit;

-- ===========================================================================
-- Verify the isolation, in a transaction you roll back:
--
--   begin;
--   set local role authenticated;
--   set local request.jwt.claims = '{"sub":"<user-b-uuid>","role":"authenticated"}';
--   select count(*) from public.cases;        -- only user B's firm's cases
--   select count(*) from public.audit_trail;  -- only user B's firm's trail
--   update public.audit_trail set detail = 'tampered';
--   -- ERROR: audit_trail is append-only: UPDATE is not permitted
--   rollback;
--
-- `infra/supabase/verify-audit-immutability.sql` proves the append-only half of
-- that in full.
-- ===========================================================================
