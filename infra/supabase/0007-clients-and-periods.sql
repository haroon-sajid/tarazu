-- Tarazu — AI Audit Assistant
-- 0007: clients and periods (ADR 0005), background jobs, value corrections,
--       evidence requests, sign-offs, and the firm's report branding.
--
-- Additive by design, exactly as ADR 0005 requires: new tables, and one new
-- nullable column on `cases`. Nothing is dropped, nothing is rewritten, and a
-- case that predates all of this stays a valid one-off engagement with no
-- client and no period. Safe to run against a project with live data, and
-- idempotent, so re-running it is a no-op.
--
-- Apply with: python scripts/apply_supabase_schema.py

begin;

-- ---------------------------------------------------------------------------
-- Clients. A firm audits many; each is audited every month or quarter.
-- ---------------------------------------------------------------------------

create table if not exists public.clients (
  client_id          text primary key,
  org_id             uuid not null references public.organizations (org_id) on delete cascade,
  name               text not null,
  reference          text,
  -- The client's own rule thresholds. `rules/` already takes a dictionary;
  -- this is where it comes from once a client owns its configuration.
  rules              jsonb not null default '{}'::jsonb,
  currency           text not null default 'PKR',
  language           text not null default 'en' check (language in ('en', 'ur')),
  relationship_owner uuid,
  notes              text,
  created_by         uuid not null,
  created_at         timestamptz not null default now(),
  -- Archiving keeps every period, decision, report, and trail entry behind the
  -- client. There is deliberately no delete path for a relationship's history.
  archived_at        timestamptz
);

create index if not exists clients_org_idx on public.clients (org_id, created_at desc);

-- ---------------------------------------------------------------------------
-- The period. ADR 0005: the existing `cases` row *is* the period, so `case_id`
-- stays the identity every foreign key already points at and only the client
-- link is added. A null `client_id` is a one-off engagement.
-- ---------------------------------------------------------------------------

alter table public.cases
  add column if not exists client_id text references public.clients (client_id) on delete set null;

create index if not exists cases_client_idx on public.cases (org_id, client_id, created_at desc);

-- The pipeline gained `matching`, and people drive `approved` and `reported`.
-- The old constraint is replaced rather than added to, because a check
-- constraint cannot be widened in place.
alter table public.cases drop constraint if exists cases_status_check;
alter table public.cases add constraint cases_status_check
  check (status in ('uploaded', 'extracting', 'awaiting_matching', 'matching',
                    'ready_for_review', 'approved', 'reported', 'failed'));

-- ---------------------------------------------------------------------------
-- Background jobs. Working state, not evidence: these rows are updated as the
-- work advances, and what actually happened is in the append-only trail
-- regardless of what a job row ends up saying. No foreign key to `cases`, so a
-- job survives its case being deleted mid-flight.
-- ---------------------------------------------------------------------------

create table if not exists public.jobs (
  job_id      text primary key,
  org_id      uuid not null references public.organizations (org_id) on delete cascade,
  case_id     text not null,
  kind        text not null default 'pipeline' check (kind in ('pipeline')),
  status      text not null default 'queued'
              check (status in ('queued', 'running', 'succeeded', 'failed')),
  progress    integer not null default 0 check (progress between 0 and 100),
  step        text not null default 'Queued',
  created_by  uuid not null,
  created_at  timestamptz not null default now(),
  started_at  timestamptz,
  finished_at timestamptz,
  error       text
);

create index if not exists jobs_org_case_idx on public.jobs (org_id, case_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Value corrections. What a human says a value actually is, beside what the
-- model read. Both are kept — this is evidence about the extraction, not a
-- rewrite of it, and not data entry into the client's books (ADR 0004).
-- ---------------------------------------------------------------------------

create table if not exists public.value_corrections (
  correction_id   text primary key,
  org_id          uuid not null references public.organizations (org_id) on delete cascade,
  case_id         text not null references public.cases (case_id) on delete cascade,
  review_item_id  text not null,
  document_id     text not null,
  field           text not null,
  ai_value        text,
  corrected_value text not null,
  note            text,
  corrected_by    uuid not null,
  corrected_at    timestamptz not null default now()
);

create index if not exists value_corrections_case_idx
  on public.value_corrections (org_id, case_id, corrected_at);

-- ---------------------------------------------------------------------------
-- Evidence requests. "Ask the client for invoice #43", with its state, inside
-- the system of record rather than in somebody's inbox.
-- ---------------------------------------------------------------------------

create table if not exists public.evidence_requests (
  request_id     text primary key,
  org_id         uuid not null references public.organizations (org_id) on delete cascade,
  case_id        text not null references public.cases (case_id) on delete cascade,
  review_item_id text,
  title          text not null,
  detail         text,
  status         text not null default 'open'
                 check (status in ('open', 'answered', 'resolved', 'cancelled')),
  due_date       date,
  requested_by   uuid not null,
  requested_at   timestamptz not null default now(),
  response_note  text,
  responded_by   uuid,
  responded_at   timestamptz,
  cancellation_note text,
  closed_by      uuid,
  closed_at      timestamptz
);

create index if not exists evidence_requests_case_idx
  on public.evidence_requests (org_id, case_id, requested_at desc);

-- ---------------------------------------------------------------------------
-- Sign-offs (maker-checker). A second person putting their name to a finished
-- engagement. Append-only for the same reason reports are: it is a signature.
-- ---------------------------------------------------------------------------

create table if not exists public.sign_offs (
  sign_off_id    text primary key,
  org_id         uuid not null references public.organizations (org_id) on delete cascade,
  case_id        text not null,
  signed_by      uuid not null,
  signed_at      timestamptz not null default now(),
  note           text,
  item_count     integer not null,
  approved_count integer not null,
  rejected_count integer not null
);

create index if not exists sign_offs_org_case_idx
  on public.sign_offs (org_id, case_id, signed_at desc);

-- ---------------------------------------------------------------------------
-- The firm's own details, printed on every report it delivers. Presentation
-- only: nothing here is an authorization input or changes a number.
-- ---------------------------------------------------------------------------

create table if not exists public.org_profiles (
  org_id              uuid primary key references public.organizations (org_id) on delete cascade,
  legal_name          text,
  address             text,
  contact_email       text,
  phone               text,
  website             text,
  registration_number text,
  logo                text,
  report_footer       text,
  updated_at          timestamptz
);

-- ---------------------------------------------------------------------------
-- Row level security. Same shape as every other tenant table: a row is visible
-- only to members of its organization. The backend reaches Postgres with the
-- service role and filters by org_id itself; these policies protect anything
-- that arrives another way (the browser, psql, a leaked anon key).
-- ---------------------------------------------------------------------------

alter table public.clients            enable row level security;
alter table public.jobs               enable row level security;
alter table public.value_corrections  enable row level security;
alter table public.evidence_requests  enable row level security;
alter table public.sign_offs          enable row level security;
alter table public.org_profiles       enable row level security;

do $$
declare
  t text;
begin
  foreach t in array array['clients', 'jobs', 'value_corrections',
                           'evidence_requests', 'sign_offs', 'org_profiles']
  loop
    execute format('drop policy if exists %I on public.%I', t || '_member_select', t);
    execute format(
      'create policy %I on public.%I for select using ('
      '  org_id in (select org_id from public.organization_members'
      '             where user_id = auth.uid()))',
      t || '_member_select', t
    );

    execute format('drop policy if exists %I on public.%I', t || '_member_insert', t);
    execute format(
      'create policy %I on public.%I for insert with check ('
      '  org_id in (select org_id from public.organization_members'
      '             where user_id = auth.uid()))',
      t || '_member_insert', t
    );
  end loop;
end
$$;

-- Update is granted only where a row is genuinely working state. `sign_offs`
-- is deliberately absent: like `reports` and `audit_trail`, it is append-only.
do $$
declare
  t text;
begin
  foreach t in array array['clients', 'jobs', 'evidence_requests', 'org_profiles']
  loop
    execute format('drop policy if exists %I on public.%I', t || '_member_update', t);
    execute format(
      'create policy %I on public.%I for update using ('
      '  org_id in (select org_id from public.organization_members'
      '             where user_id = auth.uid()))',
      t || '_member_update', t
    );
  end loop;
end
$$;

-- The append-only guarantee for sign-offs, enforced by the database rather than
-- by us remembering. The REVOKE is the one that matters: `service_role`
-- bypasses RLS, but it does not bypass table privileges.
revoke update, delete on public.sign_offs from anon, authenticated, service_role;

create or replace function public.sign_offs_are_append_only()
returns trigger
language plpgsql
as $$
begin
  raise exception 'sign_offs are append-only: % is not permitted', tg_op;
end;
$$;

drop trigger if exists sign_offs_no_change on public.sign_offs;
create trigger sign_offs_no_change
  before update or delete on public.sign_offs
  for each row execute function public.sign_offs_are_append_only();

commit;
