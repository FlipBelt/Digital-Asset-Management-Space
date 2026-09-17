$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $ProjectRoot ".local\backend\backend.pid"

function Stop-ProcessTree {
    param([int]$ProcessId)

    $Children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
    foreach ($Child in $Children) {
        Stop-ProcessTree -ProcessId $Child.ProcessId
    }
    Stop-Process -Id $ProcessId -ErrorAction SilentlyContinue
}

if (Test-Path -LiteralPath $PidFile) {
    $BackendPid = [int](Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue)
    if ($BackendPid) {
        $Process = Get-CimInstance Win32_Process -Filter "ProcessId = $BackendPid" -ErrorAction SilentlyContinue
        if ($Process -and $Process.CommandLine -match "uvicorn" -and $Process.CommandLine -match "app\.main:app") {
            Stop-ProcessTree -ProcessId $BackendPid
            Wait-Process -Id $BackendPid -Timeout 10 -ErrorAction SilentlyContinue
        }
        elseif ($Process) {
            Write-Warning "PID $BackendPid belongs to another process; it was not stopped."
        }
    }
    Remove-Item -LiteralPath $PidFile -Force
}
