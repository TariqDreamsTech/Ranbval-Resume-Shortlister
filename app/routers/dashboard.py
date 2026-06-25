"""Admin analytics dashboard — aggregate stats across jobs & candidates."""

from fastapi import APIRouter, Depends

from app.database import CANDIDATES_TABLE, JOBS_TABLE, get_client
from app.deps import require_admin
from app.schemas import DashboardOut, JobStat

router = APIRouter(prefix="/api/admin/dashboard", tags=["dashboard"])

_USERS_TABLE = "resume_users"


def _count(client, table: str, **filters) -> int:
    q = client.table(table).select("id", count="exact")
    for k, v in filters.items():
        q = q.eq(k, v)
    return q.execute().count or 0


@router.get("", response_model=DashboardOut)
def get_dashboard(_admin: dict = Depends(require_admin)) -> DashboardOut:
    client = get_client()

    total_users = _count(client, _USERS_TABLE)
    total_jobs = _count(client, JOBS_TABLE)
    total_candidates = _count(client, CANDIDATES_TABLE)

    shortlisted = _count(client, CANDIDATES_TABLE, recommended=True)
    maybe = _count(client, CANDIDATES_TABLE, verdict="maybe")
    rejected = _count(client, CANDIDATES_TABLE, verdict="reject")
    queued = _count(client, CANDIDATES_TABLE, status="queued")
    processing = _count(client, CANDIDATES_TABLE, status="processing")
    errors = _count(client, CANDIDATES_TABLE, status="error")

    # Per-job breakdown (newest first). Few jobs → a couple count queries each.
    jobs_rows = (
        client.table(JOBS_TABLE)
        .select("id,title")
        .order("id", desc=True)
        .limit(100)
        .execute()
        .data
        or []
    )
    jobs: list[JobStat] = []
    for j in jobs_rows:
        jid = j["id"]
        total = _count(client, CANDIDATES_TABLE, job_id=jid)
        rec = _count(client, CANDIDATES_TABLE, job_id=jid, recommended=True)
        q = _count(client, CANDIDATES_TABLE, job_id=jid, status="queued")
        p = _count(client, CANDIDATES_TABLE, job_id=jid, status="processing")
        jobs.append(
            JobStat(id=jid, title=j["title"], total=total, shortlisted=rec, pending=q + p)
        )

    return DashboardOut(
        total_users=total_users,
        total_jobs=total_jobs,
        total_candidates=total_candidates,
        shortlisted=shortlisted,
        maybe=maybe,
        rejected=rejected,
        pending=queued + processing,
        errors=errors,
        jobs=jobs,
    )
