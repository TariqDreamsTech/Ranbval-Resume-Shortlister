"""Authentication: credential check, signed tokens, and account seeding.

Tokens are stateless HMAC-signed blobs (works on Vercel's serverless runtime
with no session store). Passwords are stored in plaintext by design so the admin
can view them — this is an internal-only tool.
"""

import base64
import hashlib
import hmac
import json
import time

from fastapi import HTTPException

from app.config import get_settings
from app.database import get_client

_USERS_TABLE = "resume_users"
_TOKEN_TTL = 7 * 24 * 3600  # 7 days

# Self-seeded if missing (so it works even before the SQL seed is run).
_SEED_USERS = [
    {"name": "ahsan", "password": "ranbval", "role": "admin", "account_type": "recruiter"},
    {"name": "sabeen", "password": "ranbval", "role": "user", "account_type": "recruiter"},
    {"name": "student", "password": "ranbval", "role": "user", "account_type": "student"},
]


# ── token helpers ──
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload_b64: str) -> str:
    secret = get_settings().auth_secret.encode()
    sig = hmac.new(secret, payload_b64.encode(), hashlib.sha256).digest()
    return _b64(sig)


def create_token(name: str, role: str, account_type: str = "recruiter") -> str:
    payload = {
        "name": name,
        "role": role,
        "account_type": account_type,
        "exp": int(time.time()) + _TOKEN_TTL,
    }
    payload_b64 = _b64(json.dumps(payload, separators=(",", ":")).encode())
    return f"{payload_b64}.{_sign(payload_b64)}"


def decode_token(token: str) -> dict:
    try:
        payload_b64, sig = token.split(".", 1)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token") from None
    if not hmac.compare_digest(sig, _sign(payload_b64)):
        raise HTTPException(status_code=401, detail="Invalid token signature")
    try:
        payload = json.loads(_unb64(payload_b64))
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="Malformed token") from None
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=401, detail="Session expired")
    return payload


# ── seeding + lookup ──
def ensure_seed() -> None:
    """Insert the default accounts if they don't exist yet."""
    client = get_client()
    for u in _SEED_USERS:
        existing = (
            client.table(_USERS_TABLE)
            .select("id")
            .eq("name", u["name"])
            .limit(1)
            .execute()
        )
        if not existing.data:
            try:
                client.table(_USERS_TABLE).insert(u).execute()
            except Exception:
                # account_type column may not exist yet — fall back without it.
                client.table(_USERS_TABLE).insert(
                    {k: v for k, v in u.items() if k != "account_type"}
                ).execute()


def authenticate(name: str, password: str, account_type: str) -> dict:
    """Validate credentials AND that the account matches the requested type.

    Seeds defaults on first call. A recruiter account cannot sign in on the
    student tab and vice-versa.
    """
    ensure_seed()
    client = get_client()
    res = (
        client.table(_USERS_TABLE)
        .select("*")
        .eq("name", name.strip())
        .limit(1)
        .execute()
    )
    if not res.data or res.data[0]["password"] != password:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    row = res.data[0]
    actual = (row.get("account_type") or "recruiter").strip().lower()
    if actual != account_type:
        nice = actual.capitalize()
        raise HTTPException(
            status_code=403,
            detail=f"This is a {actual} account — use the {nice} login tab.",
        )
    return row
