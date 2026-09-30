"""Tests for GET /api/v1/intelligence/bootstrap -- one request replacing the previous
six-request refresh() (documents, intelligence/signals, sources, companies, topics,
system/info) for the Intelligence page's first render.
"""
import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.models import AnalysisStatus, Document, IntelligenceSignal

API = "/api/v1"


async def _workspace_id(client) -> UUID:
    return UUID((await client.get(f"{API}/me")).json()["workspace"]["id"])


async def _create_source(client, name="Feed", url="https://example.com/feed"):
    response = await client.post(f"{API}/sources", json={"name": name, "url": url, "source_type": "website"})
    assert response.status_code == 201, response.text
    return response.json()


async def _insert_document(sessions, *, workspace_id, source_id, title="Doc"):
    content = "Collected content for the intelligence bootstrap test." * 3
    async with sessions() as session:
        document = Document(
            workspace_id=workspace_id, source_id=source_id,
            canonical_url=f"https://example.com/{uuid4()}", title=title, content=content,
            excerpt=content[:100], author=None, published_at=None,
            content_hash=hashlib.sha256(f"{title}-{uuid4()}".encode()).hexdigest(), fetched_at=datetime.now(UTC),
        )
        session.add(document)
        await session.commit()
        return document.id


async def _insert_signal(sessions, *, workspace_id, document_id, status=AnalysisStatus.COMPLETED):
    async with sessions() as session:
        signal = IntelligenceSignal(
            workspace_id=workspace_id, document_id=document_id, analysis_status=status,
            analyzed_at=datetime.now(UTC), signal_type="funding", sentiment="positive",
            title="Signal", executive_summary="Summary", relevance_score=0.5, importance_score=0.5,
            key_entities=[], key_points=[], confidence_score=0.5,
        )
        session.add(signal)
        await session.commit()
        return signal.id


async def test_empty_workspace_returns_empty_lists(client):
    response = await client.get(f"{API}/intelligence/bootstrap")
    assert response.status_code == 200
    body = response.json()
    assert body["documents"] == []
    assert body["signals"] == []
    assert body["sources"] == []
    assert body["companies"] == []
    assert body["topics"] == []
    assert body["providers"] == {"llm_provider": "mock", "embedding_provider": "mock"}


async def test_populated_workspace_returns_documents_signals_and_narrow_lookups(client, sessions):
    workspace_id = await _workspace_id(client)
    source = await _create_source(client)
    await client.post(f"{API}/companies", json={"name": "Acme"})
    await client.post(f"{API}/topics", json={"name": "Cloud"})
    document_id = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=document_id)

    response = await client.get(f"{API}/intelligence/bootstrap")
    body = response.json()
    assert len(body["documents"]) == 1
    assert body["documents"][0]["id"] == str(document_id)
    assert len(body["signals"]) == 1
    assert body["signals"][0]["document_id"] == str(document_id)
    assert [item["name"] for item in body["sources"]] == ["Feed"]
    assert set(body["sources"][0].keys()) == {"id", "name"}
    assert [item["name"] for item in body["companies"]] == ["Acme"]
    assert [item["name"] for item in body["topics"]] == ["Cloud"]


async def test_document_analysis_status_and_signal_id_are_populated(client, sessions):
    workspace_id = await _workspace_id(client)
    source = await _create_source(client)
    document_id = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
    signal_id = await _insert_signal(sessions, workspace_id=workspace_id, document_id=document_id)

    response = await client.get(f"{API}/intelligence/bootstrap")
    document = response.json()["documents"][0]
    assert document["analysis_status"] == "completed"
    assert document["signal_id"] == str(signal_id)


async def test_failed_and_irrelevant_signals_are_excluded_from_the_signal_list(client, sessions):
    workspace_id = await _workspace_id(client)
    source = await _create_source(client)
    completed_doc = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
    failed_doc = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=completed_doc, status=AnalysisStatus.COMPLETED)
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=failed_doc, status=AnalysisStatus.FAILED)

    response = await client.get(f"{API}/intelligence/bootstrap")
    body = response.json()
    assert len(body["documents"]) == 2  # both documents still show up
    assert len(body["signals"]) == 1  # only the completed signal is returned


async def test_intelligence_bootstrap_never_leaks_another_workspaces_data(client, sessions, other_workspace):
    from app.models import Source, SourceType

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
        await session.commit()

    response = await client.get(f"{API}/intelligence/bootstrap")
    body = response.json()
    assert body["documents"] == []
    assert body["signals"] == []
    assert body["sources"] == []


async def test_intelligence_bootstrap_never_constructs_llm_or_embedding_provider(client):
    from app.api.deps import get_embedding_provider, get_llm_provider
    from app.main import app

    def _poison():
        raise AssertionError("intelligence bootstrap must not construct an LLM/embedding provider")

    app.dependency_overrides[get_llm_provider] = _poison
    app.dependency_overrides[get_embedding_provider] = _poison

    response = await client.get(f"{API}/intelligence/bootstrap")

    assert response.status_code == 200
