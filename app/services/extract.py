"""Extract plain text from an uploaded resume (PDF / DOCX / TXT)."""

import io

from fastapi import HTTPException

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
