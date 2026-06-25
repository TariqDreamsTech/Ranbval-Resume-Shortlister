-- Separate recruiter vs student logins. Run once in the Supabase SQL editor.
-- Every account is one type and can only sign in on its matching login tab.

alter table resume_users add column if not exists account_type text not null default 'recruiter';

-- Existing seeded accounts are recruiters; add one starter student account
-- (admin can rename/delete it from the Users panel).
insert into resume_users (name, password, role, account_type)
values ('student', 'ranbval', 'user', 'student')
on conflict (name) do nothing;
