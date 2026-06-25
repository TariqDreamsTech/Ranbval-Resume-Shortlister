"""Login endpoint."""

from fastapi import APIRouter

from app.schemas import LoginIn, LoginOut
from app.services.auth import authenticate, create_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn) -> LoginOut:
    user = authenticate(body.name, body.password)
    token = create_token(user["name"], user["role"])
    return LoginOut(token=token, name=user["name"], role=user["role"])
