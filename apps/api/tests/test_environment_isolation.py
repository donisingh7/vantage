"""Regression test for the test-client Settings isolation set up in conftest.py.

A real local .env (e.g. one kept for production-config smoke testing) must never leak
into what a test observes or does -- not the provider mode, not any other setting, and
certainly no real network call to a real provider.
"""
import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

API = "/api/v1"


async def _insert_indexed_document(sessions, *, workspace_id, source_id):
    from app.models import Document

    content = "Quarterly results exceeded expectations across every reporting segment." * 3
    async with sessions() as session:
        document = Document(
            workspace_id=workspace_id, source_id=source_id,
            canonical_url=f"https://example.com/{uuid4()}", title="Earnings", content=content,
            excerpt=content[:200], author=None, published_at=None,
            content_hash=hashlib.sha256(content.encode()).hexdigest(), fetched_at=datetime.now(UTC),
        )
        session.add(document)
        await session.commit()
        return document.id


async def test_system_info_ignores_ambient_environment_overrides(client, monkeypatch):
    # Simulate exactly the kind of real, production-shaped ambient environment that
    # motivated this fix: a real provider selected, plus another unrelated setting changed
    # to an obviously non-default value.
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setenv("DEV_USER_EMAIL", "not-the-real-dev-user@example.com")

    info = await client.get(f"{API}/system/info")
    assert info.status_code == 200
    body = info.json()
    assert body["llm_provider"] == "mock"
    assert body["embedding_provider"] == "mock"

    # A second, unrelated setting confirms this isn't a narrow llm/embedding-only patch --
    # IsolatedTestSettings ignores the OS environment entirely, for every field.
    identity = await client.get(f"{API}/me")
    assert identity.status_code == 200
    assert identity.json()["user"]["email"] == "analyst@example.local"


async def test_ask_stays_mocked_despite_ambient_gemini_environment(client, sessions, monkeypatch):
    """No real provider call can happen even on a route that actually invokes LLMProvider.

    Indexes a real document first so /ask has evidence and must call LLMProvider.generate()
    to answer -- if the mock override weren't in effect, this would attempt a real Gemini
    call using the (fake, harmless) ambient key below and fail or hang.
    """
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key-and-never-used")

    source = await client.post(f"{API}/sources", json={"name": "Feed", "url": "https://example.com/feed", "source_type": "website"})
    assert source.status_code == 201, source.text
    workspace_id = UUID((await client.get(f"{API}/me")).json()["workspace"]["id"])
    document_id = await _insert_indexed_document(sessions, workspace_id=workspace_id, source_id=UUID(source.json()["id"]))
    indexed = await client.post(f"{API}/documents/{document_id}/index")
    assert indexed.status_code == 201, indexed.text

    response = await client.post(f"{API}/ask", json={"question": "How did quarterly results look?"})
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is True
    assert body["provider"] == "mock"
    assert "Mock answer" in body["answer"]
