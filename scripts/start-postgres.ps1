$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SubstExe = "C:\Windows\System32\subst.exe"
$ProjectDrive = "Q:"
if (-not (Test-Path -LiteralPath "$ProjectDrive\")) {
    & $SubstExe $ProjectDrive $ProjectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create the local Q: path mapping required by PostgreSQL."
    }
}

$MappedRoot = "$ProjectDrive\"
$PgRoot = Join-Path $MappedRoot ".runtime\postgresql\pgsql"
$PgBin = Join-Path $PgRoot "bin"
$DataDir = Join-Path $MappedRoot ".local\postgres\data"
$LogDir = Join-Path $MappedRoot ".local\postgres\logs"
$LogFile = Join-Path $LogDir "postgres.log"
$PasswordDir = Join-Path $MappedRoot ".local\postgres"
$SuperPasswordFile = Join-Path $PasswordDir "superuser-password.txt"
$Port = 55432

if (-not (Test-Path -LiteralPath (Join-Path $PgBin "pg_ctl.exe"))) {
    throw "Local PostgreSQL runtime was not found under .runtime/postgresql."
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $PasswordDir | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $DataDir "PG_VERSION"))) {
    [System.IO.File]::WriteAllText(
        $SuperPasswordFile,
        "postgres_local_admin",
        [System.Text.UTF8Encoding]::new($false)
    )
    & (Join-Path $PgBin "initdb.exe") -D $DataDir -U postgres --pwfile=$SuperPasswordFile --auth=scram-sha-256 --encoding=UTF8 --locale=C
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL initdb failed."
    }
}

& (Join-Path $PgBin "pg_ctl.exe") -D $DataDir status *> $null
if ($LASTEXITCODE -ne 0) {
    & (Join-Path $PgBin "pg_ctl.exe") -D $DataDir -l $LogFile -o "-p $Port -h 127.0.0.1" start
}

$env:PGPASSWORD = "postgres_local_admin"
$RoleExists = [string](& (Join-Path $PgBin "psql.exe") -h 127.0.0.1 -p $Port -U postgres -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='account_center'")
if ($RoleExists -ne "1") {
    & (Join-Path $PgBin "psql.exe") -h 127.0.0.1 -p $Port -U postgres -d postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE account_center LOGIN PASSWORD 'account_center_local' NOSUPERUSER NOCREATEDB NOCREATEROLE"
}

$DatabaseExists = [string](& (Join-Path $PgBin "psql.exe") -h 127.0.0.1 -p $Port -U postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='account_center'")
if ($DatabaseExists -ne "1") {
    & (Join-Path $PgBin "createdb.exe") -h 127.0.0.1 -p $Port -U postgres -O account_center account_center
}

Remove-Item Env:PGPASSWORD
Write-Host "PostgreSQL is running at 127.0.0.1:$Port"
