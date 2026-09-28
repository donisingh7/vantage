"""Add document_chunks table and Document.indexed_content_hash for semantic search.

Revision ID: 0005_semantic
Revises: 0004_intelligence
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_semantic"
down_revision = "0004_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("indexed_content_hash", sa.String(64)))

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "workspace_id", "document_id", "chunk_index", name="uq_document_chunks_workspace_document_chunk"
        ),
    )
    op.create_index("ix_document_chunks_workspace_id", "document_chunks", ["workspace_id"])
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_workspace_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_column("documents", "indexed_content_hash")
