$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $ProjectRoot ".local\frontend\frontend.pid"

if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host "Frontend PID file not found."
    exit 0
}

$FrontendPid = [int](Get-Content -LiteralPath $PidFile)
$Process = Get-CimInstance Win32_Process -Filter "ProcessId = $FrontendPid" -ErrorAction SilentlyContinue

if ($Process -and $Process.CommandLine -match "vite" -and $Process.CommandLine -match "5173") {
    Stop-Process -Id $FrontendPid -Force
    Write-Host "Frontend stopped (PID $FrontendPid)."
}
elseif ($Process) {
    Write-Warning "PID $FrontendPid belongs to another process; it was not stopped."
}
else {
    Write-Host "Frontend process is not running."
}

Remove-Item -LiteralPath $PidFile -Force
