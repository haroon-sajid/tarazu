-- Tarazu — AI Audit Assistant: API keys.
--
-- Run this once, after `0002-organizations.sql`, in the Supabase SQL editor.
-- It is idempotent, like the others: re-running it is safe.
--
-- An organization generates a key so its own tooling — n8n, Zapier, a script —
-- can reach Tarazu without a person signing in. A key belongs to exactly one
-- organization and reaches nothing outside it, like the person who created it.
--
-- Two things this file is built around:
--
--   1. **The raw key is never here.** `key_hash` is a SHA-256 digest and
--      `key_prefix` is the key's non-secret head. Nothing stored in this table
--      can be turned back into a working credential.
--   2. **`key_hash` is unreadable to every browser-facing role.** RLS hides
--      other organizations' rows; column privileges hide the digest column even
--      within your own. A leaked anon key gets a list of prefixes and names.

begin;

create table if not exists public.api_keys (
  key_id       text        primary key,
  org_id       uuid        not null references public.organizations (org_id) on delete cascade,
  -- The person accountable for what this key does. Cases it opens are created
  -- by them, and decisions it records are attributed to them.
  created_by   uuid        not null references auth.users (id),
  -- A label the auditor chose, so a key can be recognised months later and
  -- revoked with confidence: 'n8n integration', 'Zapier - monthly export'.
  name         text        not null check (length(trim(name)) between 1 and 100),
  -- 'trz_live_' plus the key's first eight random characters. Not a secret:
  -- this is what the UI shows and what audit_trail records as 'api-key:<prefix>'.
  key_prefix   text        not null,
  -- SHA-256 of the raw key, hex, 64 characters. The key is 128 bits of CSPRNG
  -- output, so there is nothing to brute-force and no reason for a slow KDF.
  key_hash     text        not null unique check (key_hash ~ '^[0-9a-f]{64}$'),
  scopes       text[]      not null
                 check (scopes <@ array['read', 'write']::text[]
                        and array_length(scopes, 1) >= 1),
  last_used_at timestamptz,
  -- Set to revoke. Never unset: a key that has been off may have been turned
  -- off *because it leaked*, and un-revoking would be the wrong tool for
  -- "I was too hasty". Create a new key instead.
  revoked_at   timestamptz,
  created_at   timestamptz not null default now()
);

create index if not exists api_keys_org_idx on public.api_keys (org_id, created_at desc);

-- Authentication hashes the presented key and looks the digest up, on every
-- request that arrives with one. The unique constraint above already indexes
-- this column; the lookup is a single index probe.

-- ---------------------------------------------------------------------------
-- Privileges, before policies
--
-- RLS decides which *rows* you see. It cannot hide a *column*, and `key_hash`
-- is a column no browser should ever read. Column-level privileges can, so the
-- grant below lists the safe columns and omits that one.
--
-- The backend uses the service role, which needs the digest to authenticate a
-- key, and which bypasses RLS anyway.
-- ---------------------------------------------------------------------------

revoke all on public.api_keys from anon, authenticated;

grant select (key_id, org_id, created_by, name, key_prefix, scopes,
              last_used_at, revoked_at, created_at)
  on public.api_keys to authenticated;

-- Minting and revoking go through POST/DELETE /v1/api-keys, which the backend
-- serves with the service role. A browser must not be able to insert a key
-- (that is minting a credential) or update one (that is un-revoking it).
grant all on public.api_keys to service_role;

-- Keys are revoked, not deleted, so that audit_trail's 'api-key:<prefix>'
-- entries stay resolvable to a name, a creator, and a date. Nothing
-- browser-facing may delete one; the application has no delete path at all.
revoke delete on public.api_keys from anon, authenticated;

-- ---------------------------------------------------------------------------
-- Row-level security: your organization's keys, and no one else's
-- ---------------------------------------------------------------------------

alter table public.api_keys enable row level security;

drop policy if exists api_keys_org_members on public.api_keys;
create policy api_keys_org_members
  on public.api_keys
  for select
  to authenticated
  using (org_id in (select public.current_user_org_ids()));

-- Deliberately absent for `authenticated`, and must stay absent:
--   create policy ... for insert ...   -- would let a browser mint a key
--   create policy ... for update ...   -- would let a browser un-revoke one
--   create policy ... for delete ...   -- would let a browser erase the record

commit;

-- ===========================================================================
-- Check it, in a transaction you roll back:
--
--   begin;
--   set local role authenticated;
--   set local request.jwt.claims = '{"sub":"<a-user-uuid>","role":"authenticated"}';
--
--   select key_prefix, name, scopes from public.api_keys;  -- only your firm's
--   select key_hash from public.api_keys;
--   -- ERROR: permission denied for table api_keys
--
--   insert into public.api_keys (key_id, org_id, created_by, name, key_prefix,
--                                key_hash, scopes)
--   values ('AK-forged', '<your-org>', '<you>', 'forged',
--           'trz_live_00000000', repeat('a', 64), array['write']);
--   -- ERROR: permission denied for table api_keys
--   rollback;
-- ===========================================================================
