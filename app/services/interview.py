"""Compare the top scored candidates and recommend who to interview first.

Useful when several candidates tie or sit very close on score — a senior hiring
manager breaks the tie on evidence depth, must-have coverage, seniority/domain
fit, and risk, judging ONLY against the JD.
"""

import json
from typing import Any

from fastapi import HTTPException

from app.config import get_settings

_SYS = """You are a senior hiring manager choosing who to INTERVIEW from an already
scored shortlist. You get the Job Description and the candidates (with match score,
measurements, matched/missing requirements, and a summary).

Rules:
- Judge ONLY against the JD — never invent requirements.
- When candidates have the SAME or very close scores, BREAK THE TIE explicitly
  using: more must-haves fully met, stronger and more recent evidence, better
  seniority & domain fit, and fewer risky gaps. Say exactly why one beats another.
- Be decisive and honest. Recommend "interview" only for those genuinely worth the
  manager's time; mark the rest "backup" or "skip".

Return STRICT JSON:
{
  "ranking": [
    {"candidate_id": int, "name": string, "rank": int,
     "decision": "interview" | "backup" | "skip", "reason": string}
  ],
  "verdict": string   // 2-4 sentences: who to interview first and WHY, incl. tie-breaks
}"""


def recommend_interview(
    job_title: str, job_description: str, candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not set.")
    from openai import OpenAI

    digest = []
    for c in candidates:
        digest.append(
            json.dumps(
                {
                    "candidate_id": c.get("id"),
                    "name": c.get("candidate_name") or c.get("filename"),
                    "score": c.get("score"),
                    "measurements": c.get("measurements"),
                    "matched": c.get("matched_requirements"),
                    "missing": c.get("missing_requirements"),
                    "years": c.get("years_experience"),
                    "summary": c.get("summary"),
                },
                ensure_ascii=False,
            )
        )
    user = (
        f"JOB TITLE:\n{job_title}\n\nJOB DESCRIPTION:\n{job_description}\n\n"
        "CANDIDATES (already scored):\n" + "\n".join(digest) +
        "\n\nRank them, break any ties, and return the JSON."
    )

    try:
        client = OpenAI(api_key=settings.openai_api_key, timeout=90.0)
        resp = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": _SYS}, {"role": "user", "content": user}],
        )
        data = json.loads((resp.choices[0].message.content or "{}").strip())
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e}") from e

    ranking = []
    for r in data.get("ranking") or []:
        if not isinstance(r, dict):
            continue
        dec = str(r.get("decision") or "backup").strip().lower()
        if dec not in {"interview", "backup", "skip"}:
            dec = "backup"
        try:
            cid = int(r.get("candidate_id") or 0)
        except (TypeError, ValueError):
            cid = 0
        try:
            rank = int(r.get("rank") or 0)
        except (TypeError, ValueError):
            rank = 0
        ranking.append(
            {
                "candidate_id": cid,
                "name": str(r.get("name") or "").strip(),
                "rank": rank,
                "decision": dec,
                "reason": str(r.get("reason") or "").strip(),
            }
        )
    ranking.sort(key=lambda x: x["rank"] or 999)
    return {"ranking": ranking, "verdict": str(data.get("verdict") or "").strip()}
