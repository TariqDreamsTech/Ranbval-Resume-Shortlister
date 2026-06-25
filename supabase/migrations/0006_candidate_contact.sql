-- Store each candidate's contact details (extracted from their CV).
-- Run once in the Supabase SQL editor.
alter table resume_candidates add column if not exists email text;
alter table resume_candidates add column if not exists phone text;
alter table resume_candidates add column if not exists links jsonb;  -- LinkedIn / GitHub / portfolio / any URLs

create index if not exists resume_candidates_email_idx on resume_candidates (email);
