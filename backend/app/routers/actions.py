"""
Action Routes for SkillSight
- POST /actions/recommend: Generate action cards based on skill gaps (Decision 5)
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from backend.app.db.deps import get_db
    from backend.app.deps import check_doc_access
    from backend.app.security import Identity, require_auth
except ImportError:
    from app.db.deps import get_db
    from app.deps import check_doc_access
    from app.security import Identity, require_auth

router = APIRouter(prefix="/actions", tags=["actions"])
_log = logging.getLogger(__name__)

# Load action templates
TEMPLATES_PATH = Path(__file__).parent.parent.parent / "data" / "action_templates.json"

_templates_cache: List[Dict[str, Any]] = []


def _load_templates() -> List[Dict[str, Any]]:
    """Load action templates from JSON file."""
    global _templates_cache
    if _templates_cache:
        return _templates_cache
    
    if TEMPLATES_PATH.exists():
        try:
            _templates_cache = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            _log.warning("action template loading failed: %s", exc)
            _templates_cache = []
    return _templates_cache


def _now_utc():
    return datetime.now(timezone.utc)


def _get_matched_resource(
    db: Session,
    skill_id: str,
    gap_type: str,
) -> Optional[Dict[str, Any]]:
    """P5: Get learning resource matched to skill+gap_type from resource_skill_map."""
    try:
        sql = text("""
            SELECT lr.resource_id, lr.title, lr.location, lr.resource_type, lr.url
            FROM learning_resources lr
            JOIN resource_skill_map rsm ON rsm.resource_id = lr.resource_id
            WHERE rsm.skill_id = :skill_id
              AND (rsm.gap_type IS NULL OR rsm.gap_type = :gap_type)
            ORDER BY rsm.gap_type NULLS LAST
            LIMIT 1
        """)
        row = db.execute(sql, {"skill_id": skill_id, "gap_type": gap_type or ""}).mappings().first()
        return dict(row) if row else None
    except Exception as exc:
        _log.warning("resource lookup failed for skill %s: %s", skill_id, exc)
        return None


def _get_skill(db: Session, skill_id: str) -> Optional[Dict[str, Any]]:
    """Get skill by ID."""
    sql = text("""
        SELECT skill_id, canonical_name, definition
        FROM skills
        WHERE skill_id = :skill_id
        LIMIT 1
    """)
    row = db.execute(sql, {"skill_id": skill_id}).mappings().first()
    return dict(row) if row else None


def _get_default_action(skill_id: str, skill_name: str, gap_type: str) -> Dict[str, Any]:
    """P5: Action card with 4 required fields."""
    if gap_type == "missing_proof":
        return {
            "skill_id": skill_id,
            "gap_type": gap_type,
            "title": f"Add evidence for {skill_name}",
            "what_to_do": f"Create an artifact that demonstrates your {skill_name} capability. This could be a written reflection, project documentation, or code sample.",
            "where_to_do_it": "HKU course / workshop / approved external resource",
            "what_to_submit_next": "Written evidence (text, document, or code)",
            "when_to_recheck": "After uploading new evidence or next portfolio review",
            "artifact": "Written evidence (text, document, or code)",
            "how_verified": f"Evidence explicitly describes or demonstrates {skill_name} in a concrete, verifiable way.",
        }
    else:  # needs_strengthening
        return {
            "skill_id": skill_id,
            "gap_type": gap_type,
            "title": f"Strengthen {skill_name}",
            "what_to_do": f"Expand your existing evidence for {skill_name} with more detailed examples, multiple instances, or deeper analysis.",
            "where_to_do_it": "HKU course / workshop / approved external resource",
            "what_to_submit_next": "Extended evidence with additional examples",
            "when_to_recheck": "After uploading strengthened evidence or next portfolio review",
            "artifact": "Extended evidence with additional examples",
            "how_verified": f"Evidence shows multiple concrete applications of {skill_name} or deeper understanding.",
        }


class ActionRecommendRequest(BaseModel):
    """Request for action recommendations."""
    doc_id: str = Field(..., description="Document ID")
    role_id: Optional[str] = Field(default=None, description="Role ID for role-specific recommendations")
    skill_ids: Optional[List[str]] = Field(default=None, description="Specific skill IDs to get actions for")
    gap_types: Optional[List[str]] = Field(default=None, description="Filter by gap types: missing_proof, needs_strengthening")


class ActionCard(BaseModel):
    """Single action card."""
    skill_id: str
    skill_name: str
    gap_type: str
    title: str
    what_to_do: str
    artifact: str
    how_verified: str
    based_on: str  # Explanation of why this action is recommended


class ActionRecommendResponse(BaseModel):
    """Response with action recommendations."""
    doc_id: str
    role_id: Optional[str]
    actions: List[ActionCard]
    timing_ms: int


@router.post("/recommend", response_model=ActionRecommendResponse)
def recommend_actions(
    req: ActionRecommendRequest,
    db: Session = Depends(get_db),
    ident: Identity = Depends(require_auth),
) -> Dict[str, Any]:
    """
    Decision 5: Generate action cards based on skill gaps.
    
    For each skill with gap_type = 'missing_proof' or 'needs_strengthening',
    returns a concrete action card with:
    - what_to_do: Specific task
    - artifact: What to produce as evidence
    - how_verified: How completion is verified
    
    Uses templates from action_templates.json when available,
    falls back to generated defaults otherwise.
    """
    started = _now_utc()
    check_doc_access(ident, req.doc_id, db)
    templates = _load_templates()
    # Get skill gaps based on context
    gaps = []
    
    if req.role_id:
        # Get gaps from role readiness
        gaps = _get_role_readiness_gaps(db, req.doc_id, req.role_id, req.gap_types)
    elif req.skill_ids:
        # Get gaps for specific skills
        gaps = _get_skill_assessment_gaps(db, req.doc_id, req.skill_ids, req.gap_types)
    else:
        # Get all gaps for document
        gaps = _get_all_document_gaps(db, req.doc_id, req.gap_types)
    
    # Generate action cards
    actions = []
    for gap in gaps:
        skill_id = gap["skill_id"]
        gap_type = gap["gap_type"]
        skill_name = gap.get("skill_name", skill_id)
        
        # Find matching template
        template = None
        for t in templates:
            if t.get("skill_id") == skill_id and t.get("gap_type") == gap_type:
                template = t
                break
        
        # Use template or generate default; P5: ensure 4 required fields
        if template:
            action = {
                "skill_id": skill_id,
                "skill_name": skill_name,
                "gap_type": gap_type,
                "title": template.get("title", f"Action for {skill_name}"),
                "what_to_do": template.get("what_to_do", ""),
                "where_to_do_it": template.get("where_to_do_it", "HKU course / workshop / approved external"),
                "what_to_submit_next": template.get("what_to_submit_next", template.get("artifact", "")),
                "when_to_recheck": template.get("when_to_recheck", "After uploading new evidence or next portfolio review"),
                "artifact": template.get("artifact", ""),
                "how_verified": template.get("how_verified", ""),
                "based_on": f"Gap detected: {gap_type}. " + gap.get("explanation", ""),
            }
        else:
            default = _get_default_action(skill_id, skill_name, gap_type)
            action = {
                "skill_id": skill_id,
                "skill_name": skill_name,
                "gap_type": gap_type,
                "title": default["title"],
                "what_to_do": default["what_to_do"],
                "where_to_do_it": default["where_to_do_it"],
                "what_to_submit_next": default["what_to_submit_next"],
                "when_to_recheck": default["when_to_recheck"],
                "artifact": default["artifact"],
                "how_verified": default["how_verified"],
                "based_on": f"Gap detected: {gap_type}. " + gap.get("explanation", "No template available; using default action."),
            }
        # P5: Attach matched resource if available
        resource = _get_matched_resource(db, skill_id, gap_type)
        if resource:
            action["resource_id"] = str(resource.get("resource_id", ""))
            action["resource_title"] = resource.get("title", "")
            if resource.get("location"):
                action["where_to_do_it"] = resource["location"]
        actions.append(action)
    
    timing_ms = int((_now_utc() - started).total_seconds() * 1000)
    
    return {
        "doc_id": req.doc_id,
        "role_id": req.role_id,
        "actions": actions,
        "timing_ms": timing_ms,
    }


def _get_role_readiness_gaps(
    db: Session,
    doc_id: str,
    role_id: str,
    gap_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Get skill gaps from role readiness assessment."""
    # First get role requirements
    req_sql = text("""
        SELECT rsr.skill_id, rsr.target_level, rsr.required, s.canonical_name as skill_name
        FROM role_skill_requirements rsr
        JOIN skills s ON s.skill_id = rsr.skill_id
        WHERE rsr.role_id = :role_id
    """)
    requirements = db.execute(req_sql, {"role_id": role_id}).mappings().all()
    
    if not requirements:
        return []
    
    # Get current proficiency for each skill
    gaps = []
    for req in requirements:
        skill_id = req["skill_id"]
        target_level = int(req["target_level"])
        skill_name = req["skill_name"]
        
        # Get latest proficiency
        prof_sql = text("""
            SELECT level, label
            FROM skill_proficiency
            WHERE doc_id = :doc_id AND skill_id = :skill_id
            ORDER BY created_at DESC
            LIMIT 1
        """)
        prof = db.execute(prof_sql, {"doc_id": doc_id, "skill_id": skill_id}).mappings().first()
        
        # Get latest assessment
        assess_sql = text("""
            SELECT decision
            FROM skill_assessments
            WHERE doc_id = :doc_id AND skill_id = :skill_id
            ORDER BY created_at DESC
            LIMIT 1
        """)
        assess = db.execute(assess_sql, {"doc_id": doc_id, "skill_id": skill_id}).mappings().first()
        
        achieved_level = int(prof["level"]) if prof else 0
        decision = assess["decision"] if assess else ""
        
        # Determine gap type
        gap_type = None
        explanation = ""
        
        if not decision or decision in ("no_match", "not_enough_information"):
            gap_type = "missing_proof"
            explanation = f"No evidence found for {skill_name}."
        elif decision == "mentioned":
            gap_type = "missing_proof"
            explanation = f"{skill_name} was mentioned but not demonstrated with concrete evidence."
        elif achieved_level < target_level:
            gap_type = "needs_strengthening"
            explanation = f"Current level {achieved_level} is below target level {target_level}."
        
        if gap_type:
            if gap_types is None or gap_type in gap_types:
                gaps.append({
                    "skill_id": skill_id,
                    "skill_name": skill_name,
                    "gap_type": gap_type,
                    "achieved_level": achieved_level,
                    "target_level": target_level,
                    "explanation": explanation,
                })
    
    return gaps


def _get_skill_assessment_gaps(
    db: Session,
    doc_id: str,
    skill_ids: List[str],
    gap_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Get skill gaps for specific skills."""
    gaps = []
    
    for skill_id in skill_ids:
        # Get skill info
        skill = _get_skill(db, skill_id)
        skill_name = skill["canonical_name"] if skill else skill_id
        
        # Get latest proficiency
        prof_sql = text("""
            SELECT level, label
            FROM skill_proficiency
            WHERE doc_id = :doc_id AND skill_id = :skill_id
            ORDER BY created_at DESC
            LIMIT 1
        """)
        prof = db.execute(prof_sql, {"doc_id": doc_id, "skill_id": skill_id}).mappings().first()
        
        # Get latest assessment
        assess_sql = text("""
            SELECT decision
            FROM skill_assessments
            WHERE doc_id = :doc_id AND skill_id = :skill_id
            ORDER BY created_at DESC
            LIMIT 1
        """)
        assess = db.execute(assess_sql, {"doc_id": doc_id, "skill_id": skill_id}).mappings().first()
        
        achieved_level = int(prof["level"]) if prof else 0
        decision = assess["decision"] if assess else ""
        
        # Determine gap type
        gap_type = None
        explanation = ""
        
        if not decision or decision in ("no_match", "not_enough_information"):
            gap_type = "missing_proof"
            explanation = f"No evidence found for {skill_name}."
        elif decision == "mentioned":
            gap_type = "missing_proof"
            explanation = f"{skill_name} was mentioned but not demonstrated."
        elif achieved_level < 2:  # Default target level
            gap_type = "needs_strengthening"
            explanation = f"Current level {achieved_level} could be improved."
        
        if gap_type:
            if gap_types is None or gap_type in gap_types:
                gaps.append({
                    "skill_id": skill_id,
                    "skill_name": skill_name,
                    "gap_type": gap_type,
                    "achieved_level": achieved_level,
                    "explanation": explanation,
                })
    
    return gaps


def _get_all_document_gaps(
    db: Session,
    doc_id: str,
    gap_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Get all skill gaps for a document."""
    # Get all assessments for document
    sql = text("""
        SELECT sa.skill_id, sa.decision, s.canonical_name as skill_name,
               sp.level as prof_level
        FROM skill_assessments sa
        JOIN skills s ON s.skill_id = sa.skill_id
        LEFT JOIN (
            SELECT DISTINCT ON (skill_id) skill_id, level
            FROM skill_proficiency
            WHERE doc_id = :doc_id
            ORDER BY skill_id, created_at DESC
        ) sp ON sp.skill_id = sa.skill_id
        WHERE sa.doc_id = :doc_id
    """)
    
    rows = db.execute(sql, {"doc_id": doc_id}).mappings().all()
    
    gaps = []
    for r in rows:
        skill_id = r["skill_id"]
        skill_name = r["skill_name"]
        decision = r["decision"]
        achieved_level = int(r["prof_level"]) if r.get("prof_level") is not None else 0
        
        gap_type = None
        explanation = ""
        
        if decision in ("no_match", "not_enough_information"):
            gap_type = "missing_proof"
            explanation = f"No evidence found for {skill_name}."
        elif decision == "mentioned":
            gap_type = "missing_proof"
            explanation = f"{skill_name} was mentioned but not demonstrated."
        elif achieved_level < 2:
            gap_type = "needs_strengthening"
            explanation = f"Current level {achieved_level} could be improved."
        
        if gap_type:
            if gap_types is None or gap_type in gap_types:
                gaps.append({
                    "skill_id": skill_id,
                    "skill_name": skill_name,
                    "gap_type": gap_type,
                    "achieved_level": achieved_level,
                    "explanation": explanation,
                })
    
    return gaps


@router.get("/templates")
def list_action_templates() -> Dict[str, Any]:
    """List all available action templates."""
    templates = _load_templates()
    return {
        "count": len(templates),
        "items": templates,
    }
