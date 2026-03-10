"""tutor_dialogue_sessions and tutor_dialogue_turns for Live Agent (RAG) tutor

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-03-10

Strategy 1: trained Live Agent + OpenAI RAG — session and turn persistence.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "h2i3j4k5l6m7"
down_revision: Union[str, None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS tutor_dialogue_sessions (
            session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL,
            skill_id TEXT NOT NULL,
            doc_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'concluded')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_tutor_sessions_user ON tutor_dialogue_sessions(user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tutor_sessions_skill ON tutor_dialogue_sessions(skill_id);")

    op.execute("""
        CREATE TABLE IF NOT EXISTS tutor_dialogue_turns (
            turn_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL REFERENCES tutor_dialogue_sessions(session_id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            retrieved_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_tutor_turns_session ON tutor_dialogue_turns(session_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tutor_dialogue_turns;")
    op.execute("DROP TABLE IF EXISTS tutor_dialogue_sessions;")
