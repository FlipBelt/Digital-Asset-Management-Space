$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"
$BackendDir = Join-Path $ProjectRoot "backend"
$RunDir = Join-Path $ProjectRoot ".local\backend"
$PidFile = Join-Path $RunDir "backend.pid"
$StdoutLog = Join-Path $RunDir "backend.out.log"
$StderrLog = Join-Path $RunDir "backend.err.log"

New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

try {
    $Ready = Invoke-RestMethod -Uri "http://127.0.0.1:8100/api/v1/health/ready" -TimeoutSec 3
    if ($Ready.status) {
        Write-Host "Backend is already running at http://127.0.0.1:8100"
        exit 0
    }
}
catch {
    # Continue with startup.
}

if (Test-Path -LiteralPath $PidFile) {
    $ExistingPid = [int](Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue)
    $TrackedProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $ExistingPid" -ErrorAction SilentlyContinue
    if ($TrackedProcess -and $TrackedProcess.CommandLine -match "uvicorn" -and $TrackedProcess.CommandLine -match "app\.main:app") {
        throw "Tracked backend process $ExistingPid exists but is not ready. Check $StderrLog before retrying."
    }
    Remove-Item -LiteralPath $PidFile -Force
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Backend virtual environment is missing. Run scripts\setup-local.ps1 first."
}

$Process = Start-Process `
    -FilePath $Python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8100") `
    -WorkingDirectory $BackendDir `
    -RedirectStandardOutput $StdoutLog `
    -RedirectStandardError $StderrLog `
    -WindowStyle Hidden `
    -PassThru

Set-Content -LiteralPath $PidFile -Value $Process.Id -NoNewline -Encoding ASCII

for ($Attempt = 0; $Attempt -lt 20; $Attempt++) {
    Start-Sleep -Milliseconds 500
    if ($Process.HasExited) { break }
    try {
        $Ready = Invoke-RestMethod -Uri "http://127.0.0.1:8100/api/v1/health/ready" -TimeoutSec 2
        if ($Ready.status) {
            Write-Host "Backend started at http://127.0.0.1:8100 (PID $($Process.Id))"
            exit 0
        }
    }
    catch {
        # Wait for the API and database readiness check.
    }
}

if ((Test-Path -LiteralPath $PidFile) -and ((Get-Content -LiteralPath $PidFile -Raw).Trim() -eq [string]$Process.Id)) {
    Remove-Item -LiteralPath $PidFile -Force
}
throw "Backend did not become ready. Check $StderrLog"
