$ErrorActionPreference = 'Stop'

function Stop-Connector([string]$Message, [int]$Code) {
    [Console]::Error.WriteLine($Message)
    exit $Code
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    Stop-Connector 'This optional connector requires a local Windows desktop.' 1
}

$uvCommand = Get-Command -Name uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $uvCommand) {
    Stop-Connector 'Missing uv. Install Python 3.11-3.13 and uv, then follow connector/README.md.' 2
}

$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$entryPath = Join-Path $PSScriptRoot '.venv/Scripts/flipbelt-agent-connector.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    Stop-Connector 'Missing local dependencies. In this connector directory, explicitly run: uv sync --frozen --no-dev --project .' 3
}

$sourcePath = Join-Path $PSScriptRoot 'src'
$dependenciesReady = $false
try {
    & $pythonPath -c 'import pathlib, sys; import mcp, httpx, flipbelt_connector; sys.exit(0 if pathlib.Path(flipbelt_connector.__file__).resolve().is_relative_to(pathlib.Path(sys.argv[1]).resolve()) else 1)' $sourcePath 2>$null
    $dependenciesReady = $LASTEXITCODE -eq 0
}
catch {
    $dependenciesReady = $false
}
if (-not $dependenciesReady) {
    Stop-Connector 'Invalid local dependencies. In this connector directory, explicitly run: uv sync --frozen --no-dev --project .' 4
}
if (-not (Test-Path -LiteralPath $entryPath -PathType Leaf)) {
    Stop-Connector 'Missing connector entry point. In this connector directory, explicitly run: uv sync --frozen --no-dev --project .' 5
}

$previous = @{}
foreach ($name in @('UV_OFFLINE', 'UV_PYTHON_DOWNLOADS', 'UV_PROJECT_ENVIRONMENT', 'FLIPBELT_CLIENT_NAME')) {
    $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

try {
    # Startup uses only this installed environment and never installs or downloads.
    $env:UV_OFFLINE = '1'
    $env:UV_PYTHON_DOWNLOADS = 'never'
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $PSScriptRoot '.venv'
    if ([string]::IsNullOrWhiteSpace($env:FLIPBELT_CLIENT_NAME)) {
        $env:FLIPBELT_CLIENT_NAME = 'QwenWork'
    }
    & $uvCommand.Source run --frozen --no-sync --project $PSScriptRoot flipbelt-agent-connector
    $connectorExitCode = $LASTEXITCODE
}
finally {
    foreach ($name in $previous.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
}

exit $connectorExitCode
