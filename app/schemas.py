"""Pydantic request/response models."""

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)
    account_type: str = Field(default="recruiter")


class LoginOut(BaseModel):
    token: str
    name: str
    role: str
    account_type: str


class UserOut(BaseModel):
    id: int
    name: str
    password: str
    role: str
    account_type: str = "recruiter"
    created_at: str


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)
    role: str = Field(default="user")
    account_type: str = Field(default="recruiter")


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    password: str | None = Field(default=None, max_length=200)
    role: str | None = None
    account_type: str | None = None


class JobCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=20)
    threshold: int = Field(default=90, ge=1, le=100)


class JobOut(BaseModel):
    id: int
    title: str
    description: str
    threshold: int = 90
    created_at: str
    candidate_count: int = 0


class RequirementItem(BaseModel):
    requirement: str
    status: str = "missing"  # met | partial | missing
    evidence: str = ""
    location: str = ""


class CandidateOut(BaseModel):
    id: int
    job_id: int
    filename: str
    candidate_name: str | None = None
    email: str | None = None
    phone: str | None = None
    links: list[str] = []
    score: int
    verdict: str
    recommended: bool
    confidence: str | None = None
    status: str = "done"  # queued | processing | done | error
    error: str | None = None
    summary: str | None = None
    matched_requirements: list[str] = []
    missing_requirements: list[str] = []
    red_flags: list[str] = []
    key_skills: list[str] = []
    years_experience: float | None = None
    years_required: float | None = None
    seniority_required: str | None = None
    seniority_detected: str | None = None
    measurements: dict[str, int] = {}
    requirements: list[RequirementItem] = []
    nice_to_have: list[RequirementItem] = []
    interview_focus: list[str] = []
    created_at: str


class InterviewRankItem(BaseModel):
    candidate_id: int
    name: str
    rank: int
    decision: str  # interview | backup | skip
    reason: str = ""


class InterviewRecOut(BaseModel):
    ranking: list[InterviewRankItem] = []
    verdict: str = ""


class BatchUploadOut(BaseModel):
    queued: int
    skipped: int = 0
    errors: list[str] = []


class ProcessOut(BaseModel):
    processed: int
    failed: int
    remaining: int


class QueueStatusOut(BaseModel):
    queued: int
    processing: int
    done: int
    error: int
    total: int


# ── Student coach ──
class StudentCvOut(BaseModel):
    filename: str
    cv_text: str


class AnalyzeIn(BaseModel):
    jd: str = Field(min_length=20)
    cv_text: str = Field(min_length=20)


class AnalyzeOut(BaseModel):
    match_score: int
    verdict: str          # strong | needs_work | weak
    summary: str
    strengths: list[str] = []
    gaps: list[str] = []
    missing_keywords: list[str] = []
    suggestions: list[str] = []
    clarifying_questions: list[str] = []


class QAItem(BaseModel):
    question: str
    answer: str = ""


class TailorIn(BaseModel):
    jd: str = Field(min_length=20)
    cv_text: str = Field(min_length=20)
    answers: list[QAItem] = []


class TailorOut(BaseModel):
    resume_markdown: str
    change_notes: list[str] = []


class PrepIn(BaseModel):
    jd: str = Field(min_length=20)
    cv_text: str = Field(default="", max_length=30000)


class ConceptItem(BaseModel):
    topic: str
    why: str = ""


class QuestionItem(BaseModel):
    question: str
    answer_hint: str = ""


class PrepOut(BaseModel):
    key_concepts: list[ConceptItem] = []
    questions: list[QuestionItem] = []
    project_tips: list[str] = []


class JobStat(BaseModel):
    id: int
    title: str
    total: int
    shortlisted: int
    pending: int


class DashboardOut(BaseModel):
    total_users: int
    total_jobs: int
    total_candidates: int
    shortlisted: int
    maybe: int
    rejected: int
    pending: int
    errors: int
    jobs: list[JobStat]
