"""Create workspace-aware core tables and watchlist associations.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

MEMBER_ROLE = sa.Enum(
    "owner", "admin", "member", "viewer", name="member_role", native_enum=False, length=40
)
SOURCE_TYPE = sa.Enum(
    "website", "rss", "news", "blog", "other", name="source_type", native_enum=False, length=40
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _workspace_column() -> sa.Column:
    return sa.Column(
        "workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )


def _create_link_table(table_name: str, column_name: str, target_table: str) -> None:
    op.create_table(
        table_name,
        sa.Column("watchlist_id", sa.Uuid(), sa.ForeignKey("watchlists.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(column_name, sa.Uuid(), sa.ForeignKey(f"{target_table}.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("slug", name="uq_workspaces_slug"),
    )

    op.create_table(
        "workspace_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", MEMBER_ROLE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
    )
    op.create_index("ix_workspace_members_workspace_id", "workspace_members", ["workspace_id"])
    op.create_index("ix_workspace_members_user_id", "workspace_members", ["user_id"])

    op.create_table(
        "watchlists",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _workspace_column(),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )
    op.create_index("ix_watchlists_workspace_id", "watchlists", ["workspace_id"])

    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _workspace_column(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("domain", sa.String(253)),
        sa.Column("description", sa.Text()),
        *_timestamps(),
        sa.UniqueConstraint("workspace_id", "domain", name="uq_companies_workspace_domain"),
    )
    op.create_index("ix_companies_workspace_id", "companies", ["workspace_id"])

    op.create_table(
        "topics",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _workspace_column(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        *_timestamps(),
        sa.UniqueConstraint("workspace_id", "name", name="uq_topics_workspace_name"),
    )
    op.create_index("ix_topics_workspace_id", "topics", ["workspace_id"])

    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _workspace_column(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("source_type", SOURCE_TYPE, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.UniqueConstraint("workspace_id", "url", name="uq_sources_workspace_url"),
    )
    op.create_index("ix_sources_workspace_id", "sources", ["workspace_id"])

    _create_link_table("watchlist_companies", "company_id", "companies")
    _create_link_table("watchlist_topics", "topic_id", "topics")
    _create_link_table("watchlist_sources", "source_id", "sources")


def downgrade() -> None:
    for table_name in ("watchlist_sources", "watchlist_topics", "watchlist_companies"):
        op.drop_table(table_name)
    for table_name in ("sources", "topics", "companies", "watchlists"):
        op.drop_index(f"ix_{table_name}_workspace_id", table_name=table_name)
        op.drop_table(table_name)
    op.drop_index("ix_workspace_members_user_id", table_name="workspace_members")
    op.drop_index("ix_workspace_members_workspace_id", table_name="workspace_members")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
    op.drop_table("users")
