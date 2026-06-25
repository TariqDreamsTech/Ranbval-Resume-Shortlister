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

CRITICAL — JD IS THE ONLY SOURCE OF TRUTH:
Extract requirements ONLY from the Job Description text. Do NOT invent, assume, or
add any requirement the JD does not explicitly state. Every score, status, and
judgement MUST trace directly back to a line in the JD. If the JD doesn't ask for
something, it must not affect the result.

Screening rules (follow strictly):
1. First derive the role's HARD requirements from the Job Description: must-have
   skills, minimum years of experience, required domain, seniority, and any
   explicit mandatory qualifications (degree, certification, location, etc.).
   List each one and judge the CV against it with evidence (or note it as missing).
2. Judge the resume ONLY against those requirements and the actual evidence in it.
   Do not give credit for vague claims, buzzwords, or unrelated experience.
3. Be strict about RELEVANCE. A strong resume for a DIFFERENT role is still a
   REJECT. A junior applying to a senior role (or vice versa) is a poor match.
4. Penalize heavily: missing must-have skills, insufficient years, career gaps
   with no explanation, job-hopping, irrelevant industry, or generic filler.
5. Never inflate scores to be "nice". Most real applicant pools are mostly weak —
   your score distribution should reflect that.

Scoring (0-100) — BE HARSH. This is senior-level recruiting; the shortlist must
be interview-ready exact matches only:
- 90-100: EXACT match. Meets EVERY hard requirement with clear, specific evidence,
  the right seniority, and NO meaningful gaps. Could go straight to interview.
  Reserve this band — most candidates do NOT belong here.
- 75-89 : Strong, but has at least one real gap (a missing/weak skill, light on
  required years, or only vague evidence). NOT good enough to shortlist.
- 50-74 : Partial match with multiple gaps.
- 0-49  : Poor / irrelevant — do not waste the hiring manager's time.

HARD RULE: if the candidate is missing, weak on, or only vaguely demonstrates ANY
hard requirement from the JD, the score MUST stay below 90. Only flawless, fully
evidenced, exact matches score 90 or above. When unsure between two bands, pick
the LOWER one.

Verdict mapping:
- "shortlist": ONLY a 90+ exact match you would send straight to interview.
- "maybe": decent but has gaps — most "good" resumes land here, NOT shortlist.
- "reject": missing hard requirements or irrelevant.

Also rate the candidate on each dimension below from 0-100 (be just as harsh —
0 = not shown at all, 100 = perfectly evidenced and exceeds the JD):
- skills_match        : required hard/technical skills present with evidence
- experience_match    : depth & relevance of work experience vs the JD
- education_match     : degree / field / certifications the JD asks for
- seniority_fit       : right level (not too junior, not overqualified)
- domain_relevance    : same industry / problem space as the role
- responsibility_match: has actually done the JD's day-to-day responsibilities
- tools_match         : specific tools / frameworks / platforms named in the JD
- communication       : clarity, structure, and professionalism of the resume

Return STRICT JSON only, matching this shape:
{
  "candidate_name": string | null,
  "overall_score": integer 0-100,
  "verdict": "shortlist" | "maybe" | "reject",
  "years_experience": number | null,        // years the CANDIDATE has
  "years_required": number | null,           // years the JD demands (null if unstated)
  "seniority_required": string,              // level the JD asks for (e.g. "Senior")
  "seniority_detected": string,              // level the CV actually shows
  "measurements": {
    "skills_match": 0-100, "experience_match": 0-100, "education_match": 0-100,
    "seniority_fit": 0-100, "domain_relevance": 0-100, "responsibility_match": 0-100,
    "tools_match": 0-100, "communication": 0-100
  },
  "requirements": [          // ONE entry per hard requirement found in the JD
    {
      "requirement": string, // the requirement, taken from the JD
      "status": "met" | "partial" | "missing",
      "evidence": string     // exact CV evidence, or "" if missing
    }, ...
  ],
  "interview_focus": [string, ...],  // what to probe in interview — based ONLY on JD gaps
  "matched_requirements": [string, ...],
  "missing_requirements": [string, ...],
  "red_flags": [string, ...],
  "key_skills": [string, ...],
  "summary": string  // one or two sentences, blunt and specific
}"""

_MEASURE_KEYS = [
    "skills_match",
    "experience_match",
    "education_match",
    "seniority_fit",
    "domain_relevance",
    "responsibility_match",
    "tools_match",
    "communication",
]


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
    client,
    *,
    job_title: str,
    job_description: str,
    resume_text: str,
    threshold: int | None = None,
) -> dict[str, Any]:
    """Score a single resume. Retries on rate-limit / transient errors."""
    settings = get_settings()
    threshold = threshold or settings.shortlist_threshold

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

    missing = _as_str_list(data.get("missing_requirements"))
    has_critical_gap = any(_looks_critical(m) for m in missing)

    # Verdict is driven by the SCORE + threshold, not the model's own label, so a
    # 75/85 "strong but gappy" resume can never slip through as a shortlist.
    # Shortlist = score >= threshold (default 90) AND no critical requirement gap.
    if score >= threshold and not has_critical_gap:
        verdict = "shortlist"
        recommended = True
    elif score >= 60:
        verdict = "maybe"
        recommended = False
    else:
        verdict = "reject"
        recommended = False

    years = data.get("years_experience")
    try:
        years = float(years) if years is not None else None
    except (TypeError, ValueError):
        years = None

    name = data.get("candidate_name")
    name = str(name).strip() if name else None

    years_required = data.get("years_required")
    try:
        years_required = float(years_required) if years_required is not None else None
    except (TypeError, ValueError):
        years_required = None

    return {
        "candidate_name": name,
        "score": score,
        "verdict": verdict,
        "recommended": recommended,
        "years_experience": years,
        "years_required": years_required,
        "seniority_required": str(data.get("seniority_required") or "").strip(),
        "seniority_detected": str(data.get("seniority_detected") or "").strip(),
        "measurements": _measurements(data.get("measurements")),
        "requirements": _requirements(data.get("requirements")),
        "interview_focus": _as_str_list(data.get("interview_focus")),
        "matched_requirements": _as_str_list(data.get("matched_requirements")),
        "missing_requirements": missing,
        "red_flags": _as_str_list(data.get("red_flags")),
        "key_skills": _as_str_list(data.get("key_skills")),
        "summary": str(data.get("summary") or "").strip(),
    }


def _requirements(raw: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return out
    for r in raw[:40]:
        if not isinstance(r, dict):
            continue
        req = str(r.get("requirement") or "").strip()
        if not req:
            continue
        status = str(r.get("status") or "missing").strip().lower()
        if status not in {"met", "partial", "missing"}:
            status = "missing"
        out.append(
            {"requirement": req, "status": status, "evidence": str(r.get("evidence") or "").strip()}
        )
    return out


def _measurements(raw: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    src = raw if isinstance(raw, dict) else {}
    for k in _MEASURE_KEYS:
        try:
            out[k] = max(0, min(100, int(round(float(src.get(k, 0))))))
        except (TypeError, ValueError):
            out[k] = 0
    return out


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
