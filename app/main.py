"""Ranbval Resume Shortlister — FastAPI app entrypoint."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import jobs, pages, resumes

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Ranbval Resume Shortlister",
        description="Strict AI resume screening against a Job Description.",
        version="1.0.0",
    )

    app.include_router(pages.router)
    app.include_router(jobs.router)
    app.include_router(resumes.router)
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/health", tags=["health"])
    def health() -> dict[str, object]:
        settings = get_settings()
        return {
            "status": "ok",
            "model": settings.openai_model,
            "openai_configured": bool(settings.openai_api_key),
            "supabase_configured": bool(settings.supabase_url and settings.supabase_key),
            "shortlist_threshold": settings.shortlist_threshold,
        }

    return app


app = create_app()
