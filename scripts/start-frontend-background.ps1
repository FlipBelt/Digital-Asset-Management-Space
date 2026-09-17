$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $ProjectRoot "frontend"
$RuntimeRoot = Join-Path $ProjectRoot ".local\frontend"
$PidFile = Join-Path $RuntimeRoot "frontend.pid"
$StdOut = Join-Path $RuntimeRoot "frontend.out.log"
$StdErr = Join-Path $RuntimeRoot "frontend.err.log"
$Node = (Get-Command node -ErrorAction Stop).Source
$Vite = Join-Path $FrontendRoot "node_modules\vite\bin\vite.js"
$DistIndex = Join-Path $FrontendRoot "dist\index.html"

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null

try {
    $Response = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -UseBasicParsing -TimeoutSec 3
    if ($Response.StatusCode -eq 200) {
        Write-Host "Frontend is already running at http://127.0.0.1:5173"
        exit 0
    }
}
catch {
    # Continue with startup.
}

if (-not (Test-Path -LiteralPath $Vite)) {
    throw "Frontend dependencies are missing. Run npm install in $FrontendRoot first."
}
if (-not (Test-Path -LiteralPath $DistIndex)) {
    throw "Frontend production build is missing. Run npm run build in $FrontendRoot first."
}

$Process = Start-Process `
    -FilePath $Node `
    -ArgumentList @($Vite, "preview", "--host", "127.0.0.1", "--port", "5173", "--strictPort") `
    -WorkingDirectory $FrontendRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $StdOut `
    -RedirectStandardError $StdErr `
    -PassThru

Set-Content -LiteralPath $PidFile -Value $Process.Id

for ($Attempt = 0; $Attempt -lt 20; $Attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $Response = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -UseBasicParsing -TimeoutSec 2
        if ($Response.StatusCode -eq 200) {
            Write-Host "Frontend started at http://127.0.0.1:5173 (PID $($Process.Id))"
            exit 0
        }
    }
    catch {
        # Wait for Vite to become ready.
    }
}

throw "Frontend did not become ready. Check $StdErr"
