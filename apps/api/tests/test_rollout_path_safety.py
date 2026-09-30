"""Guards the reason GET /sources/management/view and GET /watchlists/bootstrap/initial use
two path segments instead of one.

A pre-Pass-3 Lambda already has GET /sources/{source_id} and GET /watchlists/{watchlist_id}
with UUID-typed path params. If the new optimized endpoints had instead been a single
segment (/sources/management, /watchlists/bootstrap), an OLD Lambda would match that URL
shape against its existing dynamic route and fail UUID validation with 422 -- not the 404
the frontend's rollout fallback specifically watches for. These tests prove that failure
mode against the single-segment shape on THIS (current) backend, where "management"/
"bootstrap" simply aren't valid UUIDs for the existing {source_id}/{watchlist_id} routes --
demonstrating why a genuinely new, unambiguous two-segment path was required, and guarding
against ever collapsing these back to one segment.
"""
API = "/api/v1"


async def test_single_segment_sources_path_would_hit_the_dynamic_uuid_route(client):
    """"management" is not a valid UUID for GET /sources/{source_id} -- proves the collision
    a single-segment /sources/management path would have caused against an old Lambda."""
    response = await client.get(f"{API}/sources/management")
    assert response.status_code == 422


async def test_single_segment_watchlists_path_would_hit_the_dynamic_uuid_route(client):
    response = await client.get(f"{API}/watchlists/bootstrap")
    assert response.status_code == 422


async def test_two_segment_sources_management_path_resolves_correctly(client):
    response = await client.get(f"{API}/sources/management/view")
    assert response.status_code == 200


async def test_two_segment_watchlists_bootstrap_path_resolves_correctly(client):
    response = await client.get(f"{API}/watchlists/bootstrap/initial")
    assert response.status_code == 200
