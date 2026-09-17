$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"

Push-Location (Join-Path $ProjectRoot "backend")
try {
    & $Python -m ruff check app tests
    & $Python -m pytest
}
finally {
    Pop-Location
}
