"""
SkillSight Pydantic Models (Week 1 Day 3)
Generated: 2026-01-16

MVP objects:
- Skill
- Role
- EvidencePointer
- AuditLog
- ConsentRecord
"""
from __future__ import annotations
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class Skill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill_id: str = Field(..., description="Stable public ID, versioned, e.g., HKU.SSKILL.000123.v1")
    canonical_name: str
    aliases: List[str] = Field(default_factory=list)
    definition: str = Field(..., description="1–3 sentences, clear and searchable")
    evidence_rules: str = Field(..., description="What counts as evidence")
    level_rubric: Dict[str, str] = Field(..., description="Observable criteria per level")
    version: str = Field(..., description="v1/v2")
    source: str = Field(..., description="HKU or external framework")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class RoleSkillRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill_id: str
    target_level: str
    required: bool
    weight: Optional[float] = None

class Role(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_id: str
    role_title: str
    skills_required: List[RoleSkillRequirement]
    description: Optional[str] = None
    version: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

PointerType = Literal["TEXT_OFFSETS", "PAGE_RANGE", "PAGE_ONLY"]

class EvidencePointer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc_id: str
    chunk_id: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    snippet: str = Field(..., max_length=300)
    quote_hash: str = Field(..., description="SHA-256 over canonical span + locator")
    storage_uri: str
    pointer_type: PointerType = "TEXT_OFFSETS"
    created_at: datetime = Field(default_factory=datetime.utcnow)

class AuditLog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor_id: str
    actor_role: str
    action: str
    object_type: str
    object_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    change_summary: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

ConsentState = Literal["granted", "revoked"]

class ConsentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consent_id: str
    doc_id: str
    user_id: str
    state: ConsentState
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    note: Optional[str] = None
