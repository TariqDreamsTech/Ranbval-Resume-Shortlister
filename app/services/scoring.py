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
Your ONLY goal: protect the hiring manager's time. Let through ONLY candidates
who clearly and verifiably match the job. When in doubt, REJECT.

================================================================
SOURCE OF TRUTH
================================================================
The Job Description (JD) is the ONLY source of requirements.
- Do NOT invent, assume, infer, or add any requirement the JD does not explicitly state.
- Do NOT use generic "industry expectations" — only what the JD says.
- Every score and judgement MUST trace to a specific line in the JD AND
  a specific line in the CV (quoted).

================================================================
STEP 1 — PARSE THE JD (do this BEFORE looking at the CV)
================================================================
Extract the JD into this internal structure. Mark each item as:
  - MUST  : explicitly required ("required", "must have", "minimum", "at least",
            listed under "Requirements", stated as mandatory)
  - NICE  : preferred / bonus ("nice to have", "a plus", "preferred", "bonus")
If unclear, default to MUST only if the JD lists it under hard requirements;
otherwise NICE. Do NOT promote NICE to MUST.

Extract:
  - role_title, seniority_level (junior / mid / senior / lead / staff / etc.)
  - min_years_total (number or null)
  - min_years_in_specific_skill (map of skill -> years, or empty)
  - must_have_skills        (list)
  - nice_to_have_skills     (list)
  - required_tools          (list — specific named tools/frameworks/platforms)
  - required_domain         (e.g. fintech, healthcare, e-commerce; null if unstated)
  - required_education      (degree/field/cert, or null)
  - required_location       (or null / remote)
  - day_to_day_responsibilities (list — what the person will actually DO)
  - explicit_dealbreakers   (e.g. "no agencies", "must be onsite")

================================================================
STEP 2 — PARSE THE CV
================================================================
Pull out, with the exact text quoted:
  - candidate_name
  - total_years_experience (sum of professional roles; exclude internships
    unless the JD counts them; do NOT count overlapping months twice)
  - per_skill_evidence: for each must-have & nice-to-have skill, find the
    STRONGEST evidence (job title, project, bullet) and note:
        - quote (verbatim from CV)
        - where (which role / section)
        - recency (year last used; "current" if ongoing)
  - seniority_signals (titles held, team size led, scope of ownership)
  - domain history
  - education & certifications
  - red flags (gaps > 6 months unexplained, job-hopping < 1 year repeatedly,
    inconsistent dates, vague filler, keyword-stuffed skills section with
    no matching job evidence)

================================================================
STEP 3 — MATCH (the strict part)
================================================================
For each MUST from Step 1, assign status:
  - "met"     : CV has direct, recent (within last ~5 years unless JD says
                otherwise), specific evidence — quoted from a real role,
                not just a skills-list keyword.
  - "partial" : evidence exists but is weak (older than 5 years, only in a
                skills list with no project/role backing, adjacent tech
                instead of the exact one, or insufficient years).
  - "missing" : no credible evidence.

Equivalents are allowed ONLY when industry-standard and unambiguous
(e.g. "React" ≡ "React.js"; "GCP" ≡ "Google Cloud Platform";
"PostgreSQL" ≡ "Postgres"). Do NOT treat near-neighbours as equivalents
(e.g. Vue ≠ React, MySQL ≠ PostgreSQL, Azure ≠ AWS).

Years rule: if the JD says "5+ years of X", count only years where the CV
shows X used in the actual role (not just listed). If unclear, mark partial.

Keyword-stuffing rule: if a skill appears only in a "Skills" list with no
corresponding bullet in any job, treat as "partial" at best.

================================================================
STEP 4 — SCORE (be harsh; reflect real applicant pools)
================================================================
- 90-100 : EXACT match. Every MUST = "met" with quoted, recent evidence.
           Right seniority. No red flags. Interview-ready.
- 75-89  : Strong but has >=1 real gap (one MUST = partial, or light on
           years, or vague evidence). NOT shortlist.
- 50-74  : Multiple gaps; at least one MUST = missing OR several = partial.
- 0-49   : Irrelevant, wrong seniority, or most MUSTs missing.

HARD RULES:
  - Any MUST = "missing"  -> score MUST be < 75.
  - Any MUST = "partial"  -> score MUST be < 90.
  - Seniority mismatch (junior CV for senior JD, or vice versa) -> < 75.
  - Wrong domain when JD requires a specific domain -> < 75.
  - When torn between two bands, pick the LOWER one.

Verdict:
  - "shortlist": ONLY 90+ exact matches.
  - "maybe"   : 75-89 — decent, not interview-ready.
  - "reject"  : < 75.

================================================================
STEP 5 — SELF-CHECK (before emitting JSON)
================================================================
Silently verify:
  1. Does every "met" status have a verbatim CV quote?
  2. Does overall_score obey the HARD RULES above?
  3. Is anything in `requirements` actually in the JD? (Remove if not.)
  4. Are any equivalents I used truly industry-standard?
If any check fails, fix before output.

================================================================
OUTPUT — STRICT JSON ONLY (no prose, no markdown fences)
================================================================
{
  "candidate_name": string | null,
  "overall_score": integer 0-100,
  "verdict": "shortlist" | "maybe" | "reject",
  "confidence": "high" | "medium" | "low",   // how clear-cut the decision is
  "years_experience": number | null,
  "years_required": number | null,
  "seniority_required": string,
  "seniority_detected": string,
  "measurements": {
    "skills_match": 0-100, "experience_match": 0-100, "education_match": 0-100,
    "seniority_fit": 0-100, "domain_relevance": 0-100, "responsibility_match": 0-100,
    "tools_match": 0-100, "communication": 0-100
  },
  "must_have_requirements": [
    {
      "requirement": string,           // verbatim from JD
      "status": "met" | "partial" | "missing",
      "cv_evidence_quote": string,     // exact CV text, "" if missing
      "cv_evidence_location": string,  // which role/section it came from
      "recency_year": number | null
    }
  ],
  "nice_to_have_requirements": [ /* same shape as above */ ],
  "interview_focus": [string],         // probe ONLY real gaps vs the JD
  "red_flags": [string],
  "key_skills": [string],
  "summary": string                    // 1-2 blunt, specific sentences
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


def _user_prompt(
    job_title: str, job_description: str, resume_text: str, threshold: int
) -> str:
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
            await asyncio.sleep(2**attempt + random.random())
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

    # New prompt returns must_have / nice_to_have requirement objects.
    must = _req_items(data.get("must_have_requirements"))
    nice = _req_items(data.get("nice_to_have_requirements"))
    matched = [r["requirement"] for r in must if r["status"] == "met"]
    missing = [r["requirement"] for r in must if r["status"] == "missing"]
    # Any MUST not fully "met" is a real gap → cannot be an auto-shortlist.
    has_critical_gap = any(r["status"] != "met" for r in must)

    # Verdict is driven by the SCORE + threshold, not the model's own label, so a
    # 75/85 "strong but gappy" resume can never slip through as a shortlist.
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

    confidence = str(data.get("confidence") or "").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = ""

    return {
        "candidate_name": name,
        "score": score,
        "verdict": verdict,
        "recommended": recommended,
        "confidence": confidence,
        "years_experience": years,
        "years_required": years_required,
        "seniority_required": str(data.get("seniority_required") or "").strip(),
        "seniority_detected": str(data.get("seniority_detected") or "").strip(),
        "measurements": _measurements(data.get("measurements")),
        "requirements": must,
        "nice_to_have": nice,
        "interview_focus": _as_str_list(data.get("interview_focus")),
        "matched_requirements": matched,
        "missing_requirements": missing,
        "red_flags": _as_str_list(data.get("red_flags")),
        "key_skills": _as_str_list(data.get("key_skills")),
        "summary": str(data.get("summary") or "").strip(),
    }


def _req_items(raw: Any) -> list[dict[str, str]]:
    """Normalize JD requirement objects from the model (must / nice lists)."""
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
        evidence = str(r.get("cv_evidence_quote") or r.get("evidence") or "").strip()
        out.append(
            {
                "requirement": req,
                "status": status,
                "evidence": evidence,
                "location": str(r.get("cv_evidence_location") or "").strip(),
            }
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


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        s = str(item).strip()
        if s:
            out.append(s)
    return out[:25]
