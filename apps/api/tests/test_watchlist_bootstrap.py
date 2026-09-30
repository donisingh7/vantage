"""Tests for GET /api/v1/watchlists/bootstrap/initial -- one request replacing
Promise.all(GET /watchlists, GET /companies, GET /topics, GET /sources) plus a separate
GET /watchlists/{id} for the initially-selected watchlist.

The path is deliberately two segments (see the route's docstring): a single-segment
/watchlists/bootstrap would collide with the pre-Pass-3 GET /watchlists/{watchlist_id}
route and fail UUID validation with a 422 instead of a genuine 404, breaking the
frontend's 404-only rollout fallback.
"""
API = "/api/v1"


async def test_empty_workspace_returns_empty_lists_and_null_detail(client):
    response = await client.get(f"{API}/watchlists/bootstrap/initial")
    assert response.status_code == 200
    body = response.json()
    assert body["watchlists"] == []
    assert body["companies"] == []
    assert body["topics"] == []
    assert body["sources"] == []
    assert body["initial_detail"] is None


async def test_catalogs_return_narrow_projections(client):
    await client.post(f"{API}/companies", json={"name": "Acme", "domain": "acme.com", "description": "Long text"})
    await client.post(f"{API}/topics", json={"name": "Cloud"})
    await client.post(f"{API}/sources", json={"name": "Feed", "url": "https://example.com/feed", "source_type": "website"})

    response = await client.get(f"{API}/watchlists/bootstrap/initial")
    body = response.json()

    assert body["companies"] == [{"id": body["companies"][0]["id"], "name": "Acme"}]
    assert set(body["companies"][0].keys()) == {"id", "name"}
    assert set(body["topics"][0].keys()) == {"id", "name"}
    assert set(body["sources"][0].keys()) == {"id", "name", "url"}


async def test_initial_detail_matches_the_first_alphabetical_watchlist(client):
    await client.post(f"{API}/watchlists", json={"name": "Zebra watchlist"})
    alpha = (await client.post(f"{API}/watchlists", json={"name": "Alpha watchlist"})).json()

    response = await client.get(f"{API}/watchlists/bootstrap/initial")
    body = response.json()
    assert body["watchlists"][0]["name"] == "Alpha watchlist"
    assert body["initial_detail"]["id"] == alpha["id"]
    assert body["initial_detail"]["name"] == "Alpha watchlist"


async def test_initial_detail_reflects_membership_counts(client):
    watchlist = (await client.post(f"{API}/watchlists", json={"name": "W1"})).json()
    company = (await client.post(f"{API}/companies", json={"name": "Acme"})).json()
    topic = (await client.post(f"{API}/topics", json={"name": "Cloud"})).json()
    await client.put(f"{API}/watchlists/{watchlist['id']}/companies/{company['id']}")
    await client.put(f"{API}/watchlists/{watchlist['id']}/topics/{topic['id']}")

    response = await client.get(f"{API}/watchlists/bootstrap/initial")
    detail = response.json()["initial_detail"]
    assert detail["counts"] == {"companies": 1, "topics": 1, "sources": 0}
    assert [item["name"] for item in detail["companies"]] == ["Acme"]
    assert detail["companies"][0]["watchlist_count"] == 1
    assert [item["name"] for item in detail["topics"]] == ["Cloud"]


async def test_watchlist_bootstrap_never_leaks_another_workspaces_data(client, sessions, other_workspace):
    async with sessions() as session:
        from app.models import Company, Watchlist

        foreign_company = Company(workspace_id=other_workspace.id, name="Foreign Co")
        session.add(foreign_company)
        foreign_watchlist = Watchlist(workspace_id=other_workspace.id, name="Foreign Watchlist")
        session.add(foreign_watchlist)
        await session.commit()

    response = await client.get(f"{API}/watchlists/bootstrap/initial")
    body = response.json()
    assert body["watchlists"] == []
    assert body["companies"] == []
    assert body["initial_detail"] is None
