"""Strict resume screening via OpenAI — async, concurrency-safe, with retries.

The screener is deliberately harsh: it defaults to REJECT unless the candidate
clearly satisfies the role's hard requirements. Scoring runs asynchronously so a
single /process call can score several resumes concurrently, with exponential
backoff on rate limits / transient errors.
"""

import asyncio
import json
import random
from typing import Any

from fastapi import HTTPException

from app.config import get_settings

_SYSTEM_PROMPT = """You are a ruthless, senior technical recruiter screening resumes.
Your only goal is to protect the hiring manager's time: let through ONLY candidates
who clearly match the job. When in doubt, REJECT.

Screening rules (follow strictly):
1. First derive the role's HARD requirements from the Job Description: must-have
   skills, minimum years of experience, required domain, seniority, and any
   explicit mandatory qualifications (degree, certification, location, etc.).
2. Judge the resume ONLY against those requirements and the actual evidence in it.
   Do not give credit for vague claims, buzzwords, or unrelated experience.
3. Be strict about RELEVANCE. A strong resume for a DIFFERENT role is still a
   REJECT. A junior applying to a senior role (or vice versa) is a poor match.
4. Penalize heavily: missing must-have skills, insufficient years, career gaps
   with no explanation, job-hopping, irrelevant industry, or generic filler.
5. Never inflate scores to be "nice". Most real applicant pools are mostly weak —
   your score distribution should reflect that.

Scoring (0-100):
- 85-100: excellent, clearly meets/exceeds every hard requirement.
- 70-84 : solid match, meets the must-haves with minor gaps.
- 50-69 : partial match, missing one or more important requirements.
- 0-49  : poor / irrelevant — do not waste the hiring manager's time.

Verdict mapping:
- "shortlist": confidently meets the hard requirements (score typically >= threshold).
- "maybe": borderline; a recruiter should glance but expectations low.
- "reject": missing hard requirements or irrelevant.

Return STRICT JSON only, matching this shape:
{
  "candidate_name": string | null,
  "overall_score": integer 0-100,
  "verdict": "shortlist" | "maybe" | "reject",
  "years_experience": number | null,
  "matched_requirements": [string, ...],
  "missing_requirements": [string, ...],
  "red_flags": [string, ...],
  "key_skills": [string, ...],
  "summary": string  // one or two sentences, blunt and specific
}"""


def async_client():
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not set. Add it to your environment.",
        )
    from openai import AsyncOpenAI

    # Per-call timeout keeps a stuck request from eating the whole batch budget.
    return AsyncOpenAI(api_key=settings.openai_api_key, timeout=40.0, max_retries=0)


def _user_prompt(job_title: str, job_description: str, resume_text: str, threshold: int) -> str:
    return (
        f"JOB TITLE:\n{job_title}\n\n"
        f"JOB DESCRIPTION:\n{job_description}\n\n"
        f"SHORTLIST THRESHOLD (score must be >= this to shortlist): {threshold}\n\n"
        f"RESUME TEXT:\n{resume_text}\n\n"
        "Screen this resume against the job. Be strict. Return the JSON only."
    )


async def score_one_async(
    client, *, job_title: str, job_description: str, resume_text: str
) -> dict[str, Any]:
    """Score a single resume. Retries on rate-limit / transient errors."""
    settings = get_settings()
    threshold = settings.shortlist_threshold

    # Import lazily so the module loads even if openai isn't installed yet.
    from openai import APIConnectionError, APITimeoutError, RateLimitError

    last_err: Exception | None = None
    for attempt in range(settings.openai_max_retries + 1):
        try:
            resp = await client.chat.completions.create(
                model=settings.openai_model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": _user_prompt(
                            job_title, job_description, resume_text, threshold
                        ),
                    },
                ],
            )
            raw = (resp.choices[0].message.content or "").strip()
            return _normalize(json.loads(raw), threshold)
        except (RateLimitError, APITimeoutError, APIConnectionError) as e:
            last_err = e
            if attempt >= settings.openai_max_retries:
                break
            # exponential backoff with jitter: 1, 2, 4, 8s (+ up to 1s jitter)
            await asyncio.sleep(2 ** attempt + random.random())
        except json.JSONDecodeError as e:
            last_err = e
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            break

    raise RuntimeError(f"scoring failed: {last_err}")


def _normalize(data: dict[str, Any], threshold: int) -> dict[str, Any]:
    """Coerce model output into a safe, consistent shape + enforce strictness."""
    try:
        score = int(round(float(data.get("overall_score", 0))))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))

    verdict = str(data.get("verdict", "reject")).strip().lower()
    if verdict not in {"shortlist", "maybe", "reject"}:
        verdict = "reject"

    missing = _as_str_list(data.get("missing_requirements"))
    recommended = score >= threshold and verdict == "shortlist"
    if recommended and any(_looks_critical(m) for m in missing):
        recommended = False
        verdict = "maybe"

    years = data.get("years_experience")
    try:
        years = float(years) if years is not None else None
    except (TypeError, ValueError):
        years = None

    name = data.get("candidate_name")
    name = str(name).strip() if name else None

    return {
        "candidate_name": name,
        "score": score,
        "verdict": verdict,
        "recommended": recommended,
        "years_experience": years,
        "matched_requirements": _as_str_list(data.get("matched_requirements")),
        "missing_requirements": missing,
        "red_flags": _as_str_list(data.get("red_flags")),
        "key_skills": _as_str_list(data.get("key_skills")),
        "summary": str(data.get("summary") or "").strip(),
    }


def _looks_critical(text: str) -> bool:
    t = text.lower()
    keywords = ("must", "required", "mandatory", "minimum", "years", "degree", "essential")
    return any(k in t for k in keywords)


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        s = str(item).strip()
        if s:
            out.append(s)
    return out[:25]
