$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $ProjectRoot "backend"
$VenvPython = Join-Path $BackendRoot ".venv\Scripts\python.exe"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required to create the locked backend environment. Install uv and retry."
}

Push-Location $BackendRoot
try {
    & uv sync --extra dev
    if ($LASTEXITCODE -ne 0) { throw "Backend dependency sync failed." }
}
finally {
    Pop-Location
}

Write-Host "Python virtual environment is ready: $VenvPython"
