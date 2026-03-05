import json
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.app.models import Skill, SkillAlias

def upsert_skill(db: Session, payload: dict) -> bool:
    skill_id = payload["skill_id"]
    existing = db.get(Skill, skill_id)
    rubric_json = json.dumps(payload.get("level_rubric", {}), ensure_ascii=False)

    created = existing is None
    if created:
        existing = Skill(
            skill_id=skill_id,
            canonical_name=payload["canonical_name"],
            definition=payload["definition"],
            evidence_rules=payload["evidence_rules"],
            level_rubric_json=rubric_json,
            version=payload["version"],
            source=payload["source"],
        )
        db.add(existing)
    else:
        existing.canonical_name = payload["canonical_name"]
        existing.definition = payload["definition"]
        existing.evidence_rules = payload["evidence_rules"]
        existing.level_rubric_json = rubric_json
        existing.version = payload["version"]
        existing.source = payload["source"]

    db.query(SkillAlias).filter(SkillAlias.skill_id == skill_id).delete()
    for a in (payload.get("aliases") or []):
        db.add(SkillAlias(skill_id=skill_id, alias=a, source=payload.get("source","manual"), confidence=0.9))
    return created

def search_skills(db: Session, q: str, limit: int = 50):
    q = (q or "").strip()
    if not q:
        return []
    skills = list(db.scalars(select(Skill).where(Skill.canonical_name.ilike(f"%{q}%")).limit(limit)).all())
    alias_hits = list(db.scalars(select(SkillAlias).where(SkillAlias.alias.ilike(f"%{q}%")).limit(limit)).all())
    for ah in alias_hits:
        s = db.get(Skill, ah.skill_id)
        if s and all(x.skill_id != s.skill_id for x in skills):
            skills.append(s)
    return skills
