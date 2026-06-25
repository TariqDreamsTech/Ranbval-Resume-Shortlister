"""Student career coach — gap analysis, resume tailoring, and interview prep.

These are single-shot interactive calls (one student at a time), so a synchronous
OpenAI client is fine. The coach is honest and JD-driven: it never invents
experience the student doesn't have, and it grounds interview prep in the JD.
"""

import json
from typing import Any

from fastapi import HTTPException

from app.config import get_settings


def _client():
    s = get_settings()
    if not s.openai_api_key:
        raise HTTPException(
            status_code=503, detail="OPENAI_API_KEY is not set in the environment."
        )
    from openai import OpenAI

    return OpenAI(api_key=s.openai_api_key, timeout=90.0)


def _chat(system: str, user: str, *, temperature: float, max_tokens: int) -> dict[str, Any]:
    try:
        resp = _client().chat.completions.create(
            model=get_settings().openai_model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e}") from e
    try:
        return json.loads((resp.choices[0].message.content or "").strip())
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Model returned invalid JSON.") from None


def _slist(v: Any, limit: int = 30) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if str(x).strip()][:limit]


# ── 1. Gap analysis ──
_ANALYZE_SYS = """You are an honest, sharp career coach helping a STUDENT/candidate
fit a specific job. You are given a Job Description (JD) and the candidate's current CV.

Be truthful and strict — do NOT flatter. Compare the CV against the JD's real
requirements and tell the candidate exactly where they fall short and how to fix it.

Then propose CLARIFYING QUESTIONS you must ask before rewriting their resume — ask
about real experience, projects, tools, metrics, and achievements that the JD wants
but the CV doesn't clearly show. These answers will be used to tailor the resume
WITHOUT fabricating anything.

Return STRICT JSON:
{
  "match_score": integer 0-100,          // how well the CURRENT CV fits the JD
  "verdict": "strong" | "needs_work" | "weak",
  "summary": string,                     // 1-2 blunt sentences
  "strengths": [string, ...],            // what already matches
  "gaps": [string, ...],                 // what's missing vs the JD
  "missing_keywords": [string, ...],     // important JD terms absent from the CV
  "suggestions": [string, ...],          // concrete fixes
  "clarifying_questions": [string, ...]  // 4-8 questions to ask before rewriting
}"""


def analyze_cv(jd: str, cv_text: str) -> dict[str, Any]:
    data = _chat(
        _ANALYZE_SYS,
        f"JOB DESCRIPTION:\n{jd}\n\nCANDIDATE CV:\n{cv_text}\n\n"
        "Analyze honestly and return the JSON.",
        temperature=0,
        max_tokens=1200,
    )
    try:
        score = max(0, min(100, int(round(float(data.get("match_score", 0))))))
    except (TypeError, ValueError):
        score = 0
    verdict = str(data.get("verdict", "weak")).strip().lower()
    if verdict not in {"strong", "needs_work", "weak"}:
        verdict = "weak"
    return {
        "match_score": score,
        "verdict": verdict,
        "summary": str(data.get("summary") or "").strip(),
        "strengths": _slist(data.get("strengths")),
        "gaps": _slist(data.get("gaps")),
        "missing_keywords": _slist(data.get("missing_keywords")),
        "suggestions": _slist(data.get("suggestions")),
        "clarifying_questions": _slist(data.get("clarifying_questions"), limit=10),
    }


# ── 2. Resume tailoring ──
_TAILOR_SYS = """You are an expert resume writer. Rewrite the candidate's resume so it
is tailored to the target JD and ATS-friendly.

HARD RULES:
- NEVER fabricate experience, employers, dates, or credentials. Use ONLY what's in
  the original CV plus the candidate's answers to the clarifying questions.
- Surface the JD's required skills/keywords where the candidate genuinely has them.
- Use strong, quantified bullet points (action verb + what + measurable impact).
- Keep it clean, well-structured, one coherent resume.

Return STRICT JSON:
{
  "resume_markdown": string,    // the full tailored resume in clean Markdown
  "change_notes": [string, ...] // bullet list of the key changes you made and why
}"""


def tailor_resume(jd: str, cv_text: str, answers: list[dict[str, str]]) -> dict[str, Any]:
    qa = "\n".join(
        f"Q: {a.get('question','')}\nA: {a.get('answer','')}" for a in answers if a.get("answer")
    ) or "(no extra answers provided)"
    data = _chat(
        _TAILOR_SYS,
        f"TARGET JOB DESCRIPTION:\n{jd}\n\nORIGINAL CV:\n{cv_text}\n\n"
        f"CANDIDATE'S ANSWERS TO CLARIFYING QUESTIONS:\n{qa}\n\n"
        "Produce the tailored resume now. Return the JSON.",
        temperature=0.3,
        max_tokens=2500,
    )
    return {
        "resume_markdown": str(data.get("resume_markdown") or "").strip(),
        "change_notes": _slist(data.get("change_notes")),
    }


# ── 3. Interview prep ──
_PREP_SYS = """You are an interview coach. Based on the target JD (and the candidate's
CV/projects if given), produce focused interview preparation.

Cover EVERYTHING the JD implies — go down to the SMALL/fundamental questions too, not
just the hard ones. Ground "project_tips" in the candidate's actual projects from the
CV: for each, what they must be ready to explain (decisions, trade-offs, concepts).

Return STRICT JSON:
{
  "key_concepts": [ {"topic": string, "why": string}, ... ],     // concepts to study, JD-driven
  "questions":    [ {"question": string, "answer_hint": string}, ... ],  // likely Qs incl. small ones
  "project_tips": [string, ...]   // per the candidate's projects: what to master/expect
}"""


def interview_prep(jd: str, cv_text: str) -> dict[str, Any]:
    data = _chat(
        _PREP_SYS,
        f"TARGET JOB DESCRIPTION:\n{jd}\n\nCANDIDATE CV / PROJECTS:\n{cv_text or '(not provided)'}\n\n"
        "Return thorough prep as JSON. Include small/fundamental questions too.",
        temperature=0.2,
        max_tokens=2000,
    )
    concepts = []
    for c in data.get("key_concepts", []) if isinstance(data.get("key_concepts"), list) else []:
        if isinstance(c, dict) and str(c.get("topic", "")).strip():
            concepts.append({"topic": str(c["topic"]).strip(), "why": str(c.get("why") or "").strip()})
    questions = []
    for q in data.get("questions", []) if isinstance(data.get("questions"), list) else []:
        if isinstance(q, dict) and str(q.get("question", "")).strip():
            questions.append(
                {"question": str(q["question"]).strip(), "answer_hint": str(q.get("answer_hint") or "").strip()}
            )
    return {
        "key_concepts": concepts[:30],
        "questions": questions[:40],
        "project_tips": _slist(data.get("project_tips")),
    }
