from __future__ import annotations

import base64
import hmac
import json
import os
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Callable, Dict, Optional, Set

from fastapi import Depends, Header, HTTPException


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * ((4 - (len(s) % 4)) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))


DEV_SECRET = "dev_secret_change_me"


def _secret() -> bytes:
    # Dev default; MUST be overridden in real deployments
    return (os.getenv("SKILLSIGHT_AUTH_SECRET") or DEV_SECRET).encode("utf-8")


def _is_production() -> bool:
    return os.getenv("SKILLSIGHT_ENV", "").strip().lower() in ("production", "prod")


def _is_dev_login_allowed() -> bool:
    """Allow dev_login only when DEV_LOGIN_ENABLED=true or not in production.
    In production, set DEV_LOGIN_ENABLED=true explicitly to re-enable for demos."""
    if _is_production():
        return os.getenv("DEV_LOGIN_ENABLED", "false").strip().lower() == "true"
    return True


def require_production_secret() -> None:
    """Raise if production env and secret is missing or equals dev default."""
    if not _is_production():
        return
    secret = os.getenv("SKILLSIGHT_AUTH_SECRET", "").strip()
    if not secret or secret == DEV_SECRET:
        raise RuntimeError(
            "SKILLSIGHT_AUTH_SECRET must be set and must not equal dev default when SKILLSIGHT_ENV=production"
        )


def issue_token(
    subject_id: str,
    role: str,
    ttl_s: int = 3600,
    *,
    faculty_id: Optional[str] = None,
    programme_id: Optional[str] = None,
    course_ids: Optional[list] = None,
    term_id: Optional[str] = None,
) -> str:
    now = int(time.time())
    payload: Dict[str, Any] = {
        "sub": subject_id,
        "role": role,
        "iat": now,
        "exp": now + int(ttl_s),
    }
    # ABAC context fields (optional)
    if faculty_id:
        payload["faculty_id"] = faculty_id
    if programme_id:
        payload["programme_id"] = programme_id
    if course_ids:
        payload["course_ids"] = course_ids
    if term_id:
        payload["term_id"] = term_id

    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    sig = hmac.new(_secret(), payload_b64.encode("utf-8"), sha256).digest()
    sig_b64 = _b64url_encode(sig)
    return f"{payload_b64}.{sig_b64}"


def verify_token(token: str) -> Dict[str, Any]:
    try:
        parts = (token or "").split(".")
        if len(parts) != 2:
            raise ValueError("bad token format")
        payload_b64, sig_b64 = parts
        expected_sig = hmac.new(_secret(), payload_b64.encode("utf-8"), sha256).digest()
        got_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, got_sig):
            raise ValueError("bad signature")
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        exp = int(payload.get("exp") or 0)
        if exp and int(time.time()) > exp:
            raise ValueError("expired")
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"invalid token: {type(e).__name__}")


def parse_token_optional(authorization: Optional[str]) -> Optional[Dict[str, Any]]:
    """Decode Bearer token without raising. Returns payload or None (for audit middleware)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    try:
        parts = (token or "").split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig_b64 = parts
        expected_sig = hmac.new(_secret(), payload_b64.encode("utf-8"), sha256).digest()
        got_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, got_sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        exp = int(payload.get("exp") or 0)
        if exp and int(time.time()) > exp:
            return None
        return payload
    except Exception:
        return None


@dataclass(frozen=True)
class Identity:
    subject_id: str
    role: str
    source: str  # bearer|headers
    # ABAC context fields from token claims
    faculty_id: Optional[str] = None
    programme_id: Optional[str] = None
    course_ids: Optional[tuple] = None
    term_id: Optional[str] = None


def get_identity(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_subject_id: str = Header(default="unknown", alias="X-Subject-Id"),
    x_role: str = Header(default="unknown", alias="X-Role"),
) -> Identity:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = verify_token(token)
        sub = str(payload.get("sub") or "unknown")
        role = str(payload.get("role") or "unknown")
        course_ids_raw = payload.get("course_ids")
        return Identity(
            subject_id=sub,
            role=role,
            source="bearer",
            faculty_id=payload.get("faculty_id"),
            programme_id=payload.get("programme_id"),
            course_ids=tuple(course_ids_raw) if course_ids_raw else None,
            term_id=payload.get("term_id"),
        )
    return Identity(subject_id=x_subject_id, role=x_role, source="headers")


def require_auth(ident: Identity = Depends(get_identity)) -> Identity:
    """Require valid Bearer token. Reject header-only identity."""
    if ident.source != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required")
    return ident


def require_roles(*roles: str) -> Callable[[Identity], Identity]:
    allow: Set[str] = {r for r in roles}

    def _dep(ident: Identity = Depends(get_identity)) -> Identity:
        if ident.role not in allow:
            raise HTTPException(status_code=403, detail="forbidden")
        return ident

    return _dep

