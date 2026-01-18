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
