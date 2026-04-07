from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.db.deps import get_db
from backend.app.security import Identity, require_auth


router = APIRouter(prefix="/job-postings", tags=["job-postings"], dependencies=[Depends(require_auth)])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class JobPostingIn(BaseModel):
    source_site: str = Field(..., max_length=80)
    source_id: str = Field(..., max_length=255)
    title: str = Field(..., max_length=300)
    company: Optional[str] = Field(default="", max_length=255)
    location: Optional[str] = Field(default="", max_length=255)
    salary: Optional[str] = Field(default="", max_length=120)
    employment_type: Optional[str] = Field(default="", max_length=80)
    posted_at: Optional[str] = Field(default="", max_length=80)
    source_url: str = Field(..., max_length=2000)
    description: Optional[str] = Field(default="", max_length=12000)
    status: str = Field(default="active", max_length=30)
    raw_payload: Dict[str, Any] = Field(default_factory=dict)


@router.post("/import")
def import_job_postings(
    payload: List[JobPostingIn],
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    if ident.role not in ("admin", "staff", "programme"):
        raise HTTPException(status_code=403, detail="Only admin/staff can import job postings")
    inserted = 0
    updated = 0
    for item in payload:
        row = db.execute(
            text(
                """
                SELECT posting_id FROM job_postings
                WHERE source_site = :source_site AND source_id = :source_id
                LIMIT 1
                """
            ),
            {"source_site": item.source_site, "source_id": item.source_id},
        ).mappings().first()
        if row:
            db.execute(
                text(
                    """
                    UPDATE job_postings
                    SET title = :title, company = :company, location = :location, salary = :salary,
                        employment_type = :employment_type, posted_at = :posted_at, source_url = :source_url,
                        description = :description, status = :status, snapshot_at = :snapshot_at, raw_payload = (:raw_payload)::jsonb
                    WHERE posting_id = :posting_id
                    """
                ),
                {**item.model_dump(), "snapshot_at": _now_utc(), "raw_payload": json.dumps(item.raw_payload), "posting_id": row["posting_id"]},
            )
            updated += 1
        else:
            db.execute(
                text(
                    """
                    INSERT INTO job_postings (
                        posting_id, source_site, source_id, title, company, location, salary,
                        employment_type, posted_at, source_url, description, status, snapshot_at, raw_payload
                    ) VALUES (
                        :posting_id, :source_site, :source_id, :title, :company, :location, :salary,
                        :employment_type, :posted_at, :source_url, :description, :status, :snapshot_at, (:raw_payload)::jsonb
                    )
                    """
                ),
                {**item.model_dump(), "posting_id": str(uuid.uuid4()), "snapshot_at": _now_utc(), "raw_payload": json.dumps(item.raw_payload)},
            )
            inserted += 1
    db.commit()
    return {"inserted": inserted, "updated": updated, "count": len(payload)}


@router.get("")
def list_job_postings(
    source_site: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    where: List[str] = []
    params: Dict[str, Any] = {"limit": min(max(limit, 1), 200)}
    if source_site:
        where.append("source_site = :source_site")
        params["source_site"] = source_site
    if q:
        where.append("(title ILIKE :q OR company ILIKE :q OR description ILIKE :q)")
        params["q"] = f"%{q}%"
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.execute(
        text(
            f"""
            SELECT posting_id, source_site, source_id, title, company, location, salary,
                   employment_type, posted_at, source_url, status, snapshot_at
            FROM job_postings
            {where_sql}
            ORDER BY snapshot_at DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()
    items = [dict(r) for r in rows]
    for item in items:
        if item.get("snapshot_at") and hasattr(item["snapshot_at"], "isoformat"):
            item["snapshot_at"] = item["snapshot_at"].isoformat()
    return {"count": len(items), "items": items}
