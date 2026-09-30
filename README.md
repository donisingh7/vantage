# Vantage

**Executive Market Intelligence Platform**

Vantage turns public sources you choose into structured intelligence and answers grounded in that evidence. It is a solo-built portfolio project with a live demo at **https://vantage-red-delta.vercel.app** -- not a commercial product, and not deployed for any customer.

## What It Does

- **Companies and topics** -- the organizations and strategic themes you want to follow.
- **Public sources** -- websites, RSS feeds, news, and blogs to collect from.
- **Watchlists** -- group companies, topics, and sources around a strategic question.
- **On-demand ingestion** -- fetch and store documents from a source when you run it.
- **Structured AI intelligence** -- analyze collected documents into typed, scored signals (type, sentiment, importance, business impact), linked to companies/topics.
- **Semantic indexing and search** -- chunk and embed documents for meaning-based retrieval.
- **Ask Vantage** -- ask a question and get an answer grounded only in your indexed evidence, with server-built citations.

In the live demo, ingestion, analysis, and indexing are **on-demand** actions. The in-process scheduler exists in the codebase but is **disabled in production** (`ENABLE_SCHEDULER=false`), and the Sources page says so. Vantage does not perform real-time or continuous monitoring.

## How To Use It

1. Add companies and topics.
2. Add public sources.
3. Create a watchlist.
4. Run ingestion on a source.
5. Analyze collected documents.
6. Index documents for search.
7. Review structured intelligence.
8. Ask grounded questions in Ask Vantage.

## Production Architecture

```text
Browser
  |
Vercel / Next.js            (primary function region: bom1)
  |
API Gateway                 (ap-south-1)
  |
AWS Lambda / FastAPI        (ap-south-1, Mangum handler)
  |
Supabase PostgreSQL         (Session Pooler, SSL, NullPool)
  |
Gemini LLM + Gemini embeddings
```

- `apps/web` -- Next.js 15 App Router + TypeScript. Presentation only; all API calls go through `src/lib/api.ts`.
- `apps/api` -- FastAPI, Pydantic v2, async SQLAlchemy 2.x, Alembic. Owns identity resolution, persistence, ingestion, analysis, indexing, retrieval, and provider interfaces.
- Every business entity is workspace-scoped; queries always filter by `workspace_id`.
- Read-only endpoints never construct an LLM or embedding client -- only the analyze/index/ask write paths do.
- Authentication is a single deterministic development identity, not production SSO.

## Request-Count Improvements

Architectural consolidation of each page's browser-to-API requests on its normal path. These are **request counts, not latency benchmarks** -- no timing figures are claimed.

| View | Before | After | Endpoint |
|---|---|---|---|
| Overview | 7 | 1 | `GET /api/v1/dashboard/overview` |
| Sources | 2 | 1 | `GET /api/v1/sources/management/view` |
| Watchlists (initial) | 5 | 1 | `GET /api/v1/watchlists/bootstrap/initial` |
| Intelligence (initial) | 6 | 1 | `GET /api/v1/intelligence/bootstrap` |
| Intelligence (filter change) | 6 | 1 | `GET /api/v1/intelligence/signals?...` |
| Entity Intelligence dialog | 4 | 1 | `GET /api/v1/intelligence/entities/{kind}/{id}` |

Backend reads behind these use bounded, workspace-scoped queries and database-side aggregation rather than loading full history into memory. Mutations reconcile local UI state from their own responses instead of refetching the page.

## Local Development

Prerequisites: Python 3.12+, Node.js 22+, npm. No database server or Docker needed -- local development uses SQLite and mock AI providers by default.

```powershell
# API
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e "apps/api[dev]"
Push-Location apps/api; alembic upgrade head; Pop-Location
.\scripts\dev.ps1 api            # http://localhost:8000

# Web (second terminal)
Push-Location apps/web; npm install; npm run dev; Pop-Location   # http://localhost:3000
```

Optional demo data: `Push-Location apps/api; python -m app.scripts.seed_dev; Pop-Location`.

Health: `/health` (liveness), `/ready` (database), `/api/v1/system/info`.

### Provider modes

`LLM_PROVIDER` and `EMBEDDING_PROVIDER` default to `mock`: deterministic, no credentials, no network. `gemini` (production) and `azure_openai` adapters implement the same interfaces; selecting one without its required settings fails fast at startup. Mock results are labeled "Mock AI" in the UI. See `.env.example` for every variable.

## Tests and Checks

```powershell
Push-Location apps/api; python -m pytest -q; python -m ruff check .; Pop-Location
Push-Location apps/web; npm run lint; npm run build; Pop-Location
```

Backend tests never make real network calls or use real API keys; test settings ignore the ambient environment and `.env`.

## Deployment

- **Frontend** -- Vercel deploys automatically from `main` (project root `apps/web`).
- **Backend** -- a GitHub Actions workflow (`deploy-api-lambda.yml`, manually triggered) builds a Lambda ZIP from `apps/api/requirements-lambda.txt` and updates the existing function. AWS access uses GitHub OIDC -- **no long-lived AWS access keys** are stored anywhere. `lambda-package-check.yml` validates the package build.
- Runtime secrets (`GEMINI_API_KEY`, `DATABASE_URL`) live only in the Lambda function's own environment configuration, never in this repository.
- Database migrations run out of band (`alembic upgrade head`), never at Lambda cold start.
- No Docker, Kubernetes, Terraform, SAM, or CDK.

Embeddings are stored as JSON float arrays and searched with an in-process cosine scan per workspace -- appropriate at demo scale; a `pgvector` migration is not part of this repository.

## Git Workflow

All work lands through a feature branch and a reviewed pull request into `main`; no direct pushes to `main`.

## Clean-Room Statement

This repository is an independent implementation based only on the Vantage product specification and general engineering practices. It contains no copied employer, client, or internal implementation, configuration, assets, schema, prompts, or documentation.
