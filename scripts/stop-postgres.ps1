$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ProjectDrive = "Q:"
$PgCtl = Join-Path "$ProjectDrive\" ".runtime\postgresql\pgsql\bin\pg_ctl.exe"
$DataDir = Join-Path "$ProjectDrive\" ".local\postgres\data"

if ((Test-Path -LiteralPath $PgCtl) -and (Test-Path -LiteralPath (Join-Path $DataDir "PG_VERSION"))) {
    & $PgCtl -D $DataDir stop -m fast
}
