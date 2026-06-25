-- Per-job shortlist threshold. Run once in the Supabase SQL editor.
-- Each job can set its own minimum score required to shortlist (default 90 = strict).
alter table resume_jobs add column if not exists threshold int not null default 90;
