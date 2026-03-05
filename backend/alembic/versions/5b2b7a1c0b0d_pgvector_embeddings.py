"""pgvector embeddings

Revision ID: 5b2b7a1c0b0d
Revises: fdf3677895c4
Create Date: 2026-01-21

"""

from typing import Sequence, Union

from alembic import op


revision: str = "5b2b7a1c0b0d"
down_revision: Union[str, None] = "fdf3677895c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector extension (available in pgvector/pgvector image; safe if already installed)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Store chunk embeddings in Postgres
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chunk_embeddings (
          emb_id UUID PRIMARY KEY,
          doc_id UUID NOT NULL,
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

    # Vector index (cosine distance)
    # Note: ivfflat requires ANALYZE and works best with enough rows; still safe for MVP.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chunk_emb_vec_ivfflat
        ON chunk_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chunk_embeddings;")
    # Keep extension; dropping extension can break other objects.

