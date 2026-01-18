from sqlalchemy.orm import Session
from backend.app.models import Role, RoleSkillRequirement

def upsert_role(db: Session, payload: dict) -> bool:
    role_id = payload["role_id"]
    existing = db.get(Role, role_id)
    created = existing is None

    if created:
        existing = Role(role_id=role_id, role_title=payload["role_title"], description=payload.get("description"), version=payload.get("version"))
        db.add(existing)
    else:
        existing.role_title = payload["role_title"]
        existing.description = payload.get("description")
        existing.version = payload.get("version")

    db.query(RoleSkillRequirement).filter(RoleSkillRequirement.role_id == role_id).delete()
    for req in payload.get("skills_required", []):
        db.add(RoleSkillRequirement(
            role_id=role_id,
            skill_id=req["skill_id"],
            target_level=req["target_level"],
            required=req["required"],
            weight=req.get("weight"),
        ))
    return created
