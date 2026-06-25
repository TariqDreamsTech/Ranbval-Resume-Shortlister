-- Ranbval Resume Shortlister — scale/queue support. Run once in Supabase SQL editor.
-- Uploads now just extract text + enqueue; a background worker scores in batches.

alter table resume_candidates add column if not exists status text not null default 'done';
alter table resume_candidates add column if not exists error text;
alter table resume_candidates add column if not exists resume_text text;

-- Fast "find queued work for this job" lookups (the worker hits this constantly).
create index if not exists resume_candidates_status_idx
    on resume_candidates (job_id, status);
