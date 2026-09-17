$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $ProjectRoot ".local\backend\backend.pid"

try {
    $Ready = Invoke-RestMethod -Uri "http://127.0.0.1:8100/api/v1/health/ready" -TimeoutSec 5
    Write-Host "Backend: $($Ready.status)"
    Write-Host "Database: $($Ready.database)"
}
catch {
    Write-Host "Backend: unavailable"
}

if (Test-Path -LiteralPath $PidFile) {
    $BackendPid = [int](Get-Content -LiteralPath $PidFile)
    $BackendProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $BackendPid" -ErrorAction SilentlyContinue
    if ($BackendProcess -and $BackendProcess.CommandLine -match "uvicorn" -and $BackendProcess.CommandLine -match "app\.main:app") {
        Write-Host "Backend tracked process: $BackendPid"
    }
    else {
        Write-Host "Backend PID file: stale ($BackendPid)"
    }
}

$FrontendPidFile = Join-Path $ProjectRoot ".local\frontend\frontend.pid"

try {
    $Frontend = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -UseBasicParsing -TimeoutSec 5
    Write-Host "Frontend: ready ($($Frontend.StatusCode))"
    Write-Host "Frontend URL: http://127.0.0.1:5173"
}
catch {
    Write-Host "Frontend: unavailable"
}

if (Test-Path -LiteralPath $FrontendPidFile) {
    $FrontendPid = [int](Get-Content -LiteralPath $FrontendPidFile)
    $FrontendProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $FrontendPid" -ErrorAction SilentlyContinue
    if ($FrontendProcess -and $FrontendProcess.CommandLine -match "vite" -and $FrontendProcess.CommandLine -match "5173") {
        Write-Host "Frontend tracked process: $FrontendPid"
    }
    else {
        Write-Host "Frontend PID file: stale ($FrontendPid)"
    }
}
