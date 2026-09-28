"""Add Document.indexed_embedding_fingerprint so a provider/config switch invalidates the index.

Revision ID: 0006_fingerprint
Revises: 0005_semantic
Create Date: 2026-09-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_fingerprint"
down_revision = "0005_semantic"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("indexed_embedding_fingerprint", sa.String(200)))


def downgrade() -> None:
    op.drop_column("documents", "indexed_embedding_fingerprint")
