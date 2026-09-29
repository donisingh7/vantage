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

Mock-first: `LLM_PROVIDER` and `EMBEDDING_PROVIDER` both default to `mock` and require no credentials -- everything above runs and is testable without any cloud account. Real Azure OpenAI and Gemini adapters exist for both providers (see [Provider Modes](#provider-modes)) but neither is the default.

## Not Included

No Docker/Kubernetes/Terraform, no Redis/Celery (scheduling is a single in-process APScheduler, off by default and always disabled in tests), no production authentication/SSO (a single deterministic development identity resolves to one workspace), no pgvector/PostgreSQL yet (see [Data Store](#data-store)), no alerts/email/PDF reporting, no conversation memory in Ask Vantage.

Deployment is **prepared, not live**: an AWS Lambda handler, a Gemini-based ZIP build, and manual (workflow_dispatch-only) GitHub Actions workflows for an OIDC auth smoke test and a Lambda code-update deploy all exist in this repository (see [Production Deployment](#production-deployment-prepared-not-live)), but no Lambda function, API Gateway, or frontend hosting has actually been created or run against real traffic yet.

## Architecture

- `apps/api`: FastAPI, Pydantic Settings, async SQLAlchemy, Alembic, provider contracts (`LLMProvider`, `EmbeddingProvider`, `SourceFetcher`), and pytest coverage.
- `apps/web`: Next.js App Router and TypeScript executive workspace UI, calling the API through a single shared client (`src/lib/api.ts`).
- `docs/architecture.md`: component boundaries, request flow, and what's deferred.

The API owns identity resolution, persistence, ingestion, analysis, indexing, retrieval, and provider interfaces. The web app owns presentation only. All business entities are workspace-scoped; repository queries always filter by `workspace_id`, so possessing an entity's UUID alone never grants access across workspaces.

## Technology

- Python 3.12+ (also the AWS Lambda runtime target), FastAPI, Pydantic v2, SQLAlchemy 2.x (async), Alembic, SQLite (dev) / PostgreSQL-ready, pytest, ruff.
- Next.js 15 App Router, React, TypeScript, ESLint.
- `httpx` + `feedparser` for fetching, `apscheduler` for optional in-process scheduling, `playwright` for an opt-in browser-rendering fallback, `openai` for the real Azure OpenAI adapters, `google-genai` (the current official SDK, not the deprecated `google-generativeai`) for the real Gemini adapters, `mangum` to run the existing FastAPI app on AWS Lambda unchanged.

## Repository Structure

```text
apps/
  api/
    app/
      api/          Routes and dependency wiring (app/api/deps.py)
      models/        SQLAlchemy entities (workspace-scoped)
      schemas/       Pydantic request/response contracts
      services/      Business logic: ingestion, analysis, indexing, search, ask, scheduling
      providers/     LLMProvider / EmbeddingProvider contracts + mock, Azure OpenAI, and Gemini adapters
      lambda_handler.py  AWS Lambda entrypoint (Mangum-wrapped app.main:app); local dev is unaffected
    migrations/      Alembic environment and versioned migrations
    requirements-lambda.txt  Trimmed runtime-only dependency set for the Lambda ZIP build
    tests/           Backend test suite (mocked SDKs/network only, no live calls)
  web/
    src/app/         App Router pages
    src/components/  Workspace UI (dashboard, intelligence, ask, resource managers)
    src/lib/         Shared API client
.github/workflows/   Manual-only CI: an AWS OIDC auth smoke test and a Lambda code-update deploy
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

| | `mock` (default) | `azure_openai` | `gemini` |
|---|---|---|---|
| Credentials required | None | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and the relevant deployment name(s) | `GEMINI_API_KEY` |
| Network calls | None -- fully deterministic, content-derived output | Real Azure OpenAI calls | Real Gemini calls (`google-genai` SDK) |
| Where selected | `LLM_PROVIDER=mock`, `EMBEDDING_PROVIDER=mock` | `LLM_PROVIDER=azure_openai`, `EMBEDDING_PROVIDER=azure_openai` | `LLM_PROVIDER=gemini`, `EMBEDDING_PROVIDER=gemini` |

All three are independently switchable per role (LLM vs. embedding); `app/api/deps.py` is the only place that branches on which one is selected.

Mock mode is not a placeholder that silently does nothing: `MockLLMProvider` classifies signal type/sentiment from real keyword heuristics and a stable content hash, and grounds its Ask Vantage answers in the actual retrieved `[Source N]` blocks -- so the whole pipeline is exercisable end to end without any account. Every mock-labeled result is clearly marked as such in the API (`provider` fields) and the UI (a visible "Mock AI" badge).

Selecting `azure_openai` or `gemini` for either provider without its required settings fails fast at startup with a clear configuration error (which required variable is missing), not a runtime crash. All real adapters implement the exact same `LLMProvider`/`EmbeddingProvider` interfaces the mocks do, so no calling code changes between modes. Real provider failures are wrapped into a generic `provider_error` response -- the raw SDK exception text (which can echo request details, and for Gemini specifically could echo the API key) is never returned to the client.

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

To switch to real Gemini, set in `.env`:

```
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=<your-key>
GEMINI_CHAT_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
GEMINI_EMBEDDING_DIMENSIONS=768
```

`GeminiEmbeddingProvider` sends one embedding request per input string (never Gemini's multi-content aggregation), so `embed_documents(["a", "b"])` always returns exactly `[vector_for_a, vector_for_b]` in order, matching the interface every caller already relies on. It also applies Gemini's retrieval-aware formatting -- a query is embedded as `task: search result | query: {text}`, a stored document/chunk as `title: none | text: {text}` -- and its fingerprint (`gemini:{model}:dims={n}:retrieval-v1`) changes if the model, dimensions, or that formatting ever changes, which naturally forces the existing re-index logic (see [Data Store](#data-store)) rather than silently comparing incompatible vectors.

See `.env.example` for every variable, including ingestion timeouts/retries and optional scheduling settings.

## Data Store

SQLite (`sqlite+aiosqlite`) is the current implementation -- it's what `DATABASE_URL` points to by default, and it's what every migration and test runs against. `DATABASE_URL` also accepts a `postgresql+asyncpg://...` URL, and the code (session setup, migrations) already branches on the URL scheme, but no PostgreSQL-specific schema has been introduced yet. Local SQLite behavior is completely unaffected by anything below.

For a serverless/autoscaling deployment (e.g. running the API on AWS Lambda), set `DATABASE_SERVERLESS=true` alongside a `postgresql+asyncpg://` `DATABASE_URL`. `DATABASE_SERVERLESS` means "this process is short-lived and scales independently, so don't keep a persistent client-side connection pool" -- `app/db/session.py` switches to `NullPool` and requires SSL on the connection. It is plain, provider-neutral SQLAlchemy/asyncpg configuration, not a Supabase-specific code path -- no hostname, project ID, or credentials are hardcoded anywhere in the codebase.

**This does not mean transaction-pooler (e.g. PgBouncer/Supabase Transaction Pooler) support.** SQLAlchemy's `asyncpg` dialect relies on server-side prepared statements, which a transaction-mode pooler doesn't support; this repository does not claim that compatibility and does not attempt to fake it by disabling asyncpg's prepared-statement cache. For Supabase specifically, the supported production path is the **Session Pooler** (port 5432): copy its connection string as-is from the Supabase Dashboard's Connect screen -- never construct the hostname manually -- and use it with the async scheme, `postgresql+asyncpg://...`. Real connection strings/passwords are never committed; only `.env.example` placeholders live in this repository. Transaction-pooler support is intentionally deferred unless the database driver/configuration is changed and separately validated for it.

Embeddings today are stored as a plain JSON float array on `DocumentChunk`, and semantic search is a brute-force in-Python cosine scan over one workspace's chunks -- correct and fine at demo scale, not the final retrieval path. The planned future step is a PostgreSQL + `pgvector` migration that replaces the JSON column with a vector column and an ANN index, and swaps the scan for an `ORDER BY embedding <=> query LIMIT k` query, behind the same `SemanticSearchService.search()` method so no caller changes. That migration is intentionally not part of this repository yet. A document's persisted index is invalidated (and transparently rebuilt) not just by a content change but also by an embedding provider/model/dimension change, via each `EmbeddingProvider`'s `fingerprint()` -- switching from mock to Gemini, or changing `GEMINI_EMBEDDING_DIMENSIONS`, can't silently leave stale, dimension-mismatched vectors behind.

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

All backend tests mock external SDKs/network (httpx `MockTransport`, patched `openai` and `google.genai` clients) -- none make a real network call, and none use a real API key.

Frontend:

```powershell
Push-Location apps/web
npm run lint
npm run typecheck
npm run build
Pop-Location
```

## Production Deployment (Prepared, Not Live)

The pieces needed to run the API on AWS Lambda are in this repository; none of them have been used to actually deploy anything yet -- there is no Lambda function, no API Gateway, and no live URL.

- **Handler**: `apps/api/app/lambda_handler.py` wraps the same FastAPI app from `app/main.py` with [Mangum](https://github.com/jordaneremieff/mangum), at handler path `app.lambda_handler.handler`. It changes nothing about local development -- `uvicorn app.main:app --reload` still works exactly as before -- and it never runs database migrations at cold start (those are applied out of band, e.g. `alembic upgrade head` before a deploy).
- **Intended production settings** (set as the Lambda function's own environment variables, never committed): `APP_ENV=production`, `ENABLE_SCHEDULER=false`, `ENABLE_BROWSER_FALLBACK=false`, `DATABASE_SERVERLESS=true`. The scheduler being off is what keeps a request-driven Lambda from trying to run an in-process background loop.
- **Package**: `apps/api/requirements-lambda.txt` is a trimmed runtime-only dependency set (no Playwright binaries, no dev/test tooling, no `alembic`/`aiosqlite`, no frontend files, no `.env`, no credentials) -- see the comments in that file for exactly what's excluded and why. No Docker, no SAM/CDK/Terraform: the deploy workflow below builds a plain ZIP.
- **CI (both manual-only, `workflow_dispatch`, no automatic trigger)**:
  - `.github/workflows/aws-oidc-smoke.yml` -- authenticates to AWS via GitHub's OIDC provider (no long-lived AWS access keys stored anywhere) and runs `aws sts get-caller-identity` as a pure auth check.
  - `.github/workflows/deploy-api-lambda.yml` -- builds the Lambda ZIP on `ubuntu-latest`/Python 3.12 (so native packages like `asyncpg` resolve as Lambda-compatible Linux wheels), authenticates the same OIDC way, and runs `aws lambda update-function-code` against the existing `vantage-api` function in `ap-south-1`. It only updates code on a function that must already exist; it never creates the function, an execution role, or API Gateway, and it never touches IAM.

Both workflows reference only `${{ vars.AWS_ROLE_ARN }}` (a GitHub repository variable, not a secret). Still needed before any of this can actually run against a real function: the AWS role/OIDC trust policy and the `AWS_ROLE_ARN` repository variable itself, an actual `vantage-api` Lambda function (with its execution role) for the deploy workflow to update, and -- separately, for real production traffic rather than just the OIDC/deploy mechanics -- `GEMINI_API_KEY` and a serverless PostgreSQL `DATABASE_URL`, set directly as the Lambda function's own environment variables, never committed here.

Not yet part of this repository: creating the Lambda function and its execution role, API Gateway (or another HTTP front door) in front of it, and Vercel (or any) frontend hosting.

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
