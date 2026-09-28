# Vantage

Vantage is an executive market intelligence platform foundation for strategy teams, product leaders, analysts, and other decision-makers. It is designed to grow from workspace-based monitoring into an evidence-led market intelligence system.

## Development Status

Part 1 establishes the application shell and backend foundation. The overview uses illustrative sample data. Workspace feature routes are honest placeholders; there is no production ingestion, live intelligence feed, or real AI analysis yet.

## Architecture

- `apps/api`: FastAPI, Pydantic Settings, async SQLAlchemy, Alembic, provider contracts, and pytest coverage.
- `apps/web`: Next.js App Router and TypeScript executive workspace shell.
- `infra`: API and web Dockerfiles.
- `docs/architecture.md`: current boundaries and planned extension points.

The API owns identity resolution, persistence contracts, request validation, and provider interfaces. The web application owns presentation and calls backend services through its shared API client. PostgreSQL is the system of record; its Compose image includes pgvector for later embedding-backed retrieval.

## Technology

- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, PostgreSQL, pgvector, pytest.
- Next.js 15 App Router, React, TypeScript, ESLint.
- Docker Compose for local PostgreSQL, API, and web services.

## Repository Structure

```text
apps/
  api/
    app/               API, configuration, models, providers, repositories
    migrations/        Alembic environment and initial migration
    tests/             Backend foundation tests
  web/
    src/app/           App Router pages and shared styles
    src/components/    Workspace navigation and dashboard
    src/lib/            Shared API client
infra/                 Dockerfiles
docs/                  Architecture notes
scripts/               Windows development shortcuts
```

## Local Development

Prerequisites: Python 3.12+, Node.js 22+, npm, and Docker Desktop (for PostgreSQL or the complete Compose workflow).

1. Copy `.env.example` to `.env`.
2. Start PostgreSQL with pgvector:

   ```powershell
   docker compose up -d postgres
   ```

3. Install and migrate the API:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -e "apps/api[dev]"
   Push-Location apps/api
   alembic upgrade head
   Pop-Location
   ```

4. In one terminal, start the API from the repository root:

   ```powershell
   .\scripts\dev.ps1 api
   ```

5. In another terminal, install and start the web application:

   ```powershell
   Push-Location apps/web
   npm install
   npm run dev
   Pop-Location
   ```

Open `http://localhost:3000`. The overview renders with sample workspace data. API liveness is at `http://localhost:8000/health`, database readiness is at `http://localhost:8000/ready`, and versioned system information is at `http://localhost:8000/api/v1/system/info`.

To run all Compose services instead, with `.env` present:

```powershell
docker compose up --build
```

Compose applies migrations before starting the API. Stop services with `docker compose down`; persistent PostgreSQL data remains in the named volume. `docker compose down -v` removes that local database volume.

## Environment

`.env.example` lists application, database, provider, logging, development-user, request-limit, and frontend API settings. `.env` is ignored by Git. Empty optional Azure values are ignored in mock mode. The default LLM and embedding providers are both `mock`; no cloud credentials are needed to boot or test.

## Mock Providers

`MockLLMProvider` returns repeatable explanatory text without network access. `MockEmbeddingProvider` creates stable, normalized vectors with configurable dimensions for local tests. Provider protocols isolate these implementations from future service logic. The dashboard's displayed activity is illustrative and is not sourced from the API.

## Database Migrations

Run commands from `apps/api` after PostgreSQL is available:

```powershell
alembic upgrade head
alembic current
alembic downgrade base
```

The initial migration enables the PostgreSQL `vector` extension and creates users, workspaces, workspace members, watchlists, companies, topics, and sources. It does not create future ingestion, analysis, or document tables.

## Tests and Checks

Backend tests:

```powershell
Push-Location apps/api
python -m pytest
Pop-Location
```

Frontend checks:

```powershell
Push-Location apps/web
npm run lint
npm run typecheck
npm run build
Pop-Location
```

## Clean-Room Statement

This repository is an independent implementation based only on the Vantage product specification and general engineering practices. It contains no copied employer, client, or internal implementation, configuration, assets, schema, prompts, or documentation.

## Implemented Capabilities

- FastAPI liveness, database-readiness, and versioned system-information endpoints.
- Structured request logging, correlation IDs, safe error responses, response security headers, CORS, and a configured request-body size check.
- Typed configuration with mock-first defaults and no required external identity or AI credentials.
- Workspace-aware UUID entities, membership-role values, a workspace repository, and a PostgreSQL/Alembic baseline.
- Development current-user provider abstraction and LLM/embedding provider contracts with deterministic mocks.
- Responsive overview, development sign-in, shared workspace navigation, and placeholder views for the planned workspace areas.
- Dockerfiles, Compose health checks, and a PostgreSQL/pgvector development database.

## Planned Next Phases

Workspace CRUD and membership enforcement; watchlist relationships; source ingestion; document normalization and deduplication; scheduled jobs; persisted intelligence; real AI provider adapters; semantic retrieval; Ask Vantage with citations; production identity; and operational reporting.
