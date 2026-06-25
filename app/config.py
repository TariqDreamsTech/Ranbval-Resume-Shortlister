"""Runtime configuration loaded from environment / .env."""

import os
from functools import lru_cache
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal .env loader (no external dependency)."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


class Settings:
    openai_api_key: str = os.environ.get("OPENAI_API_KEY", "").strip()
    openai_model: str = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
    shortlist_threshold: int = int(os.environ.get("SHORTLIST_THRESHOLD", "90"))
    # How many queued resumes one /process call claims, and how many OpenAI
    # calls run concurrently within it. Keep BATCH small enough that a single
    # call finishes inside the serverless timeout (Vercel Hobby = 10s).
    process_batch: int = int(os.environ.get("PROCESS_BATCH", "6"))
    process_concurrency: int = int(os.environ.get("PROCESS_CONCURRENCY", "3"))
    openai_max_retries: int = int(os.environ.get("OPENAI_MAX_RETRIES", "4"))
    supabase_url: str = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key: str = os.environ.get("SUPABASE_KEY", "").strip()
    # Secret used to sign login tokens. Defaults to a value derived from the
    # Supabase key so it's stable across restarts without extra config.
    auth_secret: str = (
        os.environ.get("AUTH_SECRET", "").strip()
        or (os.environ.get("SUPABASE_KEY", "").strip() or "ranbval-resume-secret")
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
