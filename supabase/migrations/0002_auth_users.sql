-- Ranbval Resume Shortlister — auth users. Run once in the Supabase SQL editor.
-- NOTE: passwords are stored in plaintext on purpose, because the admin needs to
-- VIEW every user's password in the dashboard. Keep this an internal tool only.

create table if not exists resume_users (
    id         bigint generated always as identity primary key,
    name       text        not null unique,
    password   text        not null,
    role       text        not null default 'user',  -- 'admin' | 'user'
    created_at timestamptz not null default now()
);

-- Seed accounts (the app also self-seeds these on first login if missing).
insert into resume_users (name, password, role)
values ('ahsan', 'ranbval', 'admin')
on conflict (name) do nothing;

insert into resume_users (name, password, role)
values ('sabeen', 'ranbval', 'user')
on conflict (name) do nothing;
