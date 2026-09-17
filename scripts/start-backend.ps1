$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"

Push-Location (Join-Path $ProjectRoot "backend")
try {
    & $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8100 --reload
}
finally {
    Pop-Location
}
