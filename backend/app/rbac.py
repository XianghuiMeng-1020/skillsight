
from typing import Dict
from fastapi import HTTPException, Request
from sqlalchemy import text
from sqlalchemy.engine import Engine

VALID_ROLES = {"student", "staff", "admin"}

def get_current_user(request: Request) -> Dict[str, str]:
    subject_id = (request.headers.get("X-Subject-Id") or "").strip()
    role = (request.headers.get("X-Role") or "").strip().lower()

    # Dev fallback: if header missing, treat as student_demo
    if not subject_id:
        subject_id = "student_demo"
    if not role:
        role = "student"

    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role. Use student/staff/admin")

    return {"subject_id": subject_id, "role": role}

def require_doc_access(engine: Engine, user: Dict[str, str], doc_id: str):
    # staff/admin can access all (v0)
    if user["role"] in {"staff", "admin"}:
        return

    # student must own doc
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT subject_id FROM documents WHERE doc_id = (:doc_id)::uuid"),
            {"doc_id": doc_id},
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    if row["subject_id"] != user["subject_id"]:
        raise HTTPException(status_code=403, detail="Forbidden: not your document")
