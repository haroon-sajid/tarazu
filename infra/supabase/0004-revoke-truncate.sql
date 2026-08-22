-- Tarazu — AI Audit Assistant: close the TRUNCATE hole.
--
-- Run this once, after `0003-api-keys.sql`. Idempotent, like the others.
--
-- ===========================================================================
-- What was wrong
--
-- Supabase's default grant is `grant all on all tables in schema public to
-- anon, authenticated, service_role`. ALL includes TRUNCATE, and **TRUNCATE is
-- not covered by row-level security**: RLS filters rows for SELECT, INSERT,
-- UPDATE, and DELETE, but a TRUNCATE removes every row in the table without
-- consulting a policy. It is gated by the table privilege alone.
--
-- Two consequences, both bad:
--
--   1. `anon` is the role a browser holds when it presents the publishable key,
--      which is public by design. Any visitor could have run
--      `truncate public.cases cascade` and emptied every firm's data at once.
--      Tenant isolation is about who can see which rows; TRUNCATE does not read
--      rows, so none of it applied.
--
--   2. `audit_trail` was wide open to the same thing. The hardening in
--      `schema.sql` revoked UPDATE and DELETE and installed a `before update or
--      delete` trigger — but TRUNCATE is neither of those statements, and the
--      row-level trigger never fires for it (TRUNCATE fires a STATEMENT-level
--      `before truncate` trigger, which did not exist). Reliability rule 5 was
--      one statement away from being undone, by the most public role there is.
--
-- Verified against a live project before writing this: `set local role anon;
-- truncate public.audit_trail;` succeeded, inside a transaction that was rolled
-- back. See `verify-audit-immutability.sql`, which now checks for it.
-- ===========================================================================

begin;

-- ---------------------------------------------------------------------------
-- (1) Privileges. No browser-facing role may TRUNCATE anything.
--
-- `service_role` keeps TRUNCATE on the ordinary data tables: it is a server-side
-- key that never reaches a browser, and an operator resetting a test project is
-- a legitimate thing to be able to do. `audit_trail` is the exception and is
-- handled below — there, the whole point is that *no* role can.
-- ---------------------------------------------------------------------------

do $$
declare
  target text;
begin
  foreach target in array array['cases', 'documents', 'extractions',
                                'review_items', 'flags', 'benford_results',
                                'organizations', 'organization_members',
                                'api_keys', 'audit_trail']
  loop
    execute format('revoke truncate on public.%I from anon, authenticated', target);
  end loop;
end;
$$;

-- ---------------------------------------------------------------------------
-- (2) audit_trail: TRUNCATE joins UPDATE and DELETE as something no role the
--     application can authenticate as may do — `service_role` included, for
--     exactly the reason the original REVOKE named. `service_role` bypasses
--     row-level security; it does not bypass table privileges.
-- ---------------------------------------------------------------------------

revoke truncate on public.audit_trail from anon, authenticated, service_role;

-- Re-assert the original two, so this file states the whole rule in one place.
revoke update, delete on public.audit_trail from anon, authenticated, service_role;
grant insert, select on public.audit_trail to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- (3) The backstop trigger, matching the one for UPDATE and DELETE.
--
-- Privileges can be granted back — and on this project they had been, by a
-- default grant nobody typed. A trigger refuses the statement itself, for every
-- role including the table owner and a superuser.
--
-- TRUNCATE cannot have a FOR EACH ROW trigger; it is FOR EACH STATEMENT, which
-- is why the existing trigger did not cover it and why this is a second one
-- rather than a widened first.
-- ---------------------------------------------------------------------------

drop trigger if exists audit_trail_no_truncate on public.audit_trail;
create trigger audit_trail_no_truncate
  before truncate on public.audit_trail
  for each statement execute function public.audit_trail_is_append_only();

-- Deliberately absent, and must stay absent, now including the third:
--   create policy ... for update ...
--   create policy ... for delete ...
--   grant truncate on public.audit_trail to ...

commit;

-- ===========================================================================
-- Check it, in a transaction you roll back:
--
--   begin;
--   insert into public.audit_trail (org_id, case_id, actor_type, actor_id, action)
--   values ('00000000-0000-4000-8000-0000000000d0', 'CASE-TEST', 'system',
--           'schema-check', 'case_created');
--
--   set local role anon;
--   truncate public.cases cascade;
--   -- ERROR: permission denied for table cases
--   reset role;
--
--   truncate public.audit_trail;
--   -- ERROR: audit_trail is append-only: TRUNCATE is not permitted
--   rollback;
-- ===========================================================================
