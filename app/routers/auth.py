"""Login endpoint."""

from fastapi import APIRouter

from app.schemas import LoginIn, LoginOut
from app.services.auth import authenticate, create_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn) -> LoginOut:
    acct = body.account_type if body.account_type in ("recruiter", "student") else "recruiter"
    user = authenticate(body.name, body.password, acct)
    actual = (user.get("account_type") or "recruiter")
    token = create_token(user["name"], user["role"], actual)
    return LoginOut(token=token, name=user["name"], role=user["role"], account_type=actual)
