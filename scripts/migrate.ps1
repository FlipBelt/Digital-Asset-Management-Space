$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"

Push-Location (Join-Path $ProjectRoot "backend")
try {
    & $Python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Database migration failed." }
    & $Python -m app.cli.seed
    if ($LASTEXITCODE -ne 0) { throw "Database seed failed." }
}
finally {
    Pop-Location
}
