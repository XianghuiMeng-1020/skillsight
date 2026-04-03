from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from fastapi import HTTPException

from backend.app.security import Identity, get_identity, require_auth, issue_token, _is_dev_login_allowed


router = APIRouter(prefix="/auth", tags=["auth"])


class DevLoginReq(BaseModel):
    subject_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    ttl_s: int = Field(default=3600, ge=60, le=60 * 24 * 30)


@router.post("/dev_login")
def dev_login(payload: DevLoginReq) -> Dict[str, Any]:
    """Issue a JWT token. Disabled in production unless SKILLSIGHT_ALLOW_DEV_LOGIN."""
    if not _is_dev_login_allowed():
        raise HTTPException(status_code=403, detail="dev_login disabled in production")
    token = issue_token(payload.subject_id, payload.role, ttl_s=int(payload.ttl_s))
    return {"token": token, "subject_id": payload.subject_id, "role": payload.role}


@router.get("/whoami")
def whoami(ident: Identity = Depends(require_auth)) -> Dict[str, Any]:
    return {"subject_id": ident.subject_id, "role": ident.role, "source": ident.source}


@router.get("/me")
def me(ident: Identity = Depends(require_auth)) -> Dict[str, Any]:
    """Alias for /auth/whoami for API consistency."""
    return {"subject_id": ident.subject_id, "role": ident.role, "source": ident.source}
