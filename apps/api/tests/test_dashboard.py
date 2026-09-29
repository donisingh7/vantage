"""Tests for GET /api/v1/dashboard/overview -- the Pass 2 consolidated dashboard bootstrap.

These insert signals/jobs directly via the `sessions` fixture (rather than going through
`/documents/{id}/analyze` or `/sources/{id}/ingest`) so ordering, scores, and timestamps are
fully controlled and no network fetch or LLM call is ever attempted.
"""
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.models import (
    AnalysisStatus,
    CrawlJob,
    CrawlJobStatus,
    Document,
    IntelligenceSignal,
    Source,
    SourceType,
)

API = "/api/v1"


async def _workspace_id(client) -> UUID:
    return UUID((await client.get(f"{API}/me")).json()["workspace"]["id"])


async def _create_source(client, name="Feed", url="https://example.com/feed"):
    response = await client.post(f"{API}/sources", json={"name": name, "url": url, "source_type": "website"})
    assert response.status_code == 201, response.text
    return response.json()


async def _insert_document(sessions, *, workspace_id, source_id, title="Doc"):
    content = "Some collected content for the dashboard test." * 3
    async with sessions() as session:
        document = Document(
            workspace_id=workspace_id,
            source_id=source_id,
            canonical_url=f"https://example.com/{uuid4()}",
            title=title,
            content=content,
            excerpt=content[:100],
            author=None,
            published_at=None,
            content_hash=hashlib.sha256(f"{title}-{uuid4()}".encode()).hexdigest(),
            fetched_at=datetime.now(UTC),
        )
        session.add(document)
        await session.commit()
        return document.id


async def _insert_signal(
    sessions,
    *,
    workspace_id,
    document_id,
    importance=0.5,
    analyzed_at=None,
    signal_type="product",
    sentiment="neutral",
    company_id=None,
    topic_id=None,
    status=AnalysisStatus.COMPLETED,
):
    async with sessions() as session:
        signal = IntelligenceSignal(
            workspace_id=workspace_id,
            document_id=document_id,
            analysis_status=status,
            analyzed_at=analyzed_at or datetime.now(UTC),
            signal_type=signal_type,
            sentiment=sentiment,
            title="Signal",
            executive_summary="Summary",
            relevance_score=0.5,
            importance_score=importance,
            key_entities=[],
            key_points=[],
            confidence_score=0.5,
            company_id=company_id,
            topic_id=topic_id,
        )
        session.add(signal)
        await session.commit()
        return signal.id


async def _insert_job(
    sessions, *, workspace_id, source_id, created_at=None, status=CrawlJobStatus.COMPLETED, documents_created=1
):
    async with sessions() as session:
        job = CrawlJob(
            workspace_id=workspace_id,
            source_id=source_id,
            status=status,
            documents_found=1,
            documents_created=documents_created,
            documents_skipped=0,
            pages_discovered=1,
            pages_failed=0,
        )
        if created_at is not None:
            job.created_at = created_at
        session.add(job)
        await session.commit()
        return job.id


# -- Empty workspace -----------------------------------------------------------


async def test_empty_workspace_returns_zeroed_summary_and_empty_arrays(client):
    response = await client.get(f"{API}/dashboard/overview")
    assert response.status_code == 200
    body = response.json()

    assert body["summary"] == {
        "watchlists": 0, "companies": 0, "topics": 0, "sources": 0,
        "active_watchlists": 0, "active_sources": 0,
    }
    assert body["priority_signals"] == []
    assert body["latest_signals"] == []
    assert body["signal_type_counts"] == []
    assert body["sentiment_counts"] == []
    assert body["recent_jobs"] == []
    assert body["focus_companies"] == []
    assert body["focus_topics"] == []
    assert body["providers"] == {"llm_provider": "mock", "embedding_provider": "mock"}


# -- Populated workspace: summary + active counts -------------------------------


async def test_populated_workspace_summary_counts_are_correct(client):
    await client.post(f"{API}/watchlists", json={"name": "Active watchlist", "is_active": True})
    await client.post(f"{API}/watchlists", json={"name": "Paused watchlist", "is_active": False})
    await client.post(f"{API}/companies", json={"name": "Acme Ventures"})
    await client.post(f"{API}/topics", json={"name": "Cloud Infrastructure"})
    active_source = await _create_source(client, name="Active source", url="https://example.com/a")
    paused_source = await _create_source(client, name="Paused source", url="https://example.com/b")
    await client.patch(f"{API}/sources/{paused_source['id']}", json={"is_active": False})

    response = await client.get(f"{API}/dashboard/overview")
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["watchlists"] == 2
    assert summary["active_watchlists"] == 1
    assert summary["companies"] == 1
    assert summary["topics"] == 1
    assert summary["sources"] == 2
    assert summary["active_sources"] == 1
    assert active_source["is_active"] is True


# -- Priority ordering -----------------------------------------------------------


async def test_priority_signals_ordered_by_importance_descending(client, sessions):
    workspace_id = await _workspace_id(client)
    source = await _create_source(client)
    low_doc = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]), title="Low")
    mid_doc = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]), title="Mid")
    high_doc = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]), title="High")
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=low_doc, importance=0.1)
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=mid_doc, importance=0.5)
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=high_doc, importance=0.9)

    response = await client.get(f"{API}/dashboard/overview")
    titles = [item["title"] for item in response.json()["priority_signals"]]
    scores = [item["importance_score"] for item in response.json()["priority_signals"]]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 0.9
    assert len(titles) == 3


# -- Latest ordering ---------------------------------------------------------------


async def test_latest_signals_ordered_by_analyzed_at_descending(client, sessions):
    workspace_id = await _workspace_id(client)
    source = await _create_source(client)
    now = datetime.now(UTC)
    older_doc = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
    newer_doc = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
    older_id = await _insert_signal(
        sessions, workspace_id=workspace_id, document_id=older_doc, importance=0.9, analyzed_at=now - timedelta(days=2)
    )
    newer_id = await _insert_signal(
        sessions, workspace_id=workspace_id, document_id=newer_doc, importance=0.1, analyzed_at=now
    )

    response = await client.get(f"{API}/dashboard/overview")
    latest_ids = [item["id"] for item in response.json()["latest_signals"]]
    assert latest_ids[0] == str(newer_id)
    assert str(older_id) in latest_ids


# -- Type distribution ---------------------------------------------------------------


async def test_signal_type_counts_group_correctly_and_null_becomes_other(client, sessions):
    workspace_id = await _workspace_id(client)
    source = await _create_source(client)
    for _ in range(2):
        doc = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
        await _insert_signal(sessions, workspace_id=workspace_id, document_id=doc, signal_type="funding")
    doc = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=doc, signal_type=None)

    response = await client.get(f"{API}/dashboard/overview")
    counts = {item["key"]: item["count"] for item in response.json()["signal_type_counts"]}
    assert counts == {"funding": 2, "other": 1}
    ordered_keys = [item["key"] for item in response.json()["signal_type_counts"]]
    assert ordered_keys[0] == "funding"  # highest count first


# -- Sentiment distribution -----------------------------------------------------------


async def test_sentiment_counts_group_correctly_and_null_becomes_neutral(client, sessions):
    workspace_id = await _workspace_id(client)
    source = await _create_source(client)
    doc_a = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
    doc_b = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
    doc_c = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=doc_a, sentiment="positive")
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=doc_b, sentiment="positive")
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=doc_c, sentiment=None)

    response = await client.get(f"{API}/dashboard/overview")
    counts = {item["key"]: item["count"] for item in response.json()["sentiment_counts"]}
    assert counts == {"positive": 2, "neutral": 1}


# -- Recent ingestion jobs -----------------------------------------------------------


async def test_recent_jobs_are_newest_first_and_include_source_name(client, sessions):
    workspace_id = await _workspace_id(client)
    source = await _create_source(client, name="Newsroom")
    now = datetime.now(UTC)
    job_ids = []
    for offset in range(6):
        job_id = await _insert_job(
            sessions, workspace_id=workspace_id, source_id=UUID(source["id"]), created_at=now - timedelta(minutes=offset)
        )
        job_ids.append(job_id)

    response = await client.get(f"{API}/dashboard/overview")
    recent = response.json()["recent_jobs"]
    assert len(recent) == 5  # bounded to the latest 5, not all 6
    assert recent[0]["id"] == str(job_ids[0])  # offset=0 is the newest
    assert all(item["source_name"] == "Newsroom" for item in recent)


# -- Focus company ranking -----------------------------------------------------------


async def test_focus_companies_ranked_by_linked_completed_signal_count(client, sessions):
    workspace_id = await _workspace_id(client)
    source = await _create_source(client)
    company_a = (await client.post(f"{API}/companies", json={"name": "Company A"})).json()
    company_b = (await client.post(f"{API}/companies", json={"name": "Company B"})).json()

    for _ in range(3):
        doc = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
        await _insert_signal(sessions, workspace_id=workspace_id, document_id=doc, company_id=UUID(company_a["id"]))
    doc = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=doc, company_id=UUID(company_b["id"]))

    response = await client.get(f"{API}/dashboard/overview")
    focus = response.json()["focus_companies"]
    assert focus[0]["id"] == company_a["id"]
    assert focus[0]["name"] == "Company A"
    assert focus[0]["count"] == 3
    assert focus[1]["count"] == 1


# -- Focus topic ranking -----------------------------------------------------------


async def test_focus_topics_ranked_by_linked_completed_signal_count(client, sessions):
    workspace_id = await _workspace_id(client)
    source = await _create_source(client)
    topic_a = (await client.post(f"{API}/topics", json={"name": "Topic A"})).json()
    topic_b = (await client.post(f"{API}/topics", json={"name": "Topic B"})).json()

    for _ in range(2):
        doc = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
        await _insert_signal(sessions, workspace_id=workspace_id, document_id=doc, topic_id=UUID(topic_a["id"]))
    doc = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=doc, topic_id=UUID(topic_b["id"]))

    response = await client.get(f"{API}/dashboard/overview")
    focus = response.json()["focus_topics"]
    assert focus[0]["id"] == topic_a["id"]
    assert focus[0]["count"] == 2
    assert focus[1]["id"] == topic_b["id"]


# -- Workspace isolation -----------------------------------------------------------


async def test_dashboard_overview_never_leaks_another_workspaces_data(client, sessions, other_workspace):
    async with sessions() as session:
        foreign_source = Source(
            workspace_id=other_workspace.id, name="Foreign", url="https://foreign.example/feed",
            source_type=SourceType.WEBSITE,
        )
        session.add(foreign_source)
        await session.flush()
        foreign_document = Document(
            workspace_id=other_workspace.id, source_id=foreign_source.id,
            canonical_url="https://foreign.example/a", title="Foreign doc", content="content",
            excerpt=None, author=None, published_at=None, content_hash="x" * 64, fetched_at=datetime.now(UTC),
        )
        session.add(foreign_document)
        await session.flush()
        session.add(IntelligenceSignal(
            workspace_id=other_workspace.id, document_id=foreign_document.id,
            analysis_status=AnalysisStatus.COMPLETED, analyzed_at=datetime.now(UTC),
            signal_type="funding", sentiment="positive", title="Foreign signal",
            relevance_score=0.9, importance_score=0.9, key_entities=[], key_points=[], confidence_score=0.9,
        ))
        session.add(CrawlJob(
            workspace_id=other_workspace.id, source_id=foreign_source.id, status=CrawlJobStatus.COMPLETED,
            documents_found=1, documents_created=1, documents_skipped=0, pages_discovered=1, pages_failed=0,
        ))
        await session.commit()

    response = await client.get(f"{API}/dashboard/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["sources"] == 0
    assert body["priority_signals"] == []
    assert body["latest_signals"] == []
    assert body["signal_type_counts"] == []
    assert body["sentiment_counts"] == []
    assert body["recent_jobs"] == []


# -- No AI provider construction on this read path -----------------------------------


async def test_dashboard_overview_never_constructs_llm_or_embedding_provider(client):
    """If this endpoint ever gains an LLM/embedding dependency, this test fails loudly
    instead of silently adding a Gemini/Azure client construction to a read-only path."""
    from app.api.deps import get_embedding_provider, get_llm_provider
    from app.main import app

    def _poison():
        raise AssertionError("dashboard overview must not construct an LLM/embedding provider")

    app.dependency_overrides[get_llm_provider] = _poison
    app.dependency_overrides[get_embedding_provider] = _poison

    response = await client.get(f"{API}/dashboard/overview")

    assert response.status_code == 200
