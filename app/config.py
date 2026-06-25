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
    shortlist_threshold: int = int(os.environ.get("SHORTLIST_THRESHOLD", "75"))
    supabase_url: str = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key: str = os.environ.get("SUPABASE_KEY", "").strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
