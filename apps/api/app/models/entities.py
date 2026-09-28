from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey


def _checked_string_enum(enum_type: type[Enum], name: str) -> SQLAlchemyEnum:
    """Stored as a constrained string so one schema serves both SQLite and PostgreSQL."""
    return SQLAlchemyEnum(
        enum_type,
        name=name,
        native_enum=False,
        length=40,
        values_callable=lambda members: [member.value for member in members],
    )


class MemberRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class SourceType(str, Enum):
    WEBSITE = "website"
    RSS = "rss"
    NEWS = "news"
    BLOG = "blog"
    OTHER = "other"


class IngestionInterval(str, Enum):
    MANUAL = "manual"
    EVERY_6_HOURS = "every_6_hours"
    EVERY_12_HOURS = "every_12_hours"
    EVERY_24_HOURS = "every_24_hours"


def _watchlist_link_table(table_name: str, column_name: str, target_table: str) -> Table:
    return Table(
        table_name,
        Base.metadata,
        Column("watchlist_id", ForeignKey("watchlists.id", ondelete="CASCADE"), primary_key=True),
        Column(column_name, ForeignKey(f"{target_table}.id", ondelete="CASCADE"), primary_key=True),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    )


watchlist_companies = _watchlist_link_table("watchlist_companies", "company_id", "companies")
watchlist_topics = _watchlist_link_table("watchlist_topics", "topic_id", "topics")
watchlist_sources = _watchlist_link_table("watchlist_sources", "source_id", "sources")


class User(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Workspace(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "workspaces"
    __table_args__ = (UniqueConstraint("slug", name="uq_workspaces_slug"),)

    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(80))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class WorkspaceMember(UUIDPrimaryKey, Base):
    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
        Index("ix_workspace_members_workspace_id", "workspace_id"),
        Index("ix_workspace_members_user_id", "user_id"),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[MemberRole] = mapped_column(_checked_string_enum(MemberRole, "member_role"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )


class WorkspaceEntity(UUIDPrimaryKey, Timestamped):
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )


class Watchlist(WorkspaceEntity, Base):
    __tablename__ = "watchlists"

    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    companies: Mapped[list["Company"]] = relationship(
        secondary=watchlist_companies, lazy="selectin", order_by="Company.name"
    )
    topics: Mapped[list["Topic"]] = relationship(
        secondary=watchlist_topics, lazy="selectin", order_by="Topic.name"
    )
    sources: Mapped[list["Source"]] = relationship(
        secondary=watchlist_sources, lazy="selectin", order_by="Source.name"
    )


class Company(WorkspaceEntity, Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("workspace_id", "domain", name="uq_companies_workspace_domain"),)

    name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str | None] = mapped_column(String(253))
    description: Mapped[str | None] = mapped_column(Text())


class Topic(WorkspaceEntity, Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_topics_workspace_name"),)

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text())


class Source(WorkspaceEntity, Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("workspace_id", "url", name="uq_sources_workspace_url"),)

    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(2048))
    source_type: Mapped[SourceType] = mapped_column(_checked_string_enum(SourceType, "source_type"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ingestion_interval: Mapped[IngestionInterval] = mapped_column(
        _checked_string_enum(IngestionInterval, "ingestion_interval"),
        default=IngestionInterval.MANUAL,
        nullable=False,
    )


class CrawlJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CrawlJob(WorkspaceEntity, Base):
    __tablename__ = "crawl_jobs"

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[CrawlJobStatus] = mapped_column(
        _checked_string_enum(CrawlJobStatus, "crawl_job_status"),
        default=CrawlJobStatus.QUEUED,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text())
    documents_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    documents_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    documents_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pages_discovered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Document(WorkspaceEntity, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("workspace_id", "canonical_url", name="uq_documents_workspace_canonical_url"),
    )

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True, nullable=False
    )
    canonical_url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str | None] = mapped_column(Text())
    excerpt: Mapped[str | None] = mapped_column(Text())
    author: Mapped[str | None] = mapped_column(String(300))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    indexed_content_hash: Mapped[str | None] = mapped_column(String(64))
    # Which embedding provider/config produced the current DocumentChunk rows (see
    # EmbeddingProvider.fingerprint()). A document is only "currently indexed" when both
    # this AND indexed_content_hash still match -- otherwise a provider/dimension switch
    # would silently leave stale, dimension-mismatched vectors behind.
    indexed_embedding_fingerprint: Mapped[str | None] = mapped_column(String(200))


class DocumentChunk(WorkspaceEntity, Base):
    """A deterministic slice of a Document's text plus its embedding.

    Stored as a JSON float array so SQLite needs no vector extension; a future
    PostgreSQL/pgvector backend can replace this table without touching callers,
    since SemanticSearchService owns all reads/writes of embeddings.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "document_id", "chunk_index", name="uq_document_chunks_workspace_document_chunk"
        ),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False)


class SignalType(str, Enum):
    PRODUCT = "product"
    COMPETITOR = "competitor"
    FUNDING = "funding"
    PARTNERSHIP = "partnership"
    ACQUISITION = "acquisition"
    LEADERSHIP = "leadership"
    REGULATION = "regulation"
    TECHNOLOGY = "technology"
    MARKET = "market"
    PRICING = "pricing"
    RISK = "risk"
    OTHER = "other"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"


class AnalysisStatus(str, Enum):
    COMPLETED = "completed"
    IRRELEVANT = "irrelevant"
    FAILED = "failed"


class IntelligenceSignal(WorkspaceEntity, Base):
    """One analyzed signal per Document. Reprocessing overwrites the existing row."""

    __tablename__ = "intelligence_signals"
    __table_args__ = (
        UniqueConstraint("workspace_id", "document_id", name="uq_intelligence_signals_workspace_document"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    topic_id: Mapped[UUID | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), index=True)
    signal_type: Mapped[SignalType | None] = mapped_column(_checked_string_enum(SignalType, "signal_type"))
    title: Mapped[str | None] = mapped_column(String(300))
    executive_summary: Mapped[str | None] = mapped_column(Text())
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    importance_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sentiment: Mapped[Sentiment | None] = mapped_column(_checked_string_enum(Sentiment, "sentiment"))
    key_entities: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    key_points: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    business_impact: Mapped[str | None] = mapped_column(Text())
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    evidence_excerpt: Mapped[str | None] = mapped_column(Text())
    analysis_status: Mapped[AnalysisStatus] = mapped_column(
        _checked_string_enum(AnalysisStatus, "analysis_status"), nullable=False
    )
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
