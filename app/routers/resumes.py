"""Resume upload + scoring + candidate listing — backed by Supabase."""

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.database import CANDIDATES_TABLE, JOBS_TABLE, get_client
from app.schemas import CandidateOut
from app.services.extract import extract_text
from app.services.scoring import score_resume

router = APIRouter(prefix="/api/jobs/{job_id}", tags=["resumes"])

_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per resume


@router.post("/resumes", response_model=CandidateOut)
async def upload_resume(job_id: int, file: UploadFile = File(...)) -> CandidateOut:
    client = get_client()
    job = _get_job(client, job_id)

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(raw) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB).")

    resume_text = extract_text(file.filename or "resume", raw)

    result = score_resume(
        job_title=job["title"],
        job_description=job["description"],
        resume_text=resume_text,
    )

    details = {
        "matched_requirements": result["matched_requirements"],
        "missing_requirements": result["missing_requirements"],
        "red_flags": result["red_flags"],
        "key_skills": result["key_skills"],
        "years_experience": result["years_experience"],
    }

    res = (
        client.table(CANDIDATES_TABLE)
        .insert(
            {
                "job_id": job_id,
                "filename": file.filename or "resume",
                "candidate_name": result["candidate_name"],
                "score": result["score"],
                "verdict": result["verdict"],
                "recommended": result["recommended"],
                "summary": result["summary"],
                "details": details,
            }
        )
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=502, detail="Failed to save candidate")
    return _to_candidate_out(res.data[0])


@router.get("/candidates", response_model=list[CandidateOut])
def list_candidates(job_id: int) -> list[CandidateOut]:
    client = get_client()
    _get_job(client, job_id)
    rows = (
        client.table(CANDIDATES_TABLE)
        .select("*")
        .eq("job_id", job_id)
        .order("recommended", desc=True)
        .order("score", desc=True)
        .order("id", desc=True)
        .execute()
        .data
        or []
    )
    return [_to_candidate_out(r) for r in rows]


@router.delete("/candidates/{candidate_id}")
def delete_candidate(job_id: int, candidate_id: int) -> dict[str, str]:
    client = get_client()
    client.table(CANDIDATES_TABLE).delete().eq("id", candidate_id).eq(
        "job_id", job_id
    ).execute()
    return {"status": "deleted"}


# ── helpers ──
def _get_job(client, job_id: int) -> dict:
    res = client.table(JOBS_TABLE).select("*").eq("id", job_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Job not found")
    return res.data[0]


def _to_candidate_out(row: dict) -> CandidateOut:
    details = row.get("details") or {}
    if not isinstance(details, dict):
        details = {}
    return CandidateOut(
        id=row["id"],
        job_id=row["job_id"],
        filename=row["filename"],
        candidate_name=row.get("candidate_name"),
        score=row.get("score", 0),
        verdict=row.get("verdict", "reject"),
        recommended=bool(row.get("recommended")),
        summary=row.get("summary"),
        matched_requirements=details.get("matched_requirements", []),
        missing_requirements=details.get("missing_requirements", []),
        red_flags=details.get("red_flags", []),
        key_skills=details.get("key_skills", []),
        years_experience=details.get("years_experience"),
        created_at=str(row.get("created_at", "")),
    )
