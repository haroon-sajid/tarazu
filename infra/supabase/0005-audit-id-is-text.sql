-- Tarazu — AI Audit Assistant: make `audit_trail.audit_id` text.
--
-- Run this once, after `0004-revoke-truncate.sql`. Idempotent, like the others.
--
-- ===========================================================================
-- What was wrong
--
-- `schema.sql` declared `audit_id uuid primary key default gen_random_uuid()`,
-- but the application mints `AUD-<12 hex>` — and always supplies it, so the
-- default never applied. Every audit insert against Postgres failed with
--
--   invalid input syntax for type uuid: "AUD-526841aceb28"
--
-- which meant reliability rule 5 was not merely unenforced on Supabase, it was
-- impossible: no action could be recorded at all. It went unnoticed because the
-- test suite runs on SQLite, where `audit_id` is text and the ids fit.
--
-- `uuid` was the odd one out rather than the app being wrong. Every other
-- identifier in this schema is prefixed text — `case_id` (`CASE-…`),
-- `review_item_id` (`CASE-…-RI-0001`), `flag_id` (`FLG-…`), `document_id`
-- (`DOC-BNK-…`), `key_id` (`AK-…`) — because a human reading a trail should be
-- able to tell what kind of thing an id names. This makes `audit_id` agree.
--
-- Widening the column does not touch the hardening: no privilege is granted,
-- no policy is added, and both triggers are left exactly as they are. ALTER
-- TABLE is DDL and issues no row UPDATE, so the append-only trigger neither
-- fires nor needs an exemption — the same reasoning as the `add column` in
-- `0002-organizations.sql`.
-- ===========================================================================

begin;

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'audit_trail'
      and column_name = 'audit_id'
      and data_type = 'uuid'
  ) then
    -- The default has to go first: `gen_random_uuid()` is not a text expression,
    -- and the column type cannot change out from under it.
    alter table public.audit_trail alter column audit_id drop default;
    alter table public.audit_trail
      alter column audit_id type text using audit_id::text;
  end if;
end;
$$;

-- No default is restored. The application supplies `audit_id` on every insert,
-- and a database-side default would quietly paper over a writer that forgot to.

commit;

-- ===========================================================================
-- Check it:
--
--   select data_type, column_default
--     from information_schema.columns
--    where table_schema = 'public'
--      and table_name = 'audit_trail'
--      and column_name = 'audit_id';
--   -- text, null
--
--   insert into public.audit_trail (audit_id, org_id, case_id, actor_type,
--                                   actor_id, action)
--   values ('AUD-000000000001', '00000000-0000-4000-8000-0000000000d0',
--           'CASE-TEST', 'system', 'schema-check', 'case_created');
--   -- succeeds
-- ===========================================================================
