"""Pydantic request/response models."""

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=20)


class JobOut(BaseModel):
    id: int
    title: str
    description: str
    created_at: str
    candidate_count: int = 0


class CandidateOut(BaseModel):
    id: int
    job_id: int
    filename: str
    candidate_name: str | None = None
    score: int
    verdict: str
    recommended: bool
    summary: str | None = None
    matched_requirements: list[str] = []
    missing_requirements: list[str] = []
    red_flags: list[str] = []
    key_skills: list[str] = []
    years_experience: float | None = None
    created_at: str
