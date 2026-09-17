$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendVenv = Join-Path $ProjectRoot "backend\.venv\Scripts"

Push-Location (Join-Path $ProjectRoot "backend")
try {
    & (Join-Path $BackendVenv "ruff.exe") check app tests
    if ($LASTEXITCODE -ne 0) { throw "Backend lint failed." }
    & (Join-Path $BackendVenv "pytest.exe")
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }
    & (Join-Path $BackendVenv "alembic.exe") check
    if ($LASTEXITCODE -ne 0) { throw "Database migration check failed." }
}
finally {
    Pop-Location
}

Push-Location (Join-Path $ProjectRoot "frontend")
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
}
finally {
    Pop-Location
}

Write-Host "Backend, database migrations, tests, and frontend build are verified."
