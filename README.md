# Ranbval Resume Shortlister

A strict, AI-powered resume screening tool. Create a job with its Job Description,
upload resumes one by one, and get an honest **score + shortlist / reject verdict**
for each candidate — so irrelevant resumes never waste your time.

- **No login, no accounts** — open it and use it.
- **FastAPI + Supabase (Postgres)** — one Python app, deployable to Vercel.
- **OpenAI** does the screening against the exact JD you provide.
- **Strict by design** — the screener defaults to *reject* unless a candidate
  clearly meets the role's hard requirements.

## One-time: create the tables

In the Supabase dashboard → **SQL Editor**, paste and run:
`supabase/migrations/0001_resume_shortlister.sql`
(creates `resume_jobs` and `resume_candidates`).

## Setup (local)

```bash
cd ranbval-resume-shortlister
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # paste OPENAI_API_KEY + SUPABASE_URL/SUPABASE_KEY
```

## Run (local)

```bash
uvicorn app.main:app --reload --port 8020
```

Open http://localhost:8020

## Deploy to Vercel

1. Push this folder to a Git repo and import it in Vercel.
2. In **Settings → Environment Variables**, add: `OPENAI_API_KEY`,
   `SUPABASE_URL`, `SUPABASE_KEY` (and optionally `OPENAI_MODEL`,
   `SHORTLIST_THRESHOLD`).
3. Deploy. `vercel.json` routes everything through `api/index.py` (the FastAPI
   ASGI app). Because data lives in Supabase, the serverless filesystem being
   ephemeral doesn't matter.

## How it works

1. **Create a job** — paste the title + full Job Description.
2. **Upload resumes** one at a time (PDF, DOCX, or TXT).
3. Each resume is parsed to text and scored by OpenAI against the JD's hard
   requirements. You get:
   - an **overall score (0–100)**,
   - a **verdict** (`shortlist` / `maybe` / `reject`),
   - matched & missing requirements, red flags, and a one-line reason.
4. Candidates are ranked best-first so you review only the strong ones.

## Strictness

Controlled by `SHORTLIST_THRESHOLD` in `.env` (default `75`). A candidate is
marked **recommended** only if the score clears the threshold *and* has no
critical missing requirement. Raise it to 80–85 to be even more ruthless.
