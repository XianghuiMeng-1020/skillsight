# backend/app/models/skill_alias.py
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import Text, Numeric
from sqlalchemy.sql.sqltypes import DateTime

from backend.app.db.base import Base


class SkillAlias(Base):
    __tablename__ = "skill_aliases"

    # matches DB: alias_id uuid primary key
    alias_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # matches DB: skill_id text not null
    skill_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("skills.skill_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # matches DB: alias text not null
    alias: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    # matches DB: source text not null default 'manual'
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'manual'"))

    # matches DB: confidence numeric not null default 1.0
    confidence: Mapped[float] = mapped_column(
        Numeric, nullable=False, server_default=text("1.0")
    )

    # matches DB: status text not null default 'active'
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))

    # matches DB: created_at timestamptz not null default now()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (UniqueConstraint("skill_id", "alias", name="uq_skill_aliases_pair"),)