-- Tarazu — AI Audit Assistant: user profiles.
-- Run after 0002-organizations.sql. Idempotent.
--
-- The editable presentation on top of an identity: display name, picture,
-- contact details. Keyed by user, never an authorization input — nothing in
-- this table participates in authentication, tenancy, or the audit trail.
-- The avatar is a size-capped data: URL written by the backend, so no
-- storage bucket is involved.
--
-- Only the backend (service role) touches this table; browser-facing roles
-- get nothing, exactly as with api_keys.

create table if not exists public.user_profiles (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  full_name  text,
  job_title  text,
  phone      text,
  avatar     text check (avatar is null or length(avatar) <= 400000),
  updated_at timestamptz
);

-- Additive columns for tables created by an earlier version of this file.
alter table public.user_profiles add column if not exists gender text;
alter table public.user_profiles add column if not exists date_of_birth date;
alter table public.user_profiles add column if not exists location text;
alter table public.user_profiles add column if not exists license_number text;
alter table public.user_profiles add column if not exists language text
  check (language is null or language in ('en', 'ur'));
alter table public.user_profiles add column if not exists notify_case_ready boolean;
alter table public.user_profiles add column if not exists notify_high_severity boolean;
alter table public.user_profiles add column if not exists notify_weekly_digest boolean;

revoke all on public.user_profiles from anon, authenticated;

alter table public.user_profiles enable row level security;
-- No policies on purpose: with RLS on and no policy, only the service role
-- (which bypasses RLS) can read or write rows.
