"""P3: RBAC/ABAC tables, review_tickets, org structure (faculties/programmes/terms/teaching_relations)

Revision ID: a1b2c3d4e5f6
Revises: e2f3a4b5c6d7
Create Date: 2026-02-21

"""
from typing import Sequence, Union
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Organisational hierarchy ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS faculties (
            faculty_id  TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS programmes (
            programme_id  TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            faculty_id    TEXT REFERENCES faculties(faculty_id),
            created_at    TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS terms (
            term_id     TEXT PRIMARY KEY,
            label       TEXT NOT NULL,
            start_date  DATE,
            end_date    DATE,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """)
    # Extend existing courses table with programme/faculty linkage
    op.execute("ALTER TABLE courses ADD COLUMN IF NOT EXISTS programme_id TEXT REFERENCES programmes(programme_id);")
    op.execute("ALTER TABLE courses ADD COLUMN IF NOT EXISTS faculty_id TEXT REFERENCES faculties(faculty_id);")
    op.execute("ALTER TABLE courses ADD COLUMN IF NOT EXISTS term_id TEXT REFERENCES terms(term_id);")

    # --- Teaching relations (ABAC context for staff) ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS teaching_relations (
            relation_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      TEXT NOT NULL,
            course_id    TEXT NOT NULL,
            term_id      TEXT,
            role         TEXT DEFAULT 'instructor',
            created_at   TIMESTAMPTZ DEFAULT now(),
            UNIQUE (user_id, course_id, term_id)
        )
    """)

    # --- User roles/context (RBAC + ABAC binding) ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_roles_context (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id        TEXT NOT NULL,
            role           TEXT NOT NULL,
            faculty_id     TEXT,
            programme_id   TEXT,
            course_id      TEXT,
            term_id        TEXT,
            granted_by     TEXT,
            created_at     TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles_context(user_id);")

    # --- Review tickets (Protocol 4: human review workflow) ---
    op.execute("""
        CREATE TABLE IF NOT EXISTS review_tickets (
            ticket_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at          TIMESTAMPTZ DEFAULT now(),
            status              TEXT NOT NULL DEFAULT 'open',
            scope_course_id     TEXT,
            scope_term_id       TEXT,
            skill_id            TEXT,
            role_id             TEXT,
            draft_json          JSONB DEFAULT '{}',
            evidence_pointers   JSONB DEFAULT '[]',
            uncertainty_reason  TEXT,
            routed_to_role      TEXT DEFAULT 'staff',
            resolved_by         TEXT,
            resolved_at         TIMESTAMPTZ,
            resolution          JSONB DEFAULT '{}'
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_review_tickets_status ON review_tickets(status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_review_tickets_course ON review_tickets(scope_course_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS review_tickets;")
    op.execute("DROP TABLE IF EXISTS user_roles_context;")
    op.execute("DROP TABLE IF EXISTS teaching_relations;")
    op.execute("ALTER TABLE courses DROP COLUMN IF EXISTS term_id;")
    op.execute("ALTER TABLE courses DROP COLUMN IF EXISTS faculty_id;")
    op.execute("ALTER TABLE courses DROP COLUMN IF EXISTS programme_id;")
    op.execute("DROP TABLE IF EXISTS terms;")
    op.execute("DROP TABLE IF EXISTS programmes;")
    op.execute("DROP TABLE IF EXISTS faculties;")
