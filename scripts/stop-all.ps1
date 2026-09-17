$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "stop-frontend.ps1")
& (Join-Path $PSScriptRoot "stop-backend.ps1")
& (Join-Path $PSScriptRoot "stop-postgres.ps1")
