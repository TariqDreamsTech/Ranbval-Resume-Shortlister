"""Supabase (Postgres) client — replaces the old SQLite layer for Vercel.

Tables are created once via the SQL in supabase/migrations/ (run in the
Supabase SQL editor); the app only reads/writes through the client.
"""

from functools import lru_cache

from fastapi import HTTPException
from supabase import Client, create_client

from app.config import get_settings

# Table names (prefixed to avoid clashing with other apps in the same project).
JOBS_TABLE = "resume_jobs"
CANDIDATES_TABLE = "resume_candidates"


@lru_cache(maxsize=1)
def get_client() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise HTTPException(
            status_code=503,
            detail="SUPABASE_URL and SUPABASE_KEY must be set in the environment.",
        )
    return create_client(settings.supabase_url, settings.supabase_key)
