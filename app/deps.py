"""Auth dependencies for protected routes."""

from fastapi import Header, HTTPException

from app.services.auth import decode_token


def require_user(authorization: str = Header(default="")) -> dict:
    """Any logged-in user (admin or user). Returns the token payload."""
    token = ""
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Login required")
    return decode_token(token)


def require_admin(authorization: str = Header(default="")) -> dict:
    payload = require_user(authorization)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload
