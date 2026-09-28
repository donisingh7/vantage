import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.models import Document, DocumentChunk, Source, SourceType
from app.providers.embeddings import MockEmbeddingProvider
from app.services.chunking import chunk_text

API = "/api/v1"

DOC_A_CONTENT = "Quarterly earnings exceeded analyst expectations across every reporting segment this year."
DOC_B_CONTENT = "A short guide to the best hiking trails near the coast during autumn weekends."


async def create_source(client, name="Feed", url="https://example.com/feed", source_type="website"):
    response = await client.post(f"{API}/sources", json={"name": name, "url": url, "source_type": source_type})
    assert response.status_code == 201, response.text
    return response.json()


async def insert_document(sessions, *, workspace_id, source_id, title="Doc", content, url=None):
    async with sessions() as session:
        document = Document(
            workspace_id=workspace_id,
            source_id=source_id,
            canonical_url=url or f"https://example.com/{uuid4()}",
            title=title,
            content=content,
            excerpt=content[:200] if content else None,
            author=None,
            published_at=None,
            content_hash=hashlib.sha256((content or title).encode()).hexdigest(),
            fetched_at=datetime.now(UTC),
        )
        session.add(document)
        await session.commit()
        return document.id


# -- Deterministic chunking ----------------------------------------------------


def test_chunk_text_is_deterministic():
    text = "abcdefghij" * 20
    first = chunk_text(text, chunk_size=50, overlap=10)
    second = chunk_text(text, chunk_size=50, overlap=10)
    assert first == second
    assert len(first) > 1


def test_chunk_text_overlaps_between_consecutive_chunks():
    text = "0123456789" * 10
    chunks = chunk_text(text, chunk_size=30, overlap=10)
    assert chunks[0][-10:] == chunks[1][:10]


def test_chunk_text_handles_empty_and_short_text():
    assert chunk_text("") == []
    assert chunk_text("   ") == []
    assert chunk_text("hello") == ["hello"]


# -- Mock embeddings ------------------------------------------------------------


def test_mock_embedding_is_deterministic_and_normalized():
    provider = MockEmbeddingProvider(dimensions=16)
    vector = provider.embed_text("quarterly earnings")
    assert vector == provider.embed_text("quarterly earnings")
    assert len(vector) == 16
    assert abs(sum(value * value for value in vector) - 1) < 1e-6


# -- Indexing + duplicate protection --------------------------------------------


async def test_indexing_creates_chunks_then_skips_unchanged_document(client, sessions):
    source = await create_source(client)
    workspace_id = UUID((await client.get(f"{API}/me")).json()["workspace"]["id"])
    document_id = await insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]), content=DOC_A_CONTENT)

    first = (await client.post(f"{API}/documents/{document_id}/index")).json()
    assert first["skipped"] is False
    assert first["chunks_created"] >= 1

    second = (await client.post(f"{API}/documents/{document_id}/index")).json()
    assert second["skipped"] is True
    assert second["chunks_created"] == 0
    assert second["total_chunks"] == first["chunks_created"]

    forced = (await client.post(f"{API}/documents/{document_id}/index?force=true")).json()
    assert forced["skipped"] is False
    assert forced["chunks_created"] == first["chunks_created"]

    async with sessions() as session:
        from sqlalchemy import select

        rows = (await session.execute(select(DocumentChunk).where(DocumentChunk.document_id == document_id))).scalars().all()
        assert len(rows) == first["chunks_created"]


async def test_index_pending_processes_only_up_to_limit(client, sessions):
    source = await create_source(client)
    workspace_id = UUID((await client.get(f"{API}/me")).json()["workspace"]["id"])
    for index in range(3):
        await insert_document(
            sessions, workspace_id=workspace_id, source_id=UUID(source["id"]),
            title=f"Doc {index}", content=f"{DOC_A_CONTENT} Document number {index}.",
        )

    response = await client.post(f"{API}/search/index-pending", json={"limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["indexed"] == 2

    documents = (await client.get(f"{API}/documents")).json()["items"]
    unindexed = [document for document in documents if not document["indexed"]]
    assert len(unindexed) == 1

    second_pass = await client.post(f"{API}/search/index-pending", json={"limit": 5})
    assert second_pass.json()["indexed"] == 1


# -- Semantic search ranking, isolation, empty results --------------------------


async def test_search_ranks_exact_content_match_highest(client, sessions):
    """MockEmbeddingProvider hashes raw text (see providers/embeddings.py); it has no notion
    of meaning, so ranking quality can only be verified with an exact-match query, which
    tests the cosine-similarity retrieval pipeline itself rather than embedding quality."""
    source = await create_source(client)
    workspace_id = UUID((await client.get(f"{API}/me")).json()["workspace"]["id"])
    await insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]), title="Earnings", content=DOC_A_CONTENT)
    await insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]), title="Hiking", content=DOC_B_CONTENT)

    await client.post(f"{API}/search/index-pending", json={"limit": 10})

    response = await client.get(f"{API}/search", params={"q": DOC_A_CONTENT, "top_k": 2})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2
    assert results[0]["title"] == "Earnings"
    assert results[0]["similarity"] > results[1]["similarity"]
    assert results[0]["similarity"] > 0.99


async def test_search_returns_empty_when_workspace_has_no_indexed_chunks(client):
    response = await client.get(f"{API}/search", params={"q": "anything at all"})
    assert response.status_code == 200
    assert response.json()["results"] == []


async def test_search_is_workspace_isolated(client, sessions, other_workspace):
    async with sessions() as session:
        foreign_source = Source(
            workspace_id=other_workspace.id, name="Foreign", url="https://foreign.example/feed",
            source_type=SourceType.WEBSITE,
        )
        session.add(foreign_source)
        await session.flush()
        foreign_document = Document(
            workspace_id=other_workspace.id, source_id=foreign_source.id,
            canonical_url="https://foreign.example/a", title="Foreign doc", content=DOC_A_CONTENT,
            excerpt=None, author=None, published_at=None, content_hash="f" * 64, fetched_at=datetime.now(UTC),
        )
        session.add(foreign_document)
        await session.flush()
        provider = MockEmbeddingProvider(dimensions=32)
        for index, piece in enumerate(chunk_text(DOC_A_CONTENT)):
            session.add(DocumentChunk(
                workspace_id=other_workspace.id, document_id=foreign_document.id,
                chunk_index=index, content=piece, embedding=provider.embed_text(piece),
            ))
        await session.commit()

    response = await client.get(f"{API}/search", params={"q": DOC_A_CONTENT})
    assert response.json()["results"] == []


# -- Ask Vantage: grounded answer, citations, no-evidence ----------------------


async def test_ask_vantage_returns_grounded_answer_with_mapped_citations(client, sessions):
    source = await create_source(client)
    workspace_id = UUID((await client.get(f"{API}/me")).json()["workspace"]["id"])
    document_id = await insert_document(
        sessions, workspace_id=workspace_id, source_id=UUID(source["id"]), title="Earnings", content=DOC_A_CONTENT,
        url="https://example.com/earnings-report",
    )
    await client.post(f"{API}/documents/{document_id}/index")

    response = await client.post(f"{API}/ask", json={"question": "What were the quarterly earnings?"})
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is True
    assert body["provider"] == "mock"
    assert body["retrieved_count"] >= 1
    assert len(body["citations"]) == body["retrieved_count"]
    assert "Mock answer" in body["answer"]
    assert "[Source" in body["answer"]

    citation = body["citations"][0]
    assert citation["document_id"] == str(document_id)
    assert citation["url"] == "https://example.com/earnings-report"


async def test_ask_vantage_reports_insufficient_evidence_without_indexed_chunks(client, sessions):
    source = await create_source(client)
    workspace_id = UUID((await client.get(f"{API}/me")).json()["workspace"]["id"])
    await insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]), content=DOC_A_CONTENT)

    response = await client.post(f"{API}/ask", json={"question": "Anything about anything?"})
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is False
    assert body["citations"] == []
    assert body["retrieved_count"] == 0
    assert "not enough evidence" in body["answer"].lower()
