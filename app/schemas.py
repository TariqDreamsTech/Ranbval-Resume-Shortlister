"""Pydantic request/response models."""

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class LoginOut(BaseModel):
    token: str
    name: str
    role: str


class UserOut(BaseModel):
    id: int
    name: str
    password: str
    role: str
    created_at: str


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)
    role: str = Field(default="user")


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    password: str | None = Field(default=None, max_length=200)
    role: str | None = None


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
