"""Resume intake + scoring at scale.

Flow:
  1. Upload (single or batch) → extract text + enqueue (status='queued'). Fast.
  2. /process → atomically CLAIM a small batch, score them concurrently with
     retries, write results. Clients call /process repeatedly until the queue
     drains; many clients/instances can process in parallel safely.
  3. /queue-status → progress numbers for the UI.
"""

import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.config import get_settings
from app.database import CANDIDATES_TABLE, JOBS_TABLE, get_client
from app.deps import require_recruiter
from app.schemas import (
    BatchUploadOut,
    CandidateOut,
    ProcessOut,
    QueueStatusOut,
)
from app.services.extract import extract_text
from app.services.scoring import async_client, score_one_async

router = APIRouter(
    prefix="/api/jobs/{job_id}", tags=["resumes"], dependencies=[Depends(require_recruiter)]
)

_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per resume


# ── Upload (enqueue only — no scoring in the request) ──
@router.post("/resumes", response_model=CandidateOut)
async def upload_resume(job_id: int, file: UploadFile = File(...)) -> CandidateOut:
    client = get_client()
    _get_job(client, job_id)
    raw = await file.read()
    row = _enqueue_one(client, job_id, file.filename or "resume", raw)
    return _to_candidate_out(row)


@router.post("/resumes/batch", response_model=BatchUploadOut)
async def upload_resumes_batch(
    job_id: int, files: list[UploadFile] = File(...)
) -> BatchUploadOut:
    client = get_client()
    _get_job(client, job_id)

    queued, skipped, errors = 0, 0, []
    for f in files:
        try:
            raw = await f.read()
            _enqueue_one(client, job_id, f.filename or "resume", raw)
            queued += 1
        except HTTPException as e:
            skipped += 1
            errors.append(f"{f.filename}: {e.detail}")
        except Exception as e:  # noqa: BLE001
            skipped += 1
            errors.append(f"{f.filename}: {e}")
    return BatchUploadOut(queued=queued, skipped=skipped, errors=errors[:20])


# ── Worker: claim a batch and score concurrently ──
@router.post("/process", response_model=ProcessOut)
async def process_queue(job_id: int) -> ProcessOut:
    settings = get_settings()
    client = get_client()
    job = _get_job(client, job_id)

    # 1. Atomically claim up to N queued rows for this job.
    pending = (
        client.table(CANDIDATES_TABLE)
        .select("id")
        .eq("job_id", job_id)
        .eq("status", "queued")
        .order("id")
        .limit(settings.process_batch)
        .execute()
        .data
        or []
    )
    if not pending:
        return ProcessOut(processed=0, failed=0, remaining=0)

    ids = [r["id"] for r in pending]
    # The `.eq(status,'queued')` guard makes this claim safe under concurrent
    # workers: whoever flips a row first owns it; others get fewer rows back.
    claimed = (
        client.table(CANDIDATES_TABLE)
        .update({"status": "processing"})
        .in_("id", ids)
        .eq("status", "queued")
        .execute()
        .data
        or []
    )
    if not claimed:
        remaining = _count(client, job_id, "queued")
        return ProcessOut(processed=0, failed=0, remaining=remaining)

    # 2. Score the claimed rows concurrently (bounded), no DB in the hot path.
    oai = async_client()
    sem = asyncio.Semaphore(settings.process_concurrency)

    job_threshold = job.get("threshold") or settings.shortlist_threshold

    async def _score(row: dict):
        async with sem:
            try:
                result = await score_one_async(
                    oai,
                    job_title=job["title"],
                    job_description=job["description"],
                    resume_text=row.get("resume_text") or "",
                    threshold=job_threshold,
                )
                return row["id"], result, None
            except Exception as e:  # noqa: BLE001
                return row["id"], None, str(e)[:400]

    results = await asyncio.gather(*[_score(r) for r in claimed])

    # 3. Persist results.
    processed, failed = 0, 0
    for cid, result, err in results:
        if result is not None:
            client.table(CANDIDATES_TABLE).update(
                {
                    "status": "done",
                    "error": None,
                    "candidate_name": result["candidate_name"],
                    "score": result["score"],
                    "verdict": result["verdict"],
                    "recommended": result["recommended"],
                    "summary": result["summary"],
                    "details": {
                        "matched_requirements": result["matched_requirements"],
                        "missing_requirements": result["missing_requirements"],
                        "red_flags": result["red_flags"],
                        "key_skills": result["key_skills"],
                        "years_experience": result["years_experience"],
                        "years_required": result.get("years_required"),
                        "seniority_required": result.get("seniority_required"),
                        "seniority_detected": result.get("seniority_detected"),
                        "measurements": result.get("measurements", {}),
                        "requirements": result.get("requirements", []),
                        "interview_focus": result.get("interview_focus", []),
                    },
                }
            ).eq("id", cid).execute()
            processed += 1
        else:
            client.table(CANDIDATES_TABLE).update(
                {"status": "error", "error": err}
            ).eq("id", cid).execute()
            failed += 1

    remaining = _count(client, job_id, "queued")
    return ProcessOut(processed=processed, failed=failed, remaining=remaining)


# ── Requeue an errored candidate ──
@router.post("/candidates/{candidate_id}/retry", response_model=CandidateOut)
def retry_candidate(job_id: int, candidate_id: int) -> CandidateOut:
    client = get_client()
    res = (
        client.table(CANDIDATES_TABLE)
        .update({"status": "queued", "error": None})
        .eq("id", candidate_id)
        .eq("job_id", job_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return _to_candidate_out(res.data[0])


# ── Queue progress ──
@router.get("/queue-status", response_model=QueueStatusOut)
def queue_status(job_id: int) -> QueueStatusOut:
    client = get_client()
    _get_job(client, job_id)
    q = _count(client, job_id, "queued")
    p = _count(client, job_id, "processing")
    d = _count(client, job_id, "done")
    e = _count(client, job_id, "error")
    return QueueStatusOut(queued=q, processing=p, done=d, error=e, total=q + p + d + e)


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
def _enqueue_one(client, job_id: int, filename: str, raw: bytes) -> dict:
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(raw) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB).")
    resume_text = extract_text(filename, raw)  # cheap CPU work, raises on bad files
    res = (
        client.table(CANDIDATES_TABLE)
        .insert(
            {
                "job_id": job_id,
                "filename": filename,
                "status": "queued",
                "verdict": "pending",
                "score": 0,
                "recommended": False,
                "resume_text": resume_text,
            }
        )
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=502, detail="Failed to enqueue resume")
    return res.data[0]


def _count(client, job_id: int, status: str) -> int:
    return (
        client.table(CANDIDATES_TABLE)
        .select("id", count="exact")
        .eq("job_id", job_id)
        .eq("status", status)
        .execute()
        .count
        or 0
    )


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
        score=row.get("score", 0) or 0,
        verdict=row.get("verdict", "pending"),
        recommended=bool(row.get("recommended")),
        status=row.get("status", "done"),
        error=row.get("error"),
        summary=row.get("summary"),
        matched_requirements=details.get("matched_requirements", []),
        missing_requirements=details.get("missing_requirements", []),
        red_flags=details.get("red_flags", []),
        key_skills=details.get("key_skills", []),
        years_experience=details.get("years_experience"),
        years_required=details.get("years_required"),
        seniority_required=details.get("seniority_required"),
        seniority_detected=details.get("seniority_detected"),
        measurements=details.get("measurements", {}),
        requirements=details.get("requirements", []),
        interview_focus=details.get("interview_focus", []),
        created_at=str(row.get("created_at", "")),
    )
