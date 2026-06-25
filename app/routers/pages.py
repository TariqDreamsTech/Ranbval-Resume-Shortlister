"""Serve the single-page frontend."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])

_INDEX = Path(__file__).resolve().parent.parent / "static" / "index.html"


@router.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    # Never cache the shell HTML, so the versioned ?v= asset URLs are always
    # re-read by the browser after a deploy (no stale app.js/styles.css).
    return HTMLResponse(
        _INDEX.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
