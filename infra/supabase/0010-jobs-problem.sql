-- Tarazu — AI Audit Assistant
-- 0010: a failed job carries its failure as a guide.
--
-- Run after `0009-sales-data-uploads.sql`. Idempotent, like the others, and
-- additive: one nullable column, no rewrite, no rows touched.
--
-- When a queued upload fails, `jobs.error` says why in a sentence. The upload
-- screen needs more than a sentence to help the person fix it: which document,
-- what it lacked, what to do. That is a `ReadProblem` (app/shared/schemas.py),
-- stored here as JSON beside the message it summarises. A job written before
-- this column existed simply has no guide, and the message still stands.
--
-- Apply with: python scripts/apply_supabase_schema.py

begin;

alter table public.jobs add column if not exists problem jsonb;

comment on column public.jobs.problem is
  'The failure as a ReadProblem (title, message, missing columns, guidance); null unless status is failed.';

commit;
