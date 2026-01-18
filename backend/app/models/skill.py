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
