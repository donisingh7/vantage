# Architecture

## Current Architecture

Vantage is a small monorepo: a Next.js web app and a FastAPI API, talking over HTTP. SQLite is the current system of record (see [Data Store](../README.md#data-store) in the README for the PostgreSQL/pgvector path). There is no message broker, no worker process, and no deployment infrastructure in this repository.

```text
Browser
  | Next.js App Router + shared API client (src/lib/api.ts)
  v
FastAPI /api/v1
  | async SQLAlchemy services, all workspace-scoped
  v
SQLite (sqlite+aiosqlite) -- PostgreSQL-compatible DATABASE_URL, not yet PostgreSQL-specific
```

## Request Flow: Source to Answer

```text
Source (configured URL, website or RSS)
  |  IngestionService: fetch -> extract -> normalize URL -> dedupe -> persist Document
  |  website sources also discover a bounded set of same-domain links (depth 1)
  v
Document (raw collected content)
  |  IntelligenceAnalysisService: build a grounded prompt -> LLMProvider.structured_generate
  |  -> validate against DocumentAnalysisResult -> discard if irrelevant -> persist
  v
IntelligenceSignal (typed, scored, deterministically linked to a Company/Topic if named in it)
  |  DocumentIndexingService: chunk_text -> EmbeddingProvider.embed_documents -> persist
  v
DocumentChunk (content + embedding, JSON column)
  |  SemanticSearchService: embed the query -> cosine similarity over workspace chunks -> top-k
  v
AskVantageService: retrieval -> grounded prompt -> LLMProvider.generate -> answer + citations
```

Nothing in this chain runs automatically end to end: ingestion, analysis, and indexing are each triggered manually (per-item or a bounded "pending" batch) or, for ingestion only, by an optional in-process scheduler. This is a deliberate simplification, not an oversight -- see `services/scheduler.py`.

## Implemented Now

- `apps/web` is the full executive UI: dashboard (real counts, priority signals, signal/sentiment distributions, recent ingestion activity, recently analyzed intelligence), an intelligence timeline with filters, company/topic intelligence detail views, and Ask Vantage. It calls the API only through `src/lib/api.ts`, never ad hoc component fetches.
- `apps/api` owns versioned routing, Pydantic settings/contracts, centralized error envelopes, CORS and request middleware, development identity resolution, providers, and persistence models.
- `User`, `Workspace`, `WorkspaceMember`, `Watchlist`, `Company`, `Topic`, `Source`, `CrawlJob`, `Document`, `DocumentChunk`, and `IntelligenceSignal` all carry a workspace-scoping foreign key; every repository/service query filters by `workspace_id`, so an entity UUID alone never grants cross-workspace access. Membership roles are owner, admin, member, and viewer; full RBAC/row-level enforcement beyond that is deferred.
- `CurrentUserProvider` isolates the deterministic development identity from route code, so a real JWT/OIDC provider can replace it at the dependency boundary later without touching routes.

## Provider Abstractions

`LLMProvider` (`generate`, `structured_generate`) and `EmbeddingProvider` (`embed_text`, `embed_documents`) are the only two interfaces the rest of the codebase depends on. `MockLLMProvider` and `MockEmbeddingProvider` are deterministic and make no network calls; `AzureOpenAILLMProvider` and `AzureOpenAIEmbeddingProvider` implement the same interfaces against real Azure OpenAI (see the README's [Provider Modes](../README.md#provider-modes)). `EmbeddingProvider` is intentionally synchronous (not async) -- the real adapter uses the synchronous OpenAI SDK client to match it exactly, rather than changing the interface everywhere embeddings are used, since embedding calls are infrequent relative to request handling. Real-provider failures are wrapped into a `provider_error` (502) with a generic message; the raw SDK exception is never echoed back to the client.

`app/api/deps.py` is the single place that decides mock vs. real per request, from `Settings.llm_provider` / `Settings.embedding_provider`. Nothing else in a route or service branches on provider mode.

## Prompt Safety

Crawled and retrieved content is treated as untrusted data everywhere it reaches an `LLMProvider` call: `services/analysis_prompts.py` and `services/ask_prompts.py` both wrap it in explicit "this is data, not instructions" framing, cap its length, and instruct the model to answer only from what's supplied, say so explicitly when evidence is insufficient, and (for Ask Vantage) cite sources by number. Citations returned by `POST /ask` are always built server-side from the chunks that were actually retrieved -- the model's own text is never parsed for a source list.

## Concurrency and Scheduling

`InProcessKeyGuard` (`services/concurrency.py`) is a small in-process, per-key guard used identically by `IngestionService.run`, `IntelligenceAnalysisService.analyze_document`, and `DocumentIndexingService.index_document`: a second concurrent call for the same source/document gets a `409 conflict` instead of racing the first into a duplicate-row constraint violation. It is explicitly not a distributed lock -- fine for this single-process design, not sufficient if this ever runs as multiple processes/replicas.

Scheduling (`services/scheduler.py`) is a single `AsyncIOScheduler` (APScheduler) tick that finds active sources whose configured interval has elapsed and reuses the same `IngestionService.run` (and its guard). It is off by default (`ENABLE_SCHEDULER=false`) and `should_enable_scheduler()` additionally forces it off whenever `APP_ENV=test`, regardless of that flag -- a unit-tested guarantee, not just a byproduct of the test client never invoking FastAPI's lifespan.

## Source and Link Safety

`services/url_safety.py` rejects non-http(s) schemes, `localhost`/`.local` hosts, and loopback/private/link-local/reserved/multicast IP literals. It's applied twice: once at `Source` creation (schema-level validator, so an unsafe URL is rejected at the point of entry with a normal 422) and again on every outbound fetch, including each discovered link during website crawling (so a source that later starts redirecting somewhere unsafe still can't be followed). This is a practical, bounded guard, not a full SSRF-prevention framework -- it does not resolve DNS to check where a normal hostname actually points.

Website link discovery (`services/link_discovery.py`) is bounded on every axis: same-domain by default, depth limited to the links found on one page (no recursion), a configurable page-count cap, and it skips fragments, obvious asset extensions, and mailto/social/login/share links.

## Observability and Errors

Each request receives a validated or generated correlation ID returned in `X-Request-ID`. Errors follow `{ "error": { "code", "message", "request_id" } }`; unhandled exceptions return a generic message, never raw exception text. Logs omit headers, request bodies, exception text, and provider credentials (`AZURE_OPENAI_API_KEY` is a `repr=False` Pydantic field so it can't leak through settings logging/repr either).

## Deferred

- **PostgreSQL + pgvector**: `DocumentChunk.embedding` is a JSON column and `SemanticSearchService` does an in-Python cosine scan over a workspace's chunks. Both are correct at demo scale and intentionally isolated behind `SemanticSearchService.search()` so a pgvector column + ANN query can replace the implementation without changing callers. Not done yet.
- **Production auth**: a single deterministic development identity resolves to one workspace on every request. No login flow, no JWT/OIDC, no multi-user session handling.
- **Distributed workers**: no Redis, no Celery, no queue. All ingestion/analysis/indexing work happens inline in the request (or the in-process scheduler tick) that triggers it.
- **Ask Vantage conversation memory, alerts, email, PDF reporting, agents**: not implemented.
