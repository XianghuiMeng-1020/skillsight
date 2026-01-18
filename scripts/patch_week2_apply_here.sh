#!/usr/bin/env bash
set -euo pipefail
ROOT="$(pwd)"
BACKEND="$ROOT/backend"
APP="$BACKEND/app"
SEEDS="$BACKEND/data/seeds"

mkdir -p "$APP/db" "$APP/models" "$APP/services" "$APP/routers" "$APP/api" "$SEEDS"

# --- ensure __init__.py ---
touch "$BACKEND/__init__.py" "$APP/__init__.py" "$APP/routers/__init__.py" "$APP/models/__init__.py" "$APP/services/__init__.py" "$APP/db/__init__.py" "$APP/api/__init__.py"

# --- deps ---
REQ="$BACKEND/requirements.txt"
touch "$REQ"
for line in \
"fastapi>=0.110" \
"uvicorn[standard]>=0.27" \
"pydantic>=2.6" \
"sqlalchemy>=2.0" \
"alembic>=1.13" \
"psycopg2-binary>=2.9" \
"python-dotenv>=1.0"
do
  grep -qF "$line" "$REQ" || echo "$line" >> "$REQ"
done
echo "✅ requirements.txt ensured"

# --- db layer ---
cat > "$APP/db/base.py" <<'PY'
from sqlalchemy.orm import DeclarativeBase
class Base(DeclarativeBase):
    pass
PY

cat > "$APP/db/session.py" <<'PY'
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://skillsight:skillsight@localhost:5432/skillsight")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
PY

cat > "$APP/db/deps.py" <<'PY'
from backend.app.db.session import SessionLocal
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
PY

# --- models ---
cat > "$APP/models/skill.py" <<'PY'
from datetime import datetime
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db.base import Base

class Skill(Base):
    __tablename__ = "skills"
    skill_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_rules: Mapped[str] = mapped_column(Text, nullable=False)
    level_rubric_json: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
PY

cat > "$APP/models/skill_alias.py" <<'PY'
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db.base import Base

class SkillAlias(Base):
    __tablename__ = "skill_aliases"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    skill_id: Mapped[str] = mapped_column(String(128), ForeignKey("skills.skill_id", ondelete="CASCADE"), index=True, nullable=False)
    alias: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False, default="manual")
    confidence: Mapped[str] = mapped_column(String(32), nullable=False, default="high")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("skill_id","alias", name="uq_skill_alias"),)
PY

cat > "$APP/models/role.py" <<'PY'
from datetime import datetime
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db.base import Base

class Role(Base):
    __tablename__ = "roles"
    role_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    role_title: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
PY

cat > "$APP/models/role_skill_requirement.py" <<'PY'
from sqlalchemy import String, Boolean, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.db.base import Base

class RoleSkillRequirement(Base):
    __tablename__ = "role_skill_requirements"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    role_id: Mapped[str] = mapped_column(String(128), ForeignKey("roles.role_id", ondelete="CASCADE"), index=True, nullable=False)
    skill_id: Mapped[str] = mapped_column(String(128), ForeignKey("skills.skill_id", ondelete="RESTRICT"), index=True, nullable=False)
    target_level: Mapped[str] = mapped_column(String(32), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    __table_args__ = (UniqueConstraint("role_id","skill_id", name="uq_role_skill"),)
PY

cat > "$APP/models/__init__.py" <<'PY'
from backend.app.models.skill import Skill
from backend.app.models.skill_alias import SkillAlias
from backend.app.models.role import Role
from backend.app.models.role_skill_requirement import RoleSkillRequirement
__all__ = ["Skill","SkillAlias","Role","RoleSkillRequirement"]
PY

# --- pydantic DTO ---
cat > "$APP/api/schemas.py" <<'PY'
from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class SkillIn(BaseModel):
    skill_id: str
    canonical_name: str
    aliases: List[str] = []
    definition: str
    evidence_rules: str
    level_rubric: Dict[str, str]
    version: str
    source: str

class SkillOut(SkillIn):
    pass

class RoleSkillReqIn(BaseModel):
    skill_id: str
    target_level: str
    required: bool
    weight: Optional[float] = None

class RoleIn(BaseModel):
    role_id: str
    role_title: str
    skills_required: List[RoleSkillReqIn]
    description: Optional[str] = None
    version: Optional[str] = None

class RoleOut(RoleIn):
    pass

class ImportResult(BaseModel):
    inserted: int
    updated: int
    skipped: int
    errors: List[str] = Field(default_factory=list)
PY

# --- services ---
cat > "$APP/services/skills.py" <<'PY'
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
        db.add(SkillAlias(skill_id=skill_id, alias=a, source=payload.get("source","manual"), confidence="high"))
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
PY

cat > "$APP/services/roles.py" <<'PY'
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
PY

# --- routers ---
cat > "$APP/routers/skills.py" <<'PY'
import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.app.db.deps import get_db
from backend.app.api.schemas import SkillIn, SkillOut, ImportResult
from backend.app.services.skills import upsert_skill, search_skills
from backend.app.models import Skill

router = APIRouter(prefix="/skills", tags=["skills"])

@router.get("", response_model=list[SkillOut])
def list_or_search(q: str | None = Query(default=None), db: Session = Depends(get_db)):
    skills = search_skills(db, q) if q else db.query(Skill).limit(50).all()
    out = []
    for s in skills:
        out.append(SkillOut(
            skill_id=s.skill_id,
            canonical_name=s.canonical_name,
            aliases=[],
            definition=s.definition,
            evidence_rules=s.evidence_rules,
            level_rubric=json.loads(s.level_rubric_json),
            version=s.version,
            source=s.source,
        ))
    return out

@router.post("/import", response_model=ImportResult)
def import_skills(items: list[SkillIn], db: Session = Depends(get_db)):
    inserted = updated = skipped = 0
    errors: list[str] = []
    for it in items:
        try:
            created = upsert_skill(db, it.model_dump())
            inserted += 1 if created else 0
            updated += 0 if created else 1
        except Exception as e:
            skipped += 1
            errors.append(f"{it.skill_id}: {e}")
    db.commit()
    return ImportResult(inserted=inserted, updated=updated, skipped=skipped, errors=errors)
PY

cat > "$APP/routers/roles.py" <<'PY'
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.app.db.deps import get_db
from backend.app.api.schemas import RoleIn, RoleOut, ImportResult
from backend.app.services.roles import upsert_role
from backend.app.models import Role, RoleSkillRequirement

router = APIRouter(prefix="/roles", tags=["roles"])

@router.get("/{role_id}", response_model=RoleOut)
def get_role(role_id: str, db: Session = Depends(get_db)):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="role not found")
    reqs = db.query(RoleSkillRequirement).filter(RoleSkillRequirement.role_id == role_id).all()
    return RoleOut(
        role_id=role.role_id,
        role_title=role.role_title,
        description=role.description,
        version=role.version,
        skills_required=[{"skill_id": r.skill_id, "target_level": r.target_level, "required": r.required, "weight": r.weight} for r in reqs],
    )

@router.post("/import", response_model=ImportResult)
def import_roles(items: list[RoleIn], db: Session = Depends(get_db)):
    inserted = updated = skipped = 0
    errors: list[str] = []
    for it in items:
        try:
            created = upsert_role(db, it.model_dump())
            inserted += 1 if created else 0
            updated += 0 if created else 1
        except Exception as e:
            skipped += 1
            errors.append(f"{it.role_id}: {e}")
    db.commit()
    return ImportResult(inserted=inserted, updated=updated, skipped=skipped, errors=errors)
PY

# --- seed files ---
cat > "$SEEDS/skills.json" <<'JSON'
[
  {
    "skill_id": "HKU.SSKILL.000001.v1",
    "canonical_name": "Python Programming",
    "aliases": ["Python", "Python coding"],
    "definition": "Ability to write, debug, and maintain Python programs for data processing and automation.",
    "evidence_rules": "Counts as evidence when the artifact includes runnable Python code and demonstrates correct logic for the stated task.",
    "level_rubric": {"0":"No usable code artifact.","1":"Small scripts with guidance.","2":"Multi-step tasks independently.","3":"Robust modules, tests, clear APIs."},
    "version": "v1",
    "source": "HKU"
  }
]
JSON

cat > "$SEEDS/roles.json" <<'JSON'
[
  {
    "role_id": "HKU.ROLE.000001.v1",
    "role_title": "Junior Data Analyst",
    "description": "Entry-level analyst role focusing on data cleaning, basic analysis, and reporting.",
    "version": "v1",
    "skills_required": [
      {"skill_id": "HKU.SSKILL.000001.v1", "target_level": "2", "required": true, "weight": 1.0}
    ]
  }
]
JSON

# --- patch main.py to include routers (non-destructive append) ---
MAIN="$APP/main.py"
if [[ ! -f "$MAIN" ]]; then
  echo "❌ backend/app/main.py not found. Create it first (you already have it)."
  exit 1
fi

# add imports if missing
grep -q "backend.app.routers.skills" "$MAIN" || printf "\nfrom backend.app.routers.skills import router as skills_router\nfrom backend.app.routers.roles import router as roles_router\n" >> "$MAIN"
# include routers if missing
grep -q "include_router(skills_router" "$MAIN" || printf "\n# Week2 MVP routers\napp.include_router(skills_router)\napp.include_router(roles_router)\n" >> "$MAIN"

echo "✅ Week2 code written."
echo "Next: check routers dir exists:"
echo "  ls -la backend/app/routers"
