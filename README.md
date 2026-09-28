# Vantage

Vantage is an executive market intelligence platform: it monitors sources you configure, turns what it collects into structured, cited intelligence, and answers questions about it through Ask Vantage. It is a local-first, portfolio/demo-scale system today -- see [Status](#status) and [Not Included](#not-included) below for exactly what that means.

## Pipeline

```text
Source monitoring
  -> Crawling / ingestion        (HTTP + RSS fetch, bounded same-domain link discovery, retries, SSRF guard)
  -> Structured intelligence     (LLMProvider turns a Document into a scored, typed IntelligenceSignal)
  -> Indexing                    (Document -> deterministic chunks -> EmbeddingProvider -> DocumentChunk)
  -> Retrieval                   (cosine similarity over a workspace's chunks, top-k, workspace-scoped)
  -> Ask Vantage                 (retrieval -> grounded prompt -> LLMProvider -> answer + server-built citations)
  -> Executive dashboard         (real counts, priority signals, distributions, recent activity -- no fabricated metrics)
```

Every stage above is independently triggerable (manual "Run ingestion" / "Analyze" / "Index" actions, or an optional in-process scheduler for ingestion) -- nothing runs automatically end-to-end yet, by design.

## Status

Implemented: workspace-scoped CRUD for companies, topics, sources, and watchlists; website + RSS ingestion with bounded link discovery, retries, and per-source scheduling; structured document analysis into `IntelligenceSignal` rows with deterministic company/topic association; document chunking, embedding, and cosine-similarity semantic search; Ask Vantage with server-verified citations; an executive dashboard and intelligence timeline built entirely from real workspace data.

Mock-first: `LLM_PROVIDER` and `EMBEDDING_PROVIDER` both default to `mock` and require no credentials -- everything above runs and is testable without any cloud account. Real Azure OpenAI adapters exist for both providers (see [Provider Modes](#provider-modes)) but are not the default.

## Not Included

No Docker/Kubernetes/Terraform, no Redis/Celery (scheduling is a single in-process APScheduler, off by default and always disabled in tests), no production authentication/SSO (a single deterministic development identity resolves to one workspace), no pgvector/PostgreSQL yet (see [Data Store](#data-store)), no alerts/email/PDF reporting, no conversation memory in Ask Vantage, no live deployment.

## Architecture

- `apps/api`: FastAPI, Pydantic Settings, async SQLAlchemy, Alembic, provider contracts (`LLMProvider`, `EmbeddingProvider`, `SourceFetcher`), and pytest coverage.
- `apps/web`: Next.js App Router and TypeScript executive workspace UI, calling the API through a single shared client (`src/lib/api.ts`).
- `docs/architecture.md`: component boundaries, request flow, and what's deferred.

The API owns identity resolution, persistence, ingestion, analysis, indexing, retrieval, and provider interfaces. The web app owns presentation only. All business entities are workspace-scoped; repository queries always filter by `workspace_id`, so possessing an entity's UUID alone never grants access across workspaces.

## Technology

- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.x (async), Alembic, SQLite (dev) / PostgreSQL-ready, pytest, ruff.
- Next.js 15 App Router, React, TypeScript, ESLint.
- `httpx` + `feedparser` for fetching, `apscheduler` for optional in-process scheduling, `playwright` for an opt-in browser-rendering fallback, `openai` for the real Azure OpenAI adapters.

## Repository Structure

```text
apps/
  api/
    app/
      api/          Routes and dependency wiring (app/api/deps.py)
      models/        SQLAlchemy entities (workspace-scoped)
      schemas/       Pydantic request/response contracts
      services/      Business logic: ingestion, analysis, indexing, search, ask, scheduling
      providers/     LLMProvider / EmbeddingProvider contracts + mock and Azure OpenAI adapters
    migrations/      Alembic environment and versioned migrations
    tests/           Backend test suite (mocked SDKs/network only, no live calls)
  web/
    src/app/         App Router pages
    src/components/  Workspace UI (dashboard, intelligence, ask, resource managers)
    src/lib/         Shared API client
docs/                Architecture notes
scripts/             Windows development shortcuts
```

## Local Development

Prerequisites: Python 3.12+, Node.js 22+, npm. No database server, no Docker.

1. Copy `.env.example` to `.env` (the defaults already run everything in mock mode).
2. Install and migrate the API:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -e "apps/api[dev]"
   Push-Location apps/api
   alembic upgrade head
   Pop-Location
   ```

3. In one terminal, start the API from the repository root:

   ```powershell
   .\scripts\dev.ps1 api
   ```

4. In another terminal, install and start the web application:

   ```powershell
   Push-Location apps/web
   npm install
   npm run dev
   Pop-Location
   ```

Open `http://localhost:3000`. API liveness is at `http://localhost:8000/health`, database readiness at `http://localhost:8000/ready`, versioned system info at `http://localhost:8000/api/v1/system/info`.

Optional: seed illustrative demo data (companies, topics, a couple of real public RSS/website sources) with:

```powershell
Push-Location apps/api
python -m app.scripts.seed_dev
Pop-Location
```

## Provider Modes

| | `mock` (default) | `azure_openai` |
|---|---|---|
| Credentials required | None | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and the relevant deployment name(s) |
| Network calls | None -- fully deterministic, content-derived output | Real Azure OpenAI calls |
| Where selected | `LLM_PROVIDER=mock`, `EMBEDDING_PROVIDER=mock` | `LLM_PROVIDER=azure_openai`, `EMBEDDING_PROVIDER=azure_openai` (independently switchable) |

Mock mode is not a placeholder that silently does nothing: `MockLLMProvider` classifies signal type/sentiment from real keyword heuristics and a stable content hash, and grounds its Ask Vantage answers in the actual retrieved `[Source N]` blocks -- so the whole pipeline is exercisable end to end without any account. Every mock-labeled result is clearly marked as such in the API (`provider` fields) and the UI (a visible "Mock AI" badge).

Selecting `azure_openai` for either provider without its required settings fails fast at startup with a clear configuration error (which required variable is missing), not a runtime crash. Both real adapters implement the exact same `LLMProvider`/`EmbeddingProvider` interfaces the mocks do, so no calling code changes between modes. Real provider failures are wrapped into a generic `provider_error` response -- the raw SDK exception text (which can echo request details) is never returned to the client.

To switch to real Azure OpenAI, set in `.env`:

```
LLM_PROVIDER=azure_openai
EMBEDDING_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_API_VERSION=2024-08-01-preview
AZURE_OPENAI_CHAT_DEPLOYMENT=<your-chat-deployment-name>
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=<your-embedding-deployment-name>
```

See `.env.example` for every variable, including ingestion timeouts/retries and optional scheduling settings.

## Data Store

SQLite (`sqlite+aiosqlite`) is the current implementation -- it's what `DATABASE_URL` points to by default, and it's what every migration and test runs against. `DATABASE_URL` also accepts a `postgresql+asyncpg://...` URL, and the code (session setup, migrations) already branches on the URL scheme, but no PostgreSQL-specific schema has been introduced yet.

Embeddings today are stored as a plain JSON float array on `DocumentChunk`, and semantic search is a brute-force in-Python cosine scan over one workspace's chunks -- correct and fine at demo scale, not the final retrieval path. The planned future step is a PostgreSQL + `pgvector` migration that replaces the JSON column with a vector column and an ANN index, and swaps the scan for an `ORDER BY embedding <=> query LIMIT k` query, behind the same `SemanticSearchService.search()` method so no caller changes. That migration is intentionally not part of this repository yet.

## Database Migrations

Run from `apps/api`:

```powershell
alembic upgrade head
alembic current
alembic downgrade base
```

## Tests and Checks

Backend:

```powershell
Push-Location apps/api
python -m pytest
python -m ruff check .
Pop-Location
```

All backend tests mock external SDKs/network (httpx `MockTransport`, a patched `openai` client) -- none make a real network call.

Frontend:

```powershell
Push-Location apps/web
npm run lint
npm run typecheck
npm run build
Pop-Location
```

## Git / PR Workflow

`main` is protected by convention: work happens on a feature branch (e.g. `feat/<name>`), and lands via a pull request into `main` that is reviewed before merging -- no direct pushes to `main`. Typical flow:

```powershell
git checkout main
git pull origin main
git checkout -b feat/my-change
# ...commit work...
git push -u origin feat/my-change
gh pr create --base main --head feat/my-change --title "..." --body "..."
```

## Clean-Room Statement

This repository is an independent implementation based only on the Vantage product specification and general engineering practices. It contains no copied employer, client, or internal implementation, configuration, assets, schema, prompts, or documentation.
