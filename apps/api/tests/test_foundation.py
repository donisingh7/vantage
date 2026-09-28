from uuid import UUID

import pytest
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.models import Company, User, Workspace
from app.providers.embeddings import MockEmbeddingProvider
from app.providers.llm import MockLLMProvider

API = "/api/v1"


async def create_company(client, *, name="Acme", domain="acme.example"):
    response = await client.post(
        f"{API}/companies", json={"name": name, "domain": domain, "description": "Sample"}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_topic(client, name="AI policy"):
    response = await client.post(f"{API}/topics", json={"name": name, "description": "Sample topic"})
    assert response.status_code == 201, response.text
    return response.json()


async def create_source(client, name="Research feed", url="https://example.com/feed"):
    response = await client.post(
        f"{API}/sources", json={"name": name, "url": url, "source_type": "rss"}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_watchlist(client, name="Priority market"):
    response = await client.post(f"{API}/watchlists", json={"name": name, "description": "Track it"})
    assert response.status_code == 201, response.text
    return response.json()


async def test_health_and_readiness(client):
    health = await client.get("/health")
    ready = await client.get("/ready")
    assert health.status_code == 200 and health.json() == {"status": "ok"}
    assert ready.status_code == 200 and ready.json() == {"status": "ready"}


async def test_development_identity_creates_user_and_workspace(client, sessions):
    response = await client.get(f"{API}/me")
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "analyst@example.local"
    assert body["workspace"]["slug"] == "development"
    assert body["role"] == "owner"
    async with sessions() as session:
        assert await session.get(User, UUID(body["user"]["id"])) is not None
        assert await session.get(Workspace, UUID(body["workspace"]["id"])) is not None


async def test_workspace_list_and_membership_isolation(client, other_workspace):
    current = (await client.get(f"{API}/me")).json()
    workspace_id = current["workspace"]["id"]
    visible = await client.get(f"{API}/workspaces")
    assert [entry["id"] for entry in visible.json()] == [workspace_id]
    assert (await client.get(f"{API}/workspaces/{workspace_id}")).status_code == 200
    assert (await client.get(f"{API}/workspaces/{other_workspace.id}")).status_code == 404


async def test_company_crud_normalization_duplicates_and_isolation(client, sessions, other_workspace):
    company = await create_company(client, domain="HTTPS://WWW.Acme.Example/about")
    assert company["domain"] == "acme.example"
    listed = await client.get(f"{API}/companies?search=ACME")
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == company["id"]
    assert (await client.patch(f"{API}/companies/{company['id']}", json={"name": "Acme Group"})).json()["name"] == "Acme Group"
    duplicate = await client.post(f"{API}/companies", json={"name": "Copy", "domain": "acme.example"})
    assert duplicate.status_code == 409
    async with sessions() as session:
        foreign = Company(workspace_id=other_workspace.id, name="Secret Co", domain="secret.example")
        session.add(foreign)
        await session.commit()
        foreign_id = foreign.id
    assert (await client.get(f"{API}/companies/{foreign_id}")).status_code == 404
    assert (await client.patch(f"{API}/companies/{foreign_id}", json={"name": "Leaked"})).status_code == 404
    assert (await client.delete(f"{API}/companies/{foreign_id}")).status_code == 404
    assert (await client.delete(f"{API}/companies/{company['id']}")).status_code == 204
    assert (await client.get(f"{API}/companies/{company['id']}" )).status_code == 404


async def test_topic_crud_and_duplicate_handling(client):
    topic = await create_topic(client)
    assert (await client.get(f"{API}/topics/{topic['id']}")).status_code == 200
    assert (await client.patch(f"{API}/topics/{topic['id']}", json={"name": "AI governance"})).json()["name"] == "AI governance"
    assert (await client.post(f"{API}/topics", json={"name": "AI governance"})).status_code == 409
    assert (await client.delete(f"{API}/topics/{topic['id']}")).status_code == 204


async def test_source_crud_url_validation_and_duplicate_handling(client):
    source = await create_source(client)
    assert source["source_type"] == "rss"
    invalid = await client.post(f"{API}/sources", json={"name": "Unsafe", "url": "javascript:alert(1)", "source_type": "other"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert (await client.post(f"{API}/sources", json={"name": "Duplicate", "url": source["url"], "source_type": "website"})).status_code == 409
    assert (await client.patch(f"{API}/sources/{source['id']}", json={"is_active": False})).json()["is_active"] is False
    assert (await client.delete(f"{API}/sources/{source['id']}")).status_code == 204


async def test_watchlist_crud_memberships_and_activation(client):
    company = await create_company(client)
    topic = await create_topic(client)
    source = await create_source(client)
    watchlist = await create_watchlist(client)
    watchlist_id = watchlist["id"]

    for kind, entity in (("companies", company), ("topics", topic), ("sources", source)):
        response = await client.put(f"{API}/watchlists/{watchlist_id}/{kind}/{entity['id']}")
        assert response.status_code == 200, response.text
        assert response.json()["counts"][kind] == 1

    detail = (await client.get(f"{API}/watchlists/{watchlist_id}")).json()
    assert [item["id"] for item in detail["companies"]] == [company["id"]]
    assert detail["companies"][0]["watchlist_count"] == 1
    assert detail["topics"][0]["watchlist_count"] == 1
    assert detail["sources"][0]["watchlist_count"] == 1
    assert (await client.get(f"{API}/workspace/summary")).json() == {
        "watchlists": 1,
        "companies": 1,
        "topics": 1,
        "sources": 1,
        "active_watchlists": 1,
        "active_sources": 1,
    }

    removed = await client.delete(f"{API}/watchlists/{watchlist_id}/topics/{topic['id']}")
    assert removed.json()["counts"]["topics"] == 0
    updated = await client.patch(f"{API}/watchlists/{watchlist_id}", json={"is_active": False, "name": "Paused market"})
    assert updated.json()["is_active"] is False
    assert updated.json()["name"] == "Paused market"
    assert (await client.get(f"{API}/workspace/summary")).json()["active_watchlists"] == 0
    assert (await client.delete(f"{API}/watchlists/{watchlist_id}")).status_code == 204
    assert (await client.get(f"{API}/watchlists/{watchlist_id}")).status_code == 404


async def test_watchlist_cannot_attach_foreign_workspace_entity(client, sessions, other_workspace):
    watchlist = await create_watchlist(client)
    async with sessions() as session:
        company = Company(workspace_id=other_workspace.id, name="Foreign", domain="foreign.example")
        session.add(company)
        await session.commit()
        company_id = company.id
    response = await client.put(f"{API}/watchlists/{watchlist['id']}/companies/{company_id}")
    assert response.status_code == 404


async def test_malformed_uuid_has_safe_validation_response(client):
    response = await client.get(f"{API}/companies/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("failure", [SQLAlchemyError("private database detail"), OSError("private socket detail")])
async def test_readiness_returns_safe_error_when_database_fails(client, failure):
    from app.db.session import get_db_session

    async def broken_session():
        class BrokenSession:
            async def execute(self, statement):
                raise failure

        yield BrokenSession()

    from app.main import app

    app.dependency_overrides[get_db_session] = broken_session
    response = await client.get("/ready", headers={"X-Request-ID": "readiness-check"})
    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "service_unavailable",
        "message": "Service is not ready",
        "request_id": "readiness-check",
    }


def test_mock_provider_configuration_needs_no_cloud_credentials():
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "mock"
    assert settings.embedding_provider == "mock"
    assert settings.database_url.startswith("sqlite")


async def test_mock_llm_is_repeatable_and_supports_structured_output():
    class Summary(BaseModel):
        summary: str
        highlights: list[str]
        confidence: float

    provider = MockLLMProvider()
    first = await provider.generate("Assess Acme")
    assert first == await provider.generate("Assess Acme")
    assert "No external model was called" in first
    structured = await provider.structured_generate("summarize", Summary)
    assert structured.summary == "Mock summary"
    assert structured.highlights == []
    assert structured.confidence == 0.0


def test_azure_provider_configuration_requires_credentials_only_when_selected():
    with pytest.raises(ValueError, match="AZURE_OPENAI_API_KEY"):
        Settings(_env_file=None, llm_provider="azure_openai")


def test_mock_embeddings_are_repeatable_normalized_and_batchable():
    provider = MockEmbeddingProvider(dimensions=16)
    embedding = provider.embed_text("market update")
    assert embedding == provider.embed_text("market update")
    assert len(embedding) == 16
    assert abs(sum(value * value for value in embedding) - 1) < 1e-6
    assert provider.embed_documents(["market update"]) == [embedding]


async def test_api_error_shape_does_not_expose_framework_details(client):
    response = await client.get("/missing-route", headers={"X-Request-ID": "error-check"})
    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "not_found",
        "message": "Not Found",
        "request_id": "error-check",
    }


async def test_request_body_limit_returns_safe_error(client):
    response = await client.post(
        "/health", content=b"x" * (1_048_576 + 1), headers={"X-Request-ID": "size-check"}
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
    assert response.json()["error"]["request_id"] == "size-check"
