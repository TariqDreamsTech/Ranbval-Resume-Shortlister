"""Student career-coach endpoints (login-gated, stateless)."""

from fastapi import APIRouter, Depends, File, UploadFile

from app.deps import require_student
from app.schemas import (
    AnalyzeIn,
    AnalyzeOut,
    PrepIn,
    PrepOut,
    StudentCvOut,
    TailorIn,
    TailorOut,
)
from app.services import coach
from app.services.extract import extract_text

router = APIRouter(
    prefix="/api/student", tags=["student"], dependencies=[Depends(require_student)]
)

_MAX_BYTES = 10 * 1024 * 1024


@router.post("/cv", response_model=StudentCvOut)
async def upload_cv(file: UploadFile = File(...)) -> StudentCvOut:
    raw = await file.read()
    text = extract_text(file.filename or "cv", raw[:_MAX_BYTES])
    return StudentCvOut(filename=file.filename or "cv", cv_text=text)


@router.post("/analyze", response_model=AnalyzeOut)
def analyze(body: AnalyzeIn) -> AnalyzeOut:
    return AnalyzeOut(**coach.analyze_cv(body.jd, body.cv_text))


@router.post("/tailor", response_model=TailorOut)
def tailor(body: TailorIn) -> TailorOut:
    answers = [{"question": a.question, "answer": a.answer} for a in body.answers]
    return TailorOut(**coach.tailor_resume(body.jd, body.cv_text, answers))


@router.post("/prep", response_model=PrepOut)
def prep(body: PrepIn) -> PrepOut:
    return PrepOut(**coach.interview_prep(body.jd, body.cv_text))
