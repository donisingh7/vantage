from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.models import AnalysisStatus, Document, IntelligenceSignal, Source, SourceType
from app.providers.llm import MockLLMProvider
from app.services.analysis_prompts import build_analysis_prompt
from app.services.analysis_schema import DocumentAnalysisResult

API = "/api/v1"

RELEVANT_CONTENT = (
    "Acme Ventures announced today that it has raised $50M in a Series B funding round "
    "led by new investors to expand its Cloud Infrastructure platform across new markets."
)
IRRELEVANT_CONTENT = "Just a short note."


async def create_source(client, name="Feed", url="https://example.com/feed", source_type="website"):
    response = await client.post(f"{API}/sources", json={"name": name, "url": url, "source_type": source_type})
    assert response.status_code == 201, response.text
    return response.json()


async def insert_document(sessions, *, workspace_id, source_id, title="Doc", content=RELEVANT_CONTENT, url=None):
    async with sessions() as session:
        from datetime import UTC, datetime
        import hashlib

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


# -- Structured schema validation --------------------------------------------


def test_document_analysis_result_rejects_out_of_range_scores():
    base = dict(
        relevant=True, relevance_score=0.5, signal_type="product", title="T", executive_summary="S",
        importance_score=0.5, sentiment="neutral", key_entities=[], key_points=[], business_impact="B",
        confidence_score=0.5, evidence_excerpt="E",
    )
    DocumentAnalysisResult.model_validate(base)  # valid, should not raise
    with pytest.raises(ValidationError):
        DocumentAnalysisResult.model_validate({**base, "relevance_score": 1.5})
    with pytest.raises(ValidationError):
        DocumentAnalysisResult.model_validate({**base, "signal_type": "not-a-real-type"})


# -- Deterministic mock analysis ----------------------------------------------


async def test_mock_analysis_is_deterministic_for_identical_input():
    provider = MockLLMProvider()
    prompt = build_analysis_prompt(
        document_title="Acme raises funding", document_content=RELEVANT_CONTENT,
        source_name="Feed", source_url="https://example.com",
    )
    first = await provider.structured_generate(prompt, DocumentAnalysisResult)
    second = await provider.structured_generate(prompt, DocumentAnalysisResult)
    assert first.model_dump() == second.model_dump()


async def test_mock_analysis_reflects_document_title_and_content():
    provider = MockLLMProvider()
    prompt_a = build_analysis_prompt(
        document_title="Doc A", document_content=RELEVANT_CONTENT, source_name="Feed", source_url="https://x"
    )
    prompt_b = build_analysis_prompt(
        document_title="Doc B", document_content="A totally different announcement about a leadership change.",
        source_name="Feed", source_url="https://x",
    )
    result_a = await provider.structured_generate(prompt_a, DocumentAnalysisResult)
    result_b = await provider.structured_generate(prompt_b, DocumentAnalysisResult)
    assert result_a.title != result_b.title
    assert "Doc A" in result_a.title
    assert result_a.evidence_excerpt.startswith("Acme Ventures")


async def test_mock_marks_short_content_as_irrelevant():
    provider = MockLLMProvider()
    prompt = build_analysis_prompt(
        document_title="Note", document_content=IRRELEVANT_CONTENT, source_name="Feed", source_url="https://x"
    )
    result = await provider.structured_generate(prompt, DocumentAnalysisResult)
    assert result.relevant is False


# -- Relevant / irrelevant analysis through the API ---------------------------


async def test_analyzing_relevant_document_creates_completed_signal(client, sessions):
    source = await create_source(client)
    workspace_id = UUID((await client.get(f"{API}/me")).json()["workspace"]["id"])
    document_id = await insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))

    response = await client.post(f"{API}/documents/{document_id}/analyze")
    assert response.status_code == 201, response.text
    signal = response.json()
    assert signal["analysis_status"] == "completed"
    assert signal["signal_type"] == "funding"
    assert signal["importance_score"] > 0
    assert signal["company_id"] is None or isinstance(signal["company_id"], str)

    listed = await client.get(f"{API}/intelligence/signals")
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == signal["id"]


async def test_analyzing_irrelevant_document_does_not_appear_in_signal_listing(client, sessions):
    source = await create_source(client)
    workspace_id = UUID((await client.get(f"{API}/me")).json()["workspace"]["id"])
    document_id = await insert_document(
        sessions, workspace_id=workspace_id, source_id=UUID(source["id"]), content=IRRELEVANT_CONTENT
    )

    response = await client.post(f"{API}/documents/{document_id}/analyze")
    assert response.status_code == 201
    assert response.json()["analysis_status"] == "irrelevant"

    listed = await client.get(f"{API}/intelligence/signals")
    assert listed.json()["total"] == 0


# -- Duplicate analysis protection --------------------------------------------


async def test_duplicate_analysis_is_protected_unless_forced(client, sessions):
    source = await create_source(client)
    workspace_id = UUID((await client.get(f"{API}/me")).json()["workspace"]["id"])
    document_id = await insert_document(sessions, workspace_id=workspace_id, source_id=UUID(source["id"]))

    first = (await client.post(f"{API}/documents/{document_id}/analyze")).json()
    second = (await client.post(f"{API}/documents/{document_id}/analyze")).json()
    assert first["id"] == second["id"]

    async with sessions() as session:
        from sqlalchemy import select

        rows = (await session.execute(select(IntelligenceSignal))).scalars().all()
        assert len(rows) == 1

    forced = (await client.post(f"{API}/documents/{document_id}/analyze?force=true")).json()
    assert forced["id"] == first["id"]

    async with sessions() as session:
        from sqlalchemy import select

        rows = (await session.execute(select(IntelligenceSignal))).scalars().all()
        assert len(rows) == 1


# -- Workspace isolation -------------------------------------------------------


async def test_intelligence_signal_respects_workspace_isolation(client, sessions, other_workspace):
    async with sessions() as session:
        from datetime import UTC, datetime

        foreign_source = Source(
            workspace_id=other_workspace.id, name="Foreign", url="https://foreign.example/feed",
            source_type=SourceType.WEBSITE,
        )
        session.add(foreign_source)
        await session.flush()
        foreign_document = Document(
            workspace_id=other_workspace.id, source_id=foreign_source.id,
            canonical_url="https://foreign.example/a", title="Foreign doc", content=RELEVANT_CONTENT,
            excerpt=None, author=None, published_at=None, content_hash="x" * 64, fetched_at=datetime.now(UTC),
        )
        session.add(foreign_document)
        await session.flush()
        foreign_signal = IntelligenceSignal(
            workspace_id=other_workspace.id, document_id=foreign_document.id,
            analysis_status=AnalysisStatus.COMPLETED, analyzed_at=datetime.now(UTC),
            signal_type="funding", title="Foreign signal", relevance_score=0.9, importance_score=0.9,
            key_entities=[], key_points=[], confidence_score=0.9,
        )
        session.add(foreign_signal)
        await session.commit()
        foreign_signal_id = foreign_signal.id
        foreign_document_id = foreign_document.id

    assert (await client.get(f"{API}/intelligence/signals/{foreign_signal_id}")).status_code == 404
    assert (await client.post(f"{API}/documents/{foreign_document_id}/analyze")).status_code == 404
    assert (await client.get(f"{API}/intelligence/signals")).json()["total"] == 0


# -- Signal filtering -----------------------------------------------------------


async def test_signal_filtering_by_type_importance_and_company(client, sessions):
    company = (await client.post(f"{API}/companies", json={"name": "Acme Ventures"})).json()
    topic = (await client.post(f"{API}/topics", json={"name": "Cloud Infrastructure"})).json()
    source = await create_source(client)
    workspace_id = UUID((await client.get(f"{API}/me")).json()["workspace"]["id"])

    funding_doc = await insert_document(
        sessions, workspace_id=workspace_id, source_id=UUID(source["id"]),
        title="Funding news", content=RELEVANT_CONTENT,
    )
    leadership_doc = await insert_document(
        sessions, workspace_id=workspace_id, source_id=UUID(source["id"]),
        title="Leadership change",
        content="The company today announced it will appoint a new chief executive officer next quarter.",
    )

    funding_signal = (await client.post(f"{API}/documents/{funding_doc}/analyze")).json()
    leadership_signal = (await client.post(f"{API}/documents/{leadership_doc}/analyze")).json()
    assert funding_signal["signal_type"] == "funding"
    assert leadership_signal["signal_type"] == "leadership"
    assert funding_signal["company_id"] == company["id"]
    assert funding_signal["topic_id"] == topic["id"]

    by_type = await client.get(f"{API}/intelligence/signals?signal_type=funding")
    assert [item["id"] for item in by_type.json()["items"]] == [funding_signal["id"]]

    by_company = await client.get(f"{API}/intelligence/signals?company_id={company['id']}")
    assert [item["id"] for item in by_company.json()["items"]] == [funding_signal["id"]]

    by_topic = await client.get(f"{API}/intelligence/signals?topic_id={topic['id']}")
    assert [item["id"] for item in by_topic.json()["items"]] == [funding_signal["id"]]

    high_importance = max(funding_signal["importance_score"], leadership_signal["importance_score"])
    by_importance = await client.get(f"{API}/intelligence/signals?min_importance={high_importance}")
    assert len(by_importance.json()["items"]) >= 1
    assert (await client.get(f"{API}/intelligence/signals?min_importance=1.01")).status_code == 422

    by_sentiment = await client.get(f"{API}/intelligence/signals?sentiment={funding_signal['sentiment']}")
    assert funding_signal["id"] in [item["id"] for item in by_sentiment.json()["items"]]
    assert (await client.get(f"{API}/intelligence/signals?sentiment=not-a-real-sentiment")).status_code == 422


# -- analyze-pending bounded processing ---------------------------------------


async def test_analyze_pending_processes_only_up_to_limit(client, sessions):
    source = await create_source(client)
    workspace_id = UUID((await client.get(f"{API}/me")).json()["workspace"]["id"])
    for index in range(3):
        await insert_document(
            sessions, workspace_id=workspace_id, source_id=UUID(source["id"]),
            title=f"Doc {index}", content=f"{RELEVANT_CONTENT} Document number {index}.",
        )

    response = await client.post(f"{API}/intelligence/analyze-pending", json={"limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["analyzed"] == 2
    assert len(body["signals"]) == 2

    documents = (await client.get(f"{API}/documents")).json()["items"]
    unanalyzed = [document for document in documents if document["analysis_status"] is None]
    assert len(unanalyzed) == 1

    second_pass = await client.post(f"{API}/intelligence/analyze-pending", json={"limit": 5})
    assert second_pass.json()["analyzed"] == 1
