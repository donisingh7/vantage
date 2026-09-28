"""Add crawl jobs and documents for the ingestion pipeline.

Revision ID: 0002_ingestion
Revises: 0001_initial
Create Date: 2026-09-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_ingestion"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

CRAWL_JOB_STATUS = sa.Enum(
    "queued", "running", "completed", "failed", name="crawl_job_status", native_enum=False, length=40
)


def upgrade() -> None:
    op.create_table(
        "crawl_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", CRAWL_JOB_STATUS, nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column("documents_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_crawl_jobs_workspace_id", "crawl_jobs", ["workspace_id"])
    op.create_index("ix_crawl_jobs_source_id", "crawl_jobs", ["source_id"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("content", sa.Text()),
        sa.Column("excerpt", sa.Text()),
        sa.Column("author", sa.String(300)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workspace_id", "canonical_url", name="uq_documents_workspace_canonical_url"),
    )
    op.create_index("ix_documents_workspace_id", "documents", ["workspace_id"])
    op.create_index("ix_documents_source_id", "documents", ["source_id"])
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])


def downgrade() -> None:
    op.drop_index("ix_documents_content_hash", table_name="documents")
    op.drop_index("ix_documents_source_id", table_name="documents")
    op.drop_index("ix_documents_workspace_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_crawl_jobs_source_id", table_name="crawl_jobs")
    op.drop_index("ix_crawl_jobs_workspace_id", table_name="crawl_jobs")
    op.drop_table("crawl_jobs")
