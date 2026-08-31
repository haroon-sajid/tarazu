-- Tarazu — AI Audit Assistant: generated reports, and the assistant's trail entries.
--
-- Run after `0005-audit-id-is-text.sql`. Idempotent, like the others.
--
-- Two things:
--
--   1. **`reports`** — one row per generated report: who made it, when, the
--      Storage paths of the PDF and the Excel workbook, their SHA-256 digests,
--      and the counts at the moment of generation. Append-only, for the same
--      reason the audit trail is: a report is evidence of what the firm
--      delivered on a date. Regenerating adds a row; nothing rewrites one.
--   2. **Two new audit actions**, `assistant_question_asked` and
--      `assistant_answered`, so a question put to the assistant and the answer
--      it gave are both on the record. The `audit_trail.action` check
--      constraint is re-stated with the full list. Adding a value to a check
--      constraint is DDL and issues no row UPDATE, so the table's append-only
--      trigger is never asked for an exemption.

begin;

-- ---------------------------------------------------------------------------
-- 1. reports
-- ---------------------------------------------------------------------------

create table if not exists public.reports (
  report_id          text        primary key,
  org_id             uuid        not null references public.organizations (org_id),
  -- No foreign key to cases: a report has to be able to outlive what it
  -- describes, exactly like a trail entry.
  case_id            text        not null,
  generated_by       uuid        not null references auth.users (id),
  generated_at       timestamptz not null default now(),
  pdf_path           text        not null,
  excel_path         text        not null,
  pdf_sha256         text        not null check (pdf_sha256   ~ '^[0-9a-f]{64}$'),
  excel_sha256       text        not null check (excel_sha256 ~ '^[0-9a-f]{64}$'),
  item_count         integer     not null check (item_count         >= 0),
  approved_count     integer     not null check (approved_count     >= 0),
  rejected_count     integer     not null check (rejected_count     >= 0),
  pending_count      integer     not null check (pending_count      >= 0),
  flag_count         integer     not null check (flag_count         >= 0),
  audit_record_count integer     not null check (audit_record_count >= 0),
  constraint reports_decisions_add_up
    check (approved_count + rejected_count + pending_count = item_count)
);

create index if not exists reports_org_case_idx
  on public.reports (org_id, case_id, generated_at desc);

-- The same three layers as audit_trail. (1) Privileges — the one that binds
-- the service role, which bypasses RLS but not table privileges.
revoke all on public.reports from anon, authenticated;
revoke update, delete, truncate on public.reports from anon, authenticated, service_role;
grant insert, select on public.reports to service_role;

-- (2) RLS, with no policies for browser roles: reports are read and written
-- through the backend alone, like api_keys and org_invitations.
alter table public.reports enable row level security;
alter table public.reports force  row level security;

drop policy if exists reports_insert_service on public.reports;
create policy reports_insert_service
  on public.reports for insert to service_role with check (true);

drop policy if exists reports_select_service on public.reports;
create policy reports_select_service
  on public.reports for select to service_role using (true);

-- Deliberately absent, and must stay absent:
--   create policy ... for update ...
--   create policy ... for delete ...

-- (3) A trigger, as the backstop, for every role including the owner.
create or replace function public.reports_are_append_only()
returns trigger
language plpgsql
as $$
begin
  raise exception
    'reports are append-only: % is not permitted on public.reports', tg_op
    using errcode = 'insufficient_privilege';
end;
$$;

drop trigger if exists reports_no_update_or_delete on public.reports;
create trigger reports_no_update_or_delete
  before update or delete on public.reports
  for each row execute function public.reports_are_append_only();

drop trigger if exists reports_no_truncate on public.reports;
create trigger reports_no_truncate
  before truncate on public.reports
  for each statement execute function public.reports_are_append_only();

-- ---------------------------------------------------------------------------
-- 2. The assistant's audit actions
--
-- The constraint from schema.sql is inline on the `action` column, which
-- Postgres names `audit_trail_action_check`. Re-created with the two new
-- values. The authoritative list is `AuditAction` in
-- backend/app/shared/schemas.py; change one and change the other.
-- ---------------------------------------------------------------------------

alter table public.audit_trail drop constraint if exists audit_trail_action_check;
alter table public.audit_trail add constraint audit_trail_action_check
  check (action in ('case_created', 'document_uploaded',
                    'extraction_completed', 'second_opinion_completed',
                    'matching_completed', 'flag_raised',
                    'item_approved', 'item_rejected',
                    'report_generated',
                    'assistant_question_asked', 'assistant_answered'));

commit;

-- ===========================================================================
-- Check it, in a transaction you roll back:
--
--   begin;
--   insert into public.reports (report_id, org_id, case_id, generated_by,
--     pdf_path, excel_path, pdf_sha256, excel_sha256, item_count,
--     approved_count, rejected_count, pending_count, flag_count,
--     audit_record_count)
--   values ('RPT-test', '<your-org>', 'CASE-TEST', '<a-user-uuid>',
--     'x.pdf', 'x.xlsx', repeat('a', 64), repeat('b', 64), 1, 1, 0, 0, 0, 0);
--   update public.reports set pdf_path = 'tampered' where report_id = 'RPT-test';
--   -- ERROR: reports are append-only: UPDATE is not permitted on public.reports
--   delete from public.reports where report_id = 'RPT-test';
--   -- ERROR: reports are append-only: DELETE is not permitted on public.reports
--   rollback;
-- ===========================================================================
