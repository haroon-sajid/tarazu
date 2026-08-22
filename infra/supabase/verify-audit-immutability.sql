-- Prove the audit trail is immutable, in the real database.
--
-- Run this in the Supabase SQL editor after every migration in this directory.
-- Every UPDATE, DELETE, and TRUNCATE below must fail. If any of them succeeds,
-- the hardening did not apply and reliability rule 5 is a claim rather than a
-- guarantee.
--
-- **Insert the row in step 1 first.** The UPDATE and DELETE protections come
-- from a FOR EACH ROW trigger, which cannot fire over zero rows — on an empty
-- table those statements succeed as no-ops and look like a failure of the
-- hardening when they are nothing of the kind. TRUNCATE is statement-level and
-- is refused either way.
--
-- This is worth running on camera. "We did not just promise the trail is
-- immutable, we revoked the permission — watch" is a better answer than a slide.

-- ---------------------------------------------------------------------------
-- 1. A row goes in. This must succeed.
-- ---------------------------------------------------------------------------

insert into public.audit_trail (org_id, case_id, actor_type, actor_id, action, item_id, detail)
values ('00000000-0000-4000-8000-0000000000d0', 'CASE-IMMUTABILITY-CHECK',
        'system', 'verify-audit-immutability.sql',
        'case_created', null, 'inserted by the verification script');

select 'INSERT succeeded, as it should' as step,
       count(*) as rows_for_this_case
from public.audit_trail
where case_id = 'CASE-IMMUTABILITY-CHECK';

-- ---------------------------------------------------------------------------
-- 2. Try to change it. Every one of these must raise.
--    Run them one at a time — each aborts its transaction.
-- ---------------------------------------------------------------------------

-- ERROR expected: audit_trail is append-only: UPDATE is not permitted
update public.audit_trail
   set detail = 'tampered'
 where case_id = 'CASE-IMMUTABILITY-CHECK';

-- ERROR expected: audit_trail is append-only: UPDATE is not permitted
update public.audit_trail
   set actor_id = 'someone-else'
 where case_id = 'CASE-IMMUTABILITY-CHECK';

-- ERROR expected: audit_trail is append-only: DELETE is not permitted
delete from public.audit_trail
 where case_id = 'CASE-IMMUTABILITY-CHECK';

-- ERROR expected: audit_trail is append-only: TRUNCATE is not permitted
truncate public.audit_trail;

-- The one that got away for a while. TRUNCATE is a third statement, not a
-- flavour of DELETE: row-level security does not apply to it, and the FOR EACH
-- ROW trigger above does not fire for it. `0004-revoke-truncate.sql` revoked the
-- privilege and added a statement-level trigger. Before that migration this
-- line succeeded — as `anon`, from any browser holding the publishable key.

-- ---------------------------------------------------------------------------
-- 3. Confirm the privileges really are gone.
--    Every row this returns should read `false`.
-- ---------------------------------------------------------------------------

select grantee,
       has_table_privilege(grantee, 'public.audit_trail', 'UPDATE')   as can_update,
       has_table_privilege(grantee, 'public.audit_trail', 'DELETE')   as can_delete,
       has_table_privilege(grantee, 'public.audit_trail', 'TRUNCATE') as can_truncate,
       has_table_privilege(grantee, 'public.audit_trail', 'INSERT')   as can_insert,
       has_table_privilege(grantee, 'public.audit_trail', 'SELECT')   as can_select
  from (values ('anon'), ('authenticated'), ('service_role')) as roles(grantee);

-- Expected:
--   grantee        | can_update | can_delete | can_truncate | can_insert | can_select
--   ---------------+------------+------------+--------------+------------+-----------
--   anon           | false      | false      | false        | false      | false
--   authenticated  | false      | false      | false        | true       | true
--   service_role   | false      | false      | false        | true       | true
--
-- The service_role row is the one that matters. It bypasses row-level
-- security, so RLS alone would not stop a leaked service key rewriting
-- history — but BYPASSRLS does not bypass table privileges, so the REVOKE
-- stops it and RLS could not.

-- ---------------------------------------------------------------------------
-- 3b. And confirm no browser-facing role can TRUNCATE anything else either.
--     RLS scopes rows per organization; it does not apply to TRUNCATE, so a
--     single statement would otherwise have emptied every firm's data at once.
--     Every value here should read `false`.
-- ---------------------------------------------------------------------------

select tablename,
       has_table_privilege('anon',          'public.' || tablename, 'TRUNCATE') as anon,
       has_table_privilege('authenticated', 'public.' || tablename, 'TRUNCATE') as authenticated
  from unnest(array['cases', 'documents', 'extractions', 'review_items', 'flags',
                    'benford_results', 'audit_trail', 'organizations',
                    'organization_members', 'api_keys']) as tablename
 order by tablename;

-- ---------------------------------------------------------------------------
-- 4. Confirm there is no update or delete policy, and never was one.
-- ---------------------------------------------------------------------------

select policyname, cmd, roles
  from pg_policies
 where schemaname = 'public' and tablename = 'audit_trail'
 order by policyname;

-- Expected three rows after `0002-organizations.sql`: audit_trail_insert_only
-- (INSERT), audit_trail_select_only (SELECT, scoped to your organization), and
-- audit_trail_select_service (SELECT, service_role). Anything with cmd = UPDATE
-- or DELETE is a regression and must be dropped.

-- ---------------------------------------------------------------------------
-- 5. Confirm both triggers are armed.
--
-- Query pg_trigger, not information_schema.triggers: the latter follows the SQL
-- standard, which has no TRUNCATE trigger, so it silently omits the one added by
-- 0004 — the very one worth checking for.
-- ---------------------------------------------------------------------------

select tgname, tgenabled
  from pg_trigger
 where tgrelid = 'public.audit_trail'::regclass
   and not tgisinternal
 order by tgname;

-- Expected both, tgenabled = 'O' (enabled):
--   audit_trail_no_truncate           (statement-level, BEFORE TRUNCATE)
--   audit_trail_no_update_or_delete   (row-level, BEFORE UPDATE OR DELETE)
--
-- This is the layer that also stops the table owner and a superuser, which
-- neither the REVOKE nor RLS does on their own.

-- ---------------------------------------------------------------------------
-- 6. Clean-up note
--
-- There is none, and that is the point: the check row cannot be deleted. It
-- stays in the trail forever, which is exactly the behaviour being verified.
-- Filter it out with `where case_id <> 'CASE-IMMUTABILITY-CHECK'` if it is in
-- the way.
-- ---------------------------------------------------------------------------
