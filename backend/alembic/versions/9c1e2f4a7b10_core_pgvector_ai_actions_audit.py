"""core tables + pgvector + ai persistence + actions + audit

Revision ID: 9c1e2f4a7b10
Revises: fdf3677895c4
Create Date: 2026-01-21
"""

from typing import Sequence, Union

from alembic import op


revision: str = "9c1e2f4a7b10"
down_revision: Union[str, None] = "fdf3677895c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- pgvector ---
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # --- documents / chunks ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
          doc_id UUID PRIMARY KEY,
          filename TEXT NOT NULL,
          stored_path TEXT NOT NULL,
          doc_type TEXT NOT NULL,
          title TEXT,
          source_type TEXT,
          storage_uri TEXT,
          metadata_json JSONB,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
          chunk_id UUID PRIMARY KEY,
          doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
          idx INTEGER NOT NULL,
          char_start INTEGER NOT NULL,
          char_end INTEGER NOT NULL,
          snippet TEXT NOT NULL,
          quote_hash TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          chunk_text TEXT NOT NULL,
          section_path TEXT,
          page_start INTEGER,
          page_end INTEGER,
          stored_path TEXT,
          storage_uri TEXT
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_chunks_doc_idx ON chunks(doc_id, idx);")

    # --- embeddings (pgvector) ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chunk_embeddings (
          emb_id UUID PRIMARY KEY,
          doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
          chunk_id UUID NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
          model_name TEXT NOT NULL,
          dim INTEGER NOT NULL,
          embedding vector(384) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunk_emb_doc ON chunk_embeddings(doc_id);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_chunk_emb_chunk_model ON chunk_embeddings(chunk_id, model_name);")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chunk_emb_vec_ivfflat
        ON chunk_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
        """
    )

    # --- skill assessments/proficiency (storage for Decision 2/3 outputs) ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_assessments (
          assessment_id UUID PRIMARY KEY,
          doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
          skill_id TEXT NOT NULL,
          decision TEXT NOT NULL,
          evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
          decision_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_skill_assess_doc ON skill_assessments(doc_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_skill_assess_skill ON skill_assessments(skill_id);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_proficiency (
          prof_id UUID PRIMARY KEY,
          doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
          skill_id TEXT NOT NULL,
          level INTEGER NOT NULL,
          label TEXT NOT NULL,
          rationale TEXT NOT NULL,
          best_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
          signals JSONB NOT NULL DEFAULT '{}'::jsonb,
          meta JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_skill_prof_doc ON skill_proficiency(doc_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_skill_prof_skill ON skill_proficiency(skill_id);")

    # --- AI persistence (B2) ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_demonstrations (
          ai_id UUID PRIMARY KEY,
          doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
          skill_id TEXT NOT NULL,
          model_name TEXT NOT NULL,
          prompt_hash TEXT NOT NULL,
          cache_key TEXT NOT NULL,
          request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          retrieval_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          raw_output TEXT,
          parsed_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          status TEXT NOT NULL,
          error TEXT,
          duration_ms INTEGER,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_demo_doc_skill ON ai_demonstrations(doc_id, skill_id);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_demo_cache ON ai_demonstrations(cache_key);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_proficiencies (
          ai_id UUID PRIMARY KEY,
          doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
          skill_id TEXT NOT NULL,
          model_name TEXT NOT NULL,
          prompt_hash TEXT NOT NULL,
          cache_key TEXT NOT NULL,
          request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          retrieval_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          raw_output TEXT,
          parsed_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          status TEXT NOT NULL,
          error TEXT,
          duration_ms INTEGER,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_prof_doc_skill ON ai_proficiencies(doc_id, skill_id);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_prof_cache ON ai_proficiencies(cache_key);")

    # --- readiness (Decision 4 storage) ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS role_readiness (
          readiness_id UUID PRIMARY KEY,
          doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
          role_id TEXT NOT NULL,
          result JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_readiness_doc_role ON role_readiness(doc_id, role_id);")

    # --- action engine (Decision 5) ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS action_templates (
          template_id UUID PRIMARY KEY,
          skill_id TEXT,
          gap_type TEXT NOT NULL,
          min_level INTEGER,
          max_level INTEGER,
          template_json JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_action_tpl_skill_gap ON action_templates(skill_id, gap_type);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS action_recommendations (
          rec_id UUID PRIMARY KEY,
          doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
          role_id TEXT NOT NULL,
          result JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_action_rec_doc_role ON action_recommendations(doc_id, role_id);")

    # --- audit logs (C2) ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
          audit_id UUID PRIMARY KEY,
          subject_id TEXT NOT NULL,
          role TEXT NOT NULL,
          action TEXT NOT NULL,
          object_type TEXT NOT NULL,
          object_id TEXT,
          request_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
          response_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
          status TEXT NOT NULL,
          error TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_subject ON audit_logs(subject_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_object ON audit_logs(object_type, object_id);")


def downgrade() -> None:
    # best-effort teardown
    op.execute("DROP TABLE IF EXISTS audit_logs;")
    op.execute("DROP TABLE IF EXISTS action_recommendations;")
    op.execute("DROP TABLE IF EXISTS action_templates;")
    op.execute("DROP TABLE IF EXISTS role_readiness;")
    op.execute("DROP TABLE IF EXISTS ai_proficiencies;")
    op.execute("DROP TABLE IF EXISTS ai_demonstrations;")
    op.execute("DROP TABLE IF EXISTS skill_proficiency;")
    op.execute("DROP TABLE IF EXISTS skill_assessments;")
    op.execute("DROP TABLE IF EXISTS chunk_embeddings;")
    op.execute("DROP TABLE IF EXISTS chunks;")
    op.execute("DROP TABLE IF EXISTS documents;")

