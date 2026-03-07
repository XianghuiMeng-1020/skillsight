from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.db.deps import get_db
from backend.app.security import require_auth

router = APIRouter(tags=["courses"], dependencies=[Depends(require_auth)])

@router.get("/courses")
def list_courses(db: Session = Depends(get_db), limit: int = 50):
    try:
        rows = db.execute(
            text("SELECT * FROM courses ORDER BY created_at DESC LIMIT :limit"),
            {"limit": limit},
        ).mappings().all()
        return {"count": len(rows), "items": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/courses failed: {type(e).__name__}: {e}")

@router.get("/course-skill-map")
def list_course_skill_map(db: Session = Depends(get_db), limit: int = 100):
    try:
        rows = db.execute(
            text("SELECT * FROM course_skill_map ORDER BY created_at DESC LIMIT :limit"),
            {"limit": limit},
        ).mappings().all()
        return {"count": len(rows), "items": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/course-skill-map failed: {type(e).__name__}: {e}")
