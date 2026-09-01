-- Tarazu — AI Audit Assistant: Supabase / Postgres schema.
--
-- Run this once, top to bottom, in the Supabase SQL editor, and then run
-- `0002-organizations.sql`. Both are idempotent: re-running either is safe.
--
-- **This file is the base schema, not the whole schema.** It is single-tenant:
-- the row-level security section near the bottom grants every authenticated
-- user every row. `0002-organizations.sql` adds `organizations`,
-- `organization_members`, and an `org_id` on every tenant-owned table, and
-- replaces those policies with membership-scoped ones. A project is not
-- multi-tenant until it has been run.
--
-- The section that matters most is "AUDIT TRAIL HARDENING" near the bottom.
-- Everything above it is ordinary table design; that section is the part that
-- turns reliability rule 5 from a promise into something the database enforces.
-- The migration narrows who may read the trail and changes nothing else about
-- it: same REVOKE, same trigger, still no UPDATE policy and no DELETE policy.

begin;

-- ---------------------------------------------------------------------------
-- Enumerated values. Kept as text + check constraints rather than Postgres
-- enums, because adding a value to an enum is a migration and adding one to a
-- check constraint is not — and this vocabulary will grow during the build.
-- The authoritative list lives in backend/app/shared/schemas.py.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- cases
-- ---------------------------------------------------------------------------

create table if not exists public.cases (
  case_id       text primary key,
  client_name   text        not null,
  period_start  date,
  period_end    date,
  status        text        not null default 'uploaded'
                  check (status in ('uploaded', 'extracting', 'awaiting_matching',
                                    'ready_for_review', 'failed')),
  created_by    uuid        not null references auth.users (id),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create index if not exists cases_created_by_idx on public.cases (created_by, created_at desc);

-- ---------------------------------------------------------------------------
-- documents — one row per uploaded file. Bytes live in Storage.
-- ---------------------------------------------------------------------------

create table if not exists public.documents (
  document_id   text primary key,
  case_id       text        not null references public.cases (case_id) on delete cascade,
  document_type text        not null
                  check (document_type in ('bank_statement', 'invoice', 'ledger')),
  filename      text        not null,
  storage_path  text        not null,
  size_bytes    bigint      not null default 0,
  uploaded_by   uuid        not null references auth.users (id),
  created_at    timestamptz not null default now()
);

create index if not exists documents_case_idx on public.documents (case_id);

-- ---------------------------------------------------------------------------
-- sales_data_uploads — analytical exports, separate from audit evidence.
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

revoke update, delete, truncate on public.sales_data_uploads from anon;
grant insert, select, delete on public.sales_data_uploads to service_role;

alter table public.sales_data_uploads enable row level security;
alter table public.sales_data_uploads force  row level security;

drop policy if exists sales_data_uploads_org_members on public.sales_data_uploads;
create policy sales_data_uploads_org_members
  on public.sales_data_uploads
  for all
  to authenticated
  using (org_id in (select public.current_user_org_ids()))
  with check (org_id in (select public.current_user_org_ids()));

-- ---------------------------------------------------------------------------
-- extractions — the ExtractionResult for one document.
--
-- The whole schema object is stored as jsonb, with only the columns we filter
-- on pulled out alongside it. The Pydantic model in app/shared/schemas.py stays
-- the single source of truth for the shape, and the shape can change without a
-- migration — which matters when the extraction prompt is still being tuned.
-- ---------------------------------------------------------------------------

create table if not exists public.extractions (
  extraction_id      uuid primary key default gen_random_uuid(),
  document_id        text        not null references public.documents (document_id) on delete cascade,
  case_id            text        not null references public.cases (case_id) on delete cascade,
  model              text        not null,
  needs_human_review boolean     not null default false,
  payload            jsonb       not null,
  created_at         timestamptz not null default now()
);

create index if not exists extractions_case_idx on public.extractions (case_id);
create index if not exists extractions_document_idx on public.extractions (document_id);

-- ---------------------------------------------------------------------------
-- review_items — the unit a human approves or rejects.
--
-- `payload` is the full ReviewItem. The columns beside it are denormalised for
-- filtering and for the dashboard counts, and are kept in step by the
-- application, which writes both from the same validated object.
--
-- Note there is no `confidence` column. `extraction_confidence` is the AI's
-- certainty that it read a value correctly; `match_strength` is deterministic
-- and computed by pandas. Collapsing them would imply the AI scores matches.
-- ---------------------------------------------------------------------------

create table if not exists public.review_items (
  review_item_id        text primary key,
  case_id               text        not null references public.cases (case_id) on delete cascade,
  match_status          text        not null
                          check (match_status in ('matched', 'partial', 'unmatched')),
  match_strength        text        not null
                          check (match_strength in ('high', 'medium', 'low')),
  extraction_confidence text        not null
                          check (extraction_confidence in ('high', 'medium', 'low')),
  flag_count            integer     not null default 0,
  decision              text        not null default 'pending'
                          check (decision in ('pending', 'approved', 'rejected')),
  decided_by            uuid        references auth.users (id),
  decided_at            timestamptz,
  rejection_reason      text,
  payload               jsonb       not null,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),

  -- Reliability rule 1, at the database: a decision exists only when a human
  -- made it, and a rejection always says why.
  constraint review_items_decision_is_complete check (
    (decision = 'pending'  and decided_by is null and decided_at is null
                           and rejection_reason is null)
    or
    (decision = 'approved' and decided_by is not null and decided_at is not null
                           and rejection_reason is null)
    or
    (decision = 'rejected' and decided_by is not null and decided_at is not null
                           and rejection_reason is not null and length(rejection_reason) > 0)
  )
);

create index if not exists review_items_case_idx on public.review_items (case_id, review_item_id);
create index if not exists review_items_decision_idx on public.review_items (case_id, decision);

-- ---------------------------------------------------------------------------
-- flags — red flags raised by rules/, denormalised out of the review item so
-- the dashboard can count by severity without unpacking every payload.
-- ---------------------------------------------------------------------------

create table if not exists public.flags (
  flag_id        text primary key,
  case_id        text        not null references public.cases (case_id) on delete cascade,
  review_item_id text        not null references public.review_items (review_item_id) on delete cascade,
  rule_id        text        not null,
  severity       text        not null check (severity in ('high', 'medium', 'low')),
  explanation    text        not null,
  source_row_id  text        not null,
  payload        jsonb       not null,
  created_at     timestamptz not null default now()
);

create index if not exists flags_case_idx on public.flags (case_id, severity);

-- ---------------------------------------------------------------------------
-- benford_results — one per case. Pure arithmetic over the ledger amounts,
-- produced by rules/, stored so the dashboard can chart it without recomputing.
-- ---------------------------------------------------------------------------

create table if not exists public.benford_results (
  case_id    text primary key references public.cases (case_id) on delete cascade,
  payload    jsonb       not null,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- audit_trail — append only. See the hardening section below.
-- ---------------------------------------------------------------------------

create table if not exists public.audit_trail (
  -- Text, not uuid, and always supplied by the application: `AUD-<12 hex>`.
  -- Every identifier in this schema is prefixed text so that a human reading a
  -- trail can tell what kind of thing an id names. There is deliberately no
  -- default — a writer that forgot to supply one should fail, not be papered
  -- over. (`0005-audit-id-is-text.sql` fixes projects created before this.)
  audit_id    text primary key,
  case_id     text        not null,
  actor_type  text        not null check (actor_type in ('human', 'ai', 'system')),
  actor_id    text        not null,
  action      text        not null
                check (action in ('case_created', 'document_uploaded',
                                  'extraction_completed', 'second_opinion_completed',
                                  'matching_completed', 'flag_raised',
                                  'item_approved', 'item_rejected',
                                  'report_generated')),
  item_id     text,
  detail      text,
  occurred_at timestamptz not null default now()
);

create index if not exists audit_trail_case_idx on public.audit_trail (case_id, occurred_at);
create index if not exists audit_trail_item_idx on public.audit_trail (item_id);

-- No foreign key from audit_trail to cases. Deleting a case must never cascade
-- into the trail, and the trail has to be able to outlive what it describes.

-- ===========================================================================
-- AUDIT TRAIL HARDENING
--
-- "We wrote a function that only inserts" is a convention any future line of
-- code can break. These three layers are not.
-- ===========================================================================

-- (1) Privileges. Revoke the ability to modify or remove rows from every role
--     the application can possibly authenticate as.
--
--     This is the layer that matters most, and the reason is easy to miss:
--     `service_role` bypasses row-level security, so RLS alone would not stop
--     a leaked or careless service key from rewriting history. Table
--     privileges are NOT bypassed by BYPASSRLS — so this REVOKE stops it and
--     RLS could not.
--
--     TRUNCATE is in the list for a reason worth spelling out: it is a THIRD
--     statement, not a flavour of DELETE. RLS does not apply to it, and the row
--     trigger in (3) does not fire for it, so `revoke update, delete` alone left
--     the whole trail one `truncate public.audit_trail` away from gone — a
--     statement Supabase's default `grant all` hands to `anon`.

revoke update, delete, truncate on public.audit_trail
  from anon, authenticated, service_role;

grant insert, select on public.audit_trail to authenticated, service_role;

-- (2) Row-level security. Insert and select only: there is deliberately no
--     update policy and no delete policy, so those actions have no route in
--     even if a privilege were granted back by mistake.
--
--     `force row level security` also subjects the table owner to these
--     policies, which it otherwise would not be.

alter table public.audit_trail enable row level security;
alter table public.audit_trail force  row level security;

drop policy if exists audit_trail_insert_only on public.audit_trail;
create policy audit_trail_insert_only
  on public.audit_trail
  for insert
  to authenticated, service_role
  with check (true);

drop policy if exists audit_trail_select_only on public.audit_trail;
create policy audit_trail_select_only
  on public.audit_trail
  for select
  to authenticated, service_role
  using (true);

-- Deliberately absent, and must stay absent:
--   create policy ... for update ...
--   create policy ... for delete ...

-- (3) A trigger, as the backstop. Privileges can be granted back and policies
--     can be dropped by anyone with enough rights; this refuses the write
--     itself, for every role including the owner and a superuser.

create or replace function public.audit_trail_is_append_only()
returns trigger
language plpgsql
as $$
begin
  raise exception
    'audit_trail is append-only: % is not permitted on public.audit_trail', tg_op
    using errcode = 'insufficient_privilege';
end;
$$;

drop trigger if exists audit_trail_no_update_or_delete on public.audit_trail;
create trigger audit_trail_no_update_or_delete
  before update or delete on public.audit_trail
  for each row execute function public.audit_trail_is_append_only();

-- TRUNCATE needs its own trigger: it cannot be FOR EACH ROW, so the one above
-- does not and cannot cover it. Same function, statement-level.
drop trigger if exists audit_trail_no_truncate on public.audit_trail;
create trigger audit_trail_no_truncate
  before truncate on public.audit_trail
  for each statement execute function public.audit_trail_is_append_only();

-- Verify it, right here, in the transaction that created it:
--
--   insert into public.audit_trail (case_id, actor_type, actor_id, action)
--   values ('CASE-TEST', 'system', 'schema-check', 'case_created');
--
--   update public.audit_trail set detail = 'tampered' where case_id = 'CASE-TEST';
--   -- ERROR: audit_trail is append-only: UPDATE is not permitted
--
--   delete from public.audit_trail where case_id = 'CASE-TEST';
--   -- ERROR: audit_trail is append-only: DELETE is not permitted
--
--   truncate public.audit_trail;
--   -- ERROR: audit_trail is append-only: TRUNCATE is not permitted

-- ===========================================================================
-- Row-level security on everything else.
--
-- These policies scope to "any authenticated user", which is correct only for a
-- single-tenant database. **`0002-organizations.sql` replaces every one of them**
-- with a policy that admits a row only when its `org_id` is in the caller's
-- `organization_members`. Run it: until you do, any authenticated user of this
-- project can read any firm's cases.
-- ===========================================================================

alter table public.cases           enable row level security;
alter table public.documents       enable row level security;
alter table public.extractions     enable row level security;
alter table public.review_items    enable row level security;
alter table public.flags           enable row level security;
alter table public.benford_results enable row level security;

do $$
declare
  table_name text;
begin
  foreach table_name in array array['cases', 'documents', 'extractions',
                                    'review_items', 'flags', 'benford_results']
  loop
    execute format('drop policy if exists %I_authenticated on public.%I',
                   table_name, table_name);
    execute format(
      'create policy %I_authenticated on public.%I for all to authenticated '
      'using (true) with check (true)', table_name, table_name);
  end loop;
end;
$$;

-- `updated_at` maintenance for the two tables that are genuinely mutable.

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists cases_touch_updated_at on public.cases;
create trigger cases_touch_updated_at
  before update on public.cases
  for each row execute function public.touch_updated_at();

drop trigger if exists review_items_touch_updated_at on public.review_items;
create trigger review_items_touch_updated_at
  before update on public.review_items
  for each row execute function public.touch_updated_at();

commit;

-- ===========================================================================
-- Storage
--
-- Create a PRIVATE bucket named `tarazu-documents` (Storage → New bucket, and
-- leave "Public bucket" off). Client documents must never be world-readable;
-- the backend reads them with the service role and hands the frontend
-- short-lived signed URLs.
-- ===========================================================================
