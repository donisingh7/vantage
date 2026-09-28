param(
    [ValidateSet("api", "web", "test-api", "check-web")]
    [string]$Target = "api"
)

$ErrorActionPreference = "Stop"

switch ($Target) {
    "api" {
        Push-Location (Join-Path $PSScriptRoot "../apps/api")
        try { python -m uvicorn app.main:app --reload --port 8000 } finally { Pop-Location }
    }
    "web" {
        Push-Location (Join-Path $PSScriptRoot "../apps/web")
        try { npm run dev } finally { Pop-Location }
    }
    "test-api" {
        Push-Location (Join-Path $PSScriptRoot "../apps/api")
        try { python -m pytest } finally { Pop-Location }
    }
    "check-web" {
        Push-Location (Join-Path $PSScriptRoot "../apps/web")
        try {
            npm run lint
            npm run typecheck
        } finally { Pop-Location }
    }
}