"""Add source scheduling and discovery crawl counters.

Revision ID: 0003_crawling
Revises: 0002_ingestion
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_crawling"
down_revision = "0002_ingestion"
branch_labels = None
depends_on = None

INGESTION_INTERVAL = sa.Enum(
    "manual", "every_6_hours", "every_12_hours", "every_24_hours",
    name="ingestion_interval", native_enum=False, length=40,
)


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("ingestion_interval", INGESTION_INTERVAL, nullable=False, server_default="manual"),
    )
    op.add_column("crawl_jobs", sa.Column("documents_skipped", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("crawl_jobs", sa.Column("pages_discovered", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("crawl_jobs", sa.Column("pages_failed", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("crawl_jobs", "pages_failed")
    op.drop_column("crawl_jobs", "pages_discovered")
    op.drop_column("crawl_jobs", "documents_skipped")
    op.drop_column("sources", "ingestion_interval")
