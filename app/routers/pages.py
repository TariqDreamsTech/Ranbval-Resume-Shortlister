"""Serve the single-page frontend."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])

_INDEX = Path(__file__).resolve().parent.parent / "static" / "index.html"


@router.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(_INDEX.read_text(encoding="utf-8"))
