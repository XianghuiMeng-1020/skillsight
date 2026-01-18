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
