"""Extract plain text + contact details from an uploaded resume (PDF/DOCX/TXT)."""

import io
import re

from fastapi import HTTPException

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# URLs with scheme, plus bare linkedin/github/portfolio-style hosts.
_URL_RE = re.compile(
    r"(https?://[^\s)>\]\"']+|(?:www\.)?(?:linkedin\.com|github\.com|gitlab\.com|"
    r"behance\.net|dribbble\.com|medium\.com)/[^\s)>\]\"']+)",
    re.IGNORECASE,
)
# Phone: 8+ digits allowing +, spaces, dashes, parens.
_PHONE_RE = re.compile(r"(\+?\d[\d\s\-().]{7,}\d)")


def extract_contact(text: str) -> dict:
    """Pull email, phone, and links (LinkedIn/GitHub/portfolio) from CV text."""
    text = text or ""
    email_m = _EMAIL_RE.search(text)
    email = email_m.group(0) if email_m else None

    links: list[str] = []
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;)")
        if url not in links:
            links.append(url)
        if len(links) >= 15:
            break

    phone = None
    for m in _PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 8 <= len(digits) <= 15:
            phone = m.group(0).strip()
            break

    return {"email": email, "phone": phone, "links": links}

_MAX_CHARS = 25_000  # plenty for any resume; protects token budget


def extract_text(filename: str, raw: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        text = _from_pdf(raw)
    elif name.endswith(".docx"):
        text = _from_docx(raw)
    elif name.endswith(".txt"):
        text = raw.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload a PDF, DOCX, or TXT resume.",
        )

    text = (text or "").strip()
    if len(text) < 30:
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not read meaningful text from this file. If it is a "
                "scanned/image PDF, export a text-based PDF or paste as TXT."
            ),
        )
    return text[:_MAX_CHARS]


def _from_pdf(raw: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Failed to read PDF: {e}") from e


def _from_docx(raw: bytes) -> str:
    try:
        import docx

        document = docx.Document(io.BytesIO(raw))
        return "\n".join(p.text for p in document.paragraphs)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Failed to read DOCX: {e}") from e
