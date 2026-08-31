-- Tarazu — AI Audit Assistant: sales analytics.
--
-- Run after `0006-reports-and-assistant.sql`. Idempotent, like the others.
--
-- Two things:
--
--   1. **`sales_analytics`** — one row per case: the deterministic readout
--      `modules/analytics/` computed over the case's SALES_DATA documents,
--      stored as one jsonb payload. Derived output, exactly like
--      `benford_results`: a re-run replaces the row (the primary key is
--      tenant and case, so one firm's re-run can never touch a row it cannot
--      see), and deleting the case takes it along.
--   2. **One new audit action**, `sales_analytics_run`, so every run — at
--      upload time by the pipeline, or on demand through the API — is on the
--      record. The `audit_trail.action` check constraint is re-stated with
--      the full list. Adding a value to a check constraint is DDL and issues
--      no row UPDATE, so the table's append-only trigger is never asked for
--      an exemption.

begin;

-- ---------------------------------------------------------------------------
-- 1. sales_analytics
-- ---------------------------------------------------------------------------

create table if not exists public.sales_analytics (
  org_id     uuid        not null references public.organizations (org_id),
  -- Cascade, like benford_results: the readout is working data about the case,
  -- not evidence, and is worthless without it. (Reports and the audit trail
  -- are the opposite, which is why they have no such foreign key.)
  case_id    text        not null references public.cases (case_id) on delete cascade,
  payload    jsonb       not null,
  created_at timestamptz not null default now(),
  primary key (org_id, case_id)
);

-- Privileges. No browser-facing role may change or remove a readout: `anon`
-- is the role a browser holds with the publishable key, and UPDATE, DELETE,
-- and TRUNCATE are the three statements that could rewrite what a firm was
-- told. TRUNCATE is in the list because it is a third statement, not a flavour
-- of DELETE — RLS does not apply to it and the row triggers never fire.
revoke update, delete, truncate on public.sales_analytics from anon;

-- The backend reaches this table with the service role, which bypasses RLS
-- but not table privileges. It keeps UPDATE because a re-run replaces the
-- saved readout via upsert on the (org_id, case_id) key.
grant insert, select, update on public.sales_analytics to service_role;

-- RLS, scoped by organization membership like every other tenant-owned table:
-- a row whose `org_id` is not in the caller's `organization_members` is
-- invisible rather than forbidden, so a cross-tenant read finds nothing and
-- the API answers 404.
alter table public.sales_analytics enable row level security;
alter table public.sales_analytics force  row level security;

drop policy if exists sales_analytics_org_members on public.sales_analytics;
create policy sales_analytics_org_members
  on public.sales_analytics
  for all
  to authenticated
  using (org_id in (select public.current_user_org_ids()))
  with check (org_id in (select public.current_user_org_ids()));

-- ---------------------------------------------------------------------------
-- 2. The analytics audit action
--
-- The constraint is re-created with the full authoritative list —
-- `AuditAction` in backend/app/shared/schemas.py. `case_updated` and
-- `case_deleted` are in the enum and were missing from the list stated in
-- `0006-reports-and-assistant.sql`; restating the whole list here brings the
-- constraint and the enum back together. Change one and change the other.
-- ---------------------------------------------------------------------------

alter table public.audit_trail drop constraint if exists audit_trail_action_check;
alter table public.audit_trail add constraint audit_trail_action_check
  check (action in ('case_created', 'case_updated', 'case_deleted',
                    'document_uploaded',
                    'extraction_completed', 'second_opinion_completed',
                    'matching_completed', 'flag_raised',
                    'item_approved', 'item_rejected',
                    'report_generated',
                    'assistant_question_asked', 'assistant_answered',
                    'sales_analytics_run'));

commit;

-- ===========================================================================
-- Check it, in a transaction you roll back:
--
--   begin;
--   insert into public.sales_analytics (org_id, case_id, payload)
--   values ('<your-org>', 'CASE-TEST', '{"record_count": 0}');
--
--   set local role anon;
--   update public.sales_analytics set payload = '{"record_count": 999}';
--   -- ERROR: permission denied for table sales_analytics
--   delete from public.sales_analytics;
--   -- ERROR: permission denied for table sales_analytics
--   truncate public.sales_analytics;
--   -- ERROR: permission denied for table sales_analytics
--   reset role;
--
--   set local role authenticated;
--   set local request.jwt.claims =
--     '{"sub":"<user-of-another-org>","role":"authenticated"}';
--   select count(*) from public.sales_analytics;
--   -- 0: another firm's readout is invisible, not forbidden
--   rollback;
-- ===========================================================================
