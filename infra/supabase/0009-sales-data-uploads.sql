-- Tarazu — AI Audit Assistant: standalone sales data uploads.
--
-- Run after `0008-sales-analytics.sql`. Idempotent, like the others.
--
-- Sales analytics needs its own data source: a sales export is analytical
-- material, not audit evidence. This table holds the metadata for exports
-- uploaded separately from the case's documents. The bytes themselves live in
-- the same storage layer; deleting a case cascades here too.

begin;

-- ---------------------------------------------------------------------------
-- 1. sales_data_uploads
-- ---------------------------------------------------------------------------

create table if not exists public.sales_data_uploads (
  sales_data_id text        primary key,
  org_id        uuid        not null references public.organizations (org_id),
  case_id       text        not null references public.cases (case_id) on delete cascade,
  filename      text        not null,
  storage_path  text        not null,
  size_bytes    bigint      not null default 0,
  uploaded_by   uuid        not null references auth.users (id),
  created_at    timestamptz not null default now()
);

create index if not exists sales_data_uploads_case_idx
  on public.sales_data_uploads (case_id);

-- Privileges. The backend talks to this table through the service role, so it
-- needs insert, select, and delete (analysts may remove a bad export). Browser
-- roles get nothing directly.
revoke update, delete, truncate on public.sales_data_uploads from anon;
grant insert, select, delete on public.sales_data_uploads to service_role;

-- RLS, scoped by organization membership like every other tenant-owned table.
alter table public.sales_data_uploads enable row level security;
alter table public.sales_data_uploads force  row level security;

drop policy if exists sales_data_uploads_org_members on public.sales_data_uploads;
create policy sales_data_uploads_org_members
  on public.sales_data_uploads
  for all
  to authenticated
  using (org_id in (select public.current_user_org_ids()))
  with check (org_id in (select public.current_user_org_ids()));

commit;
