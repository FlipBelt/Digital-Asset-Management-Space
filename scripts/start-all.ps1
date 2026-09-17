$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "start-postgres.ps1")
& (Join-Path $PSScriptRoot "migrate.ps1")
& (Join-Path $PSScriptRoot "start-backend-background.ps1")
& (Join-Path $PSScriptRoot "start-frontend-background.ps1")
& (Join-Path $PSScriptRoot "status.ps1")
