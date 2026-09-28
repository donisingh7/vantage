# Architecture

## Current Architecture

Vantage is a small monorepo with a separately deployable web application and API. PostgreSQL is the relational system of record. The PostgreSQL image used for development includes pgvector so future vector columns and indexes can be introduced without replacing the datastore.

```text
Browser
  | Next.js App Router and shared API client
  v
FastAPI /api/v1
  | async SQLAlchemy repositories
  v
PostgreSQL + pgvector extension
```

## Implemented Now

- `apps/web` provides the responsive product shell, overview, development entry route, and workspace-area placeholders. It calls API services through `src/lib/api.ts`, not ad hoc component fetches.
- `apps/api` owns versioned routing, Pydantic settings/contracts, centralized error envelopes, CORS and request middleware, development identity resolution, providers, repositories, and persistence models.
- Async SQLAlchemy sessions use PostgreSQL via `asyncpg`. Alembic owns schema changes. The initial migration enables pgvector and creates the first workspace-aware entities.
- User, Workspace, WorkspaceMember, Watchlist, Company, Topic, and Source establish UUID keys and workspace foreign-key scoping. Membership roles are owner, admin, member, and viewer. Authorization enforcement is not implemented yet.
- `CurrentUserProvider` isolates the deterministic development identity from route code. A future JWT/OIDC provider can replace it at the dependency boundary.
- `LLMProvider` and `EmbeddingProvider` describe service contracts. Mock implementations are deterministic and avoid external calls. No real provider adapter is implemented in this phase.
- Structured JSON request logs record method, path, response status, duration, and request ID. Raw exception text and request payloads are not logged. OpenTelemetry and metrics are extension points, not current dependencies.

## Frontend and Backend Boundaries

The frontend owns navigation, presentation, and graceful API-client failures. Backend routes own service boundaries and do not embed business operations in React components. The current API has only system endpoints; placeholder workspace pages do not imply that corresponding CRUD or intelligence APIs exist.

## Database and Workspace Tenancy

Business entities carry a non-null `workspace_id` foreign key with cascade deletion and an index. Access checks must later scope repository queries through a workspace membership check; possession of an entity UUID alone is not an authorization rule. Workspace membership is unique per user/workspace pair. Full RBAC, row-level security, and workspace provisioning flows are deferred.

The vector extension is enabled in the migration. No vector column, embedding persistence, or semantic query is implemented in Part 1. Embedding dimensions are configurable so a future model-specific vector schema can make its dimensionality explicit.

## Provider Abstractions

Routes and repositories do not call model APIs. Future application services should depend on provider protocols and receive configured providers through dependencies or service construction. Mock implementations are the only runnable implementations today. Azure endpoint, key, and deployment settings are optional while the configured providers are mock; selecting Azure settings validates required endpoint and key values, but does not yet enable real Azure calls.

## Observability and Errors

Each request receives a validated or generated correlation ID returned in `X-Request-ID`. Errors follow `{ "error": { "code", "message", "request_id" } }`; internal exceptions return a generic message. Logs omit headers, request bodies, exception text, and provider credentials. Security response headers and a configurable content-length request-size guard are applied in middleware.

## Planned: Ingestion

Later ingestion can add source definitions, crawl scheduling, fetch adapters, normalized documents, deduplication, and analysis as independent service boundaries. Persisted `CrawlJob`, `Document`, `IntelligenceSignal`, and `Analysis` models do not exist yet. Production crawling and scheduled ingestion are explicitly out of scope here.

## Planned: Semantic Search

Future documents can be chunked, embedded through `EmbeddingProvider`, and stored with a pgvector column and matching-dimension index. Retrieval should remain workspace-filtered before ranking, then provide source-backed citations. Neither vector persistence nor semantic search is currently implemented.

## Planned: Workers and Jobs

No Redis service or queue is included in Part 1. Once ingestion has durable asynchronous workloads, job delivery, retry policy, idempotency, and operations can be chosen from observed requirements. `REDIS_URL` is an optional configuration placeholder only; it is unused.
