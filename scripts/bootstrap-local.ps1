$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "setup-local.ps1")
& (Join-Path $PSScriptRoot "start-postgres.ps1")
& (Join-Path $PSScriptRoot "migrate.ps1")
& (Join-Path $PSScriptRoot "start-backend-background.ps1")

Write-Host "Local environment is ready: http://127.0.0.1:8100/docs"

