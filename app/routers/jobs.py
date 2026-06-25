"""Job (Job Description) endpoints — backed by Supabase."""

from fastapi import APIRouter, Depends, HTTPException

from app.database import CANDIDATES_TABLE, JOBS_TABLE, get_client
from app.deps import require_user
from app.schemas import JobCreate, JobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(require_user)])


@router.post("", response_model=JobOut)
def create_job(body: JobCreate) -> JobOut:
    client = get_client()
    res = (
        client.table(JOBS_TABLE)
        .insert({"title": body.title.strip(), "description": body.description.strip()})
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=502, detail="Failed to create job")
    return _to_job_out(res.data[0], candidate_count=0)


@router.get("", response_model=list[JobOut])
def list_jobs() -> list[JobOut]:
    client = get_client()
    jobs = (
        client.table(JOBS_TABLE).select("*").order("id", desc=True).execute().data
        or []
    )
    counts = _candidate_counts(client)
    return [_to_job_out(j, candidate_count=counts.get(j["id"], 0)) for j in jobs]


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int) -> JobOut:
    client = get_client()
    row = _fetch_job(client, job_id)
    cnt = (
        client.table(CANDIDATES_TABLE)
        .select("id", count="exact")
        .eq("job_id", job_id)
        .execute()
        .count
        or 0
    )
    return _to_job_out(row, candidate_count=cnt)


@router.delete("/{job_id}")
def delete_job(job_id: int) -> dict[str, str]:
    client = get_client()
    client.table(JOBS_TABLE).delete().eq("id", job_id).execute()
    return {"status": "deleted"}


# ── helpers ──
def _fetch_job(client, job_id: int) -> dict:
    res = client.table(JOBS_TABLE).select("*").eq("id", job_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Job not found")
    return res.data[0]


def _candidate_counts(client) -> dict[int, int]:
    """One query → {job_id: count} (fine for the modest job counts here)."""
    rows = client.table(CANDIDATES_TABLE).select("job_id").execute().data or []
    counts: dict[int, int] = {}
    for r in rows:
        jid = r["job_id"]
        counts[jid] = counts.get(jid, 0) + 1
    return counts


def _to_job_out(row: dict, candidate_count: int) -> JobOut:
    return JobOut(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        created_at=str(row.get("created_at", "")),
        candidate_count=candidate_count,
    )
