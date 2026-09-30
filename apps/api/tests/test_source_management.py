"""Tests for GET /api/v1/sources/management/view -- one request replacing GET /sources +
GET /ingestion/jobs (full job history) for the Sources management page.

The path is deliberately two segments (see the route's docstring): a single-segment
/sources/management would collide with the pre-Pass-3 GET /sources/{source_id} route and
fail UUID validation with a 422 instead of a genuine 404, breaking the frontend's
404-only rollout fallback.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.models import CrawlJob, CrawlJobStatus, SourceType

API = "/api/v1"


async def _workspace_id(client) -> UUID:
    return UUID((await client.get(f"{API}/me")).json()["workspace"]["id"])


async def _create_source(client, name="Feed", url="https://example.com/feed"):
    response = await client.post(f"{API}/sources", json={"name": name, "url": url, "source_type": "website"})
    assert response.status_code == 201, response.text
    return response.json()


async def _insert_job(sessions, *, workspace_id, source_id, created_at, status=CrawlJobStatus.COMPLETED, error_message=None):
    async with sessions() as session:
        job = CrawlJob(
            workspace_id=workspace_id, source_id=source_id, status=status,
            documents_found=1, documents_created=1, documents_skipped=0,
            pages_discovered=1, pages_failed=0, error_message=error_message,
        )
        job.created_at = created_at
        session.add(job)
        await session.commit()
        return job.id


async def test_empty_workspace_returns_no_items(client):
    response = await client.get(f"{API}/sources/management/view")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_source_with_no_jobs_has_null_latest_job(client):
    await _create_source(client)
    response = await client.get(f"{API}/sources/management/view")
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["latest_job"] is None
    assert items[0]["watchlist_count"] == 0


async def test_newer_job_is_selected_over_older_job(client, sessions):
    workspace_id = await _workspace_id(client)
    source = await _create_source(client)
    now = datetime.now(UTC)
    older_id = await _insert_job(
        sessions, workspace_id=workspace_id, source_id=UUID(source["id"]),
        created_at=now - timedelta(days=1), status=CrawlJobStatus.COMPLETED,
    )
    newer_id = await _insert_job(
        sessions, workspace_id=workspace_id, source_id=UUID(source["id"]),
        created_at=now, status=CrawlJobStatus.FAILED, error_message="timed out",
    )

    response = await client.get(f"{API}/sources/management/view")
    items = response.json()["items"]
    assert len(items) == 1
    latest_job = items[0]["latest_job"]
    assert latest_job is not None
    assert latest_job["id"] == str(newer_id)
    assert latest_job["id"] != str(older_id)
    assert latest_job["status"] == "failed"
    assert latest_job["error_message"] == "timed out"


async def test_response_does_not_leak_full_job_history(client, sessions):
    """The management read must expose only each source's own latest job -- not every
    CrawlJob row -- so the browser never receives full ingestion history."""
    workspace_id = await _workspace_id(client)
    source = await _create_source(client)
    now = datetime.now(UTC)
    for offset in range(5):
        await _insert_job(
            sessions, workspace_id=workspace_id, source_id=UUID(source["id"]), created_at=now - timedelta(hours=offset)
        )

    response = await client.get(f"{API}/sources/management/view")
    body = response.json()
    assert len(body["items"]) == 1  # one row per source, not one row per job
    assert "jobs" not in body["items"][0]  # no embedded job-history array


async def test_scheduler_enabled_reflects_settings(client):
    response = await client.get(f"{API}/sources/management/view")
    # IsolatedTestSettings() reads only field defaults; Settings.enable_scheduler defaults False,
    # matching production's ENABLE_SCHEDULER=false.
    assert response.json()["scheduler_enabled"] is False


async def test_watchlist_count_reflects_membership(client):
    source = await _create_source(client)
    watchlist = (await client.post(f"{API}/watchlists", json={"name": "W1"})).json()
    await client.put(f"{API}/watchlists/{watchlist['id']}/sources/{source['id']}")

    response = await client.get(f"{API}/sources/management/view")
    items = response.json()["items"]
    assert items[0]["watchlist_count"] == 1


async def test_source_management_never_leaks_another_workspaces_data(client, sessions, other_workspace):
    async with sessions() as session:
        from app.models import Source

        foreign_source = Source(
            workspace_id=other_workspace.id, name="Foreign", url="https://foreign.example/feed",
            source_type=SourceType.WEBSITE,
        )
        session.add(foreign_source)
        await session.flush()
        session.add(CrawlJob(
            workspace_id=other_workspace.id, source_id=foreign_source.id, status=CrawlJobStatus.COMPLETED,
            documents_found=1, documents_created=1, documents_skipped=0, pages_discovered=1, pages_failed=0,
        ))
        await session.commit()

    response = await client.get(f"{API}/sources/management/view")
    assert response.status_code == 200
    assert response.json()["items"] == []
