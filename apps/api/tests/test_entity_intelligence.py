"""Tests for GET /api/v1/intelligence/entities/{kind}/{entity_id} -- one request replacing
the Entity Intelligence dialog's previous four requests (filtered signals, watchlists
containing entity, all sources, all documents).
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


async def _insert_document(sessions, *, workspace_id, source_id, canonical_url=None):
    content = "Collected content for the entity intelligence test." * 3
    async with sessions() as session:
        document = Document(
            workspace_id=workspace_id, source_id=source_id,
            canonical_url=canonical_url or f"https://example.com/{uuid4()}", title="Doc", content=content,
            excerpt=content[:100], author=None, published_at=None,
            content_hash=hashlib.sha256(str(uuid4()).encode()).hexdigest(), fetched_at=datetime.now(UTC),
        )
        session.add(document)
        await session.commit()
        return document.id


async def _insert_signal(sessions, *, workspace_id, document_id, company_id=None, topic_id=None, importance=0.5):
    async with sessions() as session:
        signal = IntelligenceSignal(
            workspace_id=workspace_id, document_id=document_id, analysis_status=AnalysisStatus.COMPLETED,
            analyzed_at=datetime.now(UTC), signal_type="funding", sentiment="positive",
            title="Signal", executive_summary="Summary", relevance_score=0.5, importance_score=importance,
            key_entities=[], key_points=[], confidence_score=0.5, company_id=company_id, topic_id=topic_id,
        )
        session.add(signal)
        await session.commit()
        return signal.id


async def test_company_entity_returns_only_its_own_signals(client, sessions):
    workspace_id = await _workspace_id(client)
    source = await _create_source(client)
    company_a = (await client.post(f"{API}/companies", json={"name": "Company A"})).json()
    company_b = (await client.post(f"{API}/companies", json={"name": "Company B"})).json()

    doc_a = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
    doc_b = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=doc_a, company_id=UUID(company_a["id"]))
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=doc_b, company_id=UUID(company_b["id"]))

    response = await client.get(f"{API}/intelligence/entities/company/{company_a['id']}")
    assert response.status_code == 200
    body = response.json()
    assert len(body["signals"]) == 1
    assert body["signals"][0]["company_id"] == company_a["id"]


async def test_topic_entity_returns_only_its_own_signals(client, sessions):
    workspace_id = await _workspace_id(client)
    source = await _create_source(client)
    topic_a = (await client.post(f"{API}/topics", json={"name": "Topic A"})).json()
    topic_b = (await client.post(f"{API}/topics", json={"name": "Topic B"})).json()

    doc_a = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
    doc_b = await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=doc_a, topic_id=UUID(topic_a["id"]))
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=doc_b, topic_id=UUID(topic_b["id"]))

    response = await client.get(f"{API}/intelligence/entities/topic/{topic_a['id']}")
    assert response.status_code == 200
    body = response.json()
    assert len(body["signals"]) == 1
    assert body["signals"][0]["topic_id"] == topic_a["id"]


async def test_response_only_includes_relevant_documents_and_sources(client, sessions):
    """Regression guard: must not return every workspace document/source, only those that
    actually back this entity's signals."""
    workspace_id = await _workspace_id(client)
    relevant_source = await _create_source(client, name="Relevant", url="https://example.com/relevant")
    unrelated_source = await _create_source(client, name="Unrelated", url="https://example.com/unrelated")
    company = (await client.post(f"{API}/companies", json={"name": "Company A"})).json()

    relevant_doc = await _insert_document(
        sessions, workspace_id=workspace_id, source_id=UUID(relevant_source["id"]),
        canonical_url="https://example.com/relevant/a",
    )
    await _insert_signal(sessions, workspace_id=workspace_id, document_id=relevant_doc, company_id=UUID(company["id"]))
    # An unrelated document/source exist in the workspace but have no signal for this company.
    await _insert_document(sessions, workspace_id=workspace_id, source_id=UUID(unrelated_source["id"]))

    response = await client.get(f"{API}/intelligence/entities/company/{company['id']}")
    body = response.json()
    assert len(body["documents"]) == 1
    assert body["documents"][0]["id"] == str(relevant_doc)
    assert body["documents"][0]["canonical_url"] == "https://example.com/relevant/a"
    assert len(body["sources"]) == 1
    assert body["sources"][0]["name"] == "Relevant"


async def test_watchlist_containment_is_correct(client, sessions):
    company = (await client.post(f"{API}/companies", json={"name": "Company A"})).json()
    containing = (await client.post(f"{API}/watchlists", json={"name": "Containing"})).json()
    await client.post(f"{API}/watchlists", json={"name": "Not containing"})
    await client.put(f"{API}/watchlists/{containing['id']}/companies/{company['id']}")

    response = await client.get(f"{API}/intelligence/entities/company/{company['id']}")
    watchlists = response.json()["watchlists"]
    assert [item["name"] for item in watchlists] == ["Containing"]


async def test_unknown_entity_returns_404(client):
    response = await client.get(f"{API}/intelligence/entities/company/{uuid4()}")
    assert response.status_code == 404


async def test_entity_intelligence_never_leaks_another_workspaces_entity(client, sessions, other_workspace):
    async with sessions() as session:
        from app.models import Company

        foreign_company = Company(workspace_id=other_workspace.id, name="Foreign Co")
        session.add(foreign_company)
        await session.commit()
        foreign_company_id = foreign_company.id

    response = await client.get(f"{API}/intelligence/entities/company/{foreign_company_id}")
    assert response.status_code == 404


async def test_entity_intelligence_never_constructs_llm_or_embedding_provider(client):
    from app.api.deps import get_embedding_provider, get_llm_provider
    from app.main import app

    def _poison():
        raise AssertionError("entity intelligence must not construct an LLM/embedding provider")

    app.dependency_overrides[get_llm_provider] = _poison
    app.dependency_overrides[get_embedding_provider] = _poison

    company = (await client.post(f"{API}/companies", json={"name": "Company A"})).json()
    response = await client.get(f"{API}/intelligence/entities/company/{company['id']}")

    assert response.status_code == 200
