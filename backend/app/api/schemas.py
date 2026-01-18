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
