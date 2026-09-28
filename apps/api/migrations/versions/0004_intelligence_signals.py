"""Add intelligence_signals table for structured document analysis.

Revision ID: 0004_intelligence
Revises: 0003_crawling
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_intelligence"
down_revision = "0003_crawling"
branch_labels = None
depends_on = None

SIGNAL_TYPE = sa.Enum(
    "product", "competitor", "funding", "partnership", "acquisition", "leadership",
    "regulation", "technology", "market", "pricing", "risk", "other",
    name="signal_type", native_enum=False, length=40,
)
SENTIMENT = sa.Enum(
    "positive", "neutral", "negative", "mixed", name="sentiment", native_enum=False, length=40
)
ANALYSIS_STATUS = sa.Enum(
    "completed", "irrelevant", "failed", name="analysis_status", native_enum=False, length=40
)


def upgrade() -> None:
    op.create_table(
        "intelligence_signals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="SET NULL")),
        sa.Column("topic_id", sa.Uuid(), sa.ForeignKey("topics.id", ondelete="SET NULL")),
        sa.Column("signal_type", SIGNAL_TYPE),
        sa.Column("title", sa.String(300)),
        sa.Column("executive_summary", sa.Text()),
        sa.Column("relevance_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("importance_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sentiment", SENTIMENT),
        sa.Column("key_entities", sa.JSON(), nullable=False),
        sa.Column("key_points", sa.JSON(), nullable=False),
        sa.Column("business_impact", sa.Text()),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_excerpt", sa.Text()),
        sa.Column("analysis_status", ANALYSIS_STATUS, nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workspace_id", "document_id", name="uq_intelligence_signals_workspace_document"),
    )
    op.create_index("ix_intelligence_signals_workspace_id", "intelligence_signals", ["workspace_id"])
    op.create_index("ix_intelligence_signals_document_id", "intelligence_signals", ["document_id"])
    op.create_index("ix_intelligence_signals_company_id", "intelligence_signals", ["company_id"])
    op.create_index("ix_intelligence_signals_topic_id", "intelligence_signals", ["topic_id"])


def downgrade() -> None:
    op.drop_index("ix_intelligence_signals_topic_id", table_name="intelligence_signals")
    op.drop_index("ix_intelligence_signals_company_id", table_name="intelligence_signals")
    op.drop_index("ix_intelligence_signals_document_id", table_name="intelligence_signals")
    op.drop_index("ix_intelligence_signals_workspace_id", table_name="intelligence_signals")
    op.drop_table("intelligence_signals")
