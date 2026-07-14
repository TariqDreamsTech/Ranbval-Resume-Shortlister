"""Ranbval Resume Shortlister — FastAPI app entrypoint."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import auth, dashboard, jobs, pages, resumes, student, users

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Ranbval Resume Shortlister",
        description="Strict AI resume screening against a Job Description.",
        version="1.0.0",
    )

    app.include_router(pages.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(dashboard.router)
    app.include_router(student.router)
    app.include_router(jobs.router)
    app.include_router(resumes.router)
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    # Search engines look for these at the site root, not under /static — without them Google
    # simply never indexes the site.
    @app.get("/robots.txt", include_in_schema=False)
    def robots() -> PlainTextResponse:
        return PlainTextResponse(
            "User-agent: *\n"
            "Allow: /\n"
            "Disallow: /api/\n"
            "Disallow: /dashboard\n"
            "\n"
            "Sitemap: https://resume.ranbval.com/sitemap.xml\n"
        )

    @app.get("/sitemap.xml", include_in_schema=False)
    def sitemap() -> Response:
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            "  <url><loc>https://resume.ranbval.com/</loc>"
            "<changefreq>weekly</changefreq><priority>1.0</priority></url>\n"
            "</urlset>\n"
        )
        return Response(content=xml, media_type="application/xml")

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
