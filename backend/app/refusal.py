"""
Canonical refusal contract for SkillSight.

Strict shape: { code, message, next_step }. No label/reason in default responses.
Wrapper for 403 and in-body refusal: { ok: False, refusal: Refusal, request_id?: str }.

Compat mode: header X-Compat-Refusal: 1 or env REFUSAL_COMPAT=1 adds legacy fields
(label=code, reason=message) to the refusal object; strict fields always present.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class Refusal(BaseModel):
    """Canonical refusal payload. Only code, message, next_step."""
    code: str = Field(..., description="Machine-readable refusal code")
    message: str = Field(..., description="Human-readable message")
    next_step: str = Field(..., description="Suggested next action")


def _compat_requested(headers: Optional[Any] = None) -> bool:
    if os.getenv("REFUSAL_COMPAT", "").strip().lower() in ("1", "true", "yes"):
        return True
    if headers is not None:
        h = getattr(headers, "get", None) or getattr(headers, "getheader", None)
        if h and h("X-Compat-Refusal", "").strip() in ("1", "true"):
            return True
    return False


def make_refusal(
    code: str,
    message: str,
    next_step: str = "Contact your administrator if you believe this is an error.",
    status_code: int = 403,
    request_id: Optional[str] = None,
    headers: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Build the canonical refusal shape for HTTP 403 (or other status).

    Returns a dict suitable for HTTPException(detail=...) so that the response
    body is: { "detail": { "ok": false, "refusal": { "code", "message", "next_step" }, "request_id"?: str } }.

    In compat mode, refusal dict also includes "label" (=code) and "reason" (=message).
    """
    refusal_dict: Dict[str, Any] = {
        "code": code,
        "message": message,
        "next_step": next_step,
    }
    if _compat_requested(headers):
        refusal_dict["label"] = code
        refusal_dict["reason"] = message
    body: Dict[str, Any] = {"ok": False, "refusal": refusal_dict}
    if request_id:
        body["request_id"] = request_id
    return body


def refusal_dict(
    code: str,
    message: str,
    next_step: str = "Contact your administrator if you believe this is an error.",
    headers: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Build only the refusal object (for in-body use, e.g. items=[], refusal=...).
    Strict: { code, message, next_step }. Compat adds label, reason.
    """
    out: Dict[str, Any] = {"code": code, "message": message, "next_step": next_step}
    if _compat_requested(headers):
        out["label"] = code
        out["reason"] = message
    return out


def normalize_legacy_refusal(refusal: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Convert legacy { label, reason } or mixed shape to strict { code, message, next_step }.
    Returns None if refusal is None or not a dict. Does not add legacy fields.
    """
    if not refusal or not isinstance(refusal, dict):
        return None
    code = refusal.get("code") or refusal.get("label") or "refusal"
    message = refusal.get("message") or refusal.get("reason") or "Request refused."
    next_step = refusal.get("next_step") or "Contact support or try again later."
    return {"code": code, "message": message, "next_step": next_step}
