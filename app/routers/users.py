"""Admin-only user management: view (incl. passwords), add, update, delete."""

from fastapi import APIRouter, Depends, HTTPException

from app.database import get_client
from app.deps import require_admin
from app.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/admin/users", tags=["users"])

_TABLE = "resume_users"
_ROLES = {"admin", "user"}


@router.get("", response_model=list[UserOut])
def list_users(_admin: dict = Depends(require_admin)) -> list[UserOut]:
    rows = (
        get_client().table(_TABLE).select("*").order("id").execute().data or []
    )
    return [_to_user_out(r) for r in rows]


@router.post("", response_model=UserOut)
def create_user(body: UserCreate, _admin: dict = Depends(require_admin)) -> UserOut:
    role = body.role if body.role in _ROLES else "user"
    client = get_client()
    if client.table(_TABLE).select("id").eq("name", body.name.strip()).limit(1).execute().data:
        raise HTTPException(status_code=409, detail="A user with that name already exists")
    res = (
        client.table(_TABLE)
        .insert({"name": body.name.strip(), "password": body.password, "role": role})
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=502, detail="Failed to create user")
    return _to_user_out(res.data[0])


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, body: UserUpdate, _admin: dict = Depends(require_admin)
) -> UserOut:
    patch: dict = {}
    if body.name is not None and body.name.strip():
        patch["name"] = body.name.strip()
    if body.password is not None and body.password != "":
        patch["password"] = body.password
    if body.role is not None and body.role in _ROLES:
        patch["role"] = body.role
    if not patch:
        raise HTTPException(status_code=400, detail="Nothing to update")

    client = get_client()
    res = client.table(_TABLE).update(patch).eq("id", user_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_user_out(res.data[0])


@router.delete("/{user_id}")
def delete_user(user_id: int, _admin: dict = Depends(require_admin)) -> dict[str, str]:
    client = get_client()
    row = client.table(_TABLE).select("role").eq("id", user_id).limit(1).execute().data
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    # Don't allow deleting the last remaining admin.
    if row[0]["role"] == "admin":
        admins = client.table(_TABLE).select("id", count="exact").eq("role", "admin").execute().count or 0
        if admins <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last admin")
    client.table(_TABLE).delete().eq("id", user_id).execute()
    return {"status": "deleted"}


def _to_user_out(row: dict) -> UserOut:
    return UserOut(
        id=row["id"],
        name=row["name"],
        password=row.get("password", ""),
        role=row.get("role", "user"),
        created_at=str(row.get("created_at", "")),
    )
