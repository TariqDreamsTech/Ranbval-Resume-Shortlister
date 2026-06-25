-- Ranbval Resume Shortlister — run this once in the Supabase SQL editor.
-- Tables are prefixed `resume_` so they don't collide with other apps that
-- share this Supabase project.

create table if not exists resume_jobs (
    id          bigint generated always as identity primary key,
    title       text        not null,
    description text        not null,
    created_at  timestamptz not null default now()
);

create table if not exists resume_candidates (
    id             bigint generated always as identity primary key,
    job_id         bigint      not null references resume_jobs(id) on delete cascade,
    filename       text        not null,
    candidate_name text,
    score          int         not null default 0,
    verdict        text        not null default 'reject',
    recommended    boolean     not null default false,
    summary        text,
    details        jsonb,
    created_at     timestamptz not null default now()
);

create index if not exists resume_candidates_job_idx
    on resume_candidates (job_id, recommended desc, score desc);
