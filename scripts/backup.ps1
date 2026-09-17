$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ProjectDrive = "Q:"
if (-not (Test-Path -LiteralPath "$ProjectDrive\")) {
    & "C:\Windows\System32\subst.exe" $ProjectDrive $ProjectRoot
}
$PgDump = "$ProjectDrive\.runtime\postgresql\pgsql\bin\pg_dump.exe"
$BackupDir = Join-Path $ProjectRoot ".local\backups"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupFile = Join-Path $BackupDir "account-center-$Timestamp.dump"

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$env:PGPASSWORD = "account_center_local"
try {
    & $PgDump -h 127.0.0.1 -p 55432 -U account_center -d account_center -Fc -f $BackupFile
    if ($LASTEXITCODE -ne 0) {
        throw "Database backup failed."
    }
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

Get-ChildItem -LiteralPath $BackupDir -Filter "account-center-*.dump" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 7 |
    Remove-Item -Force

Write-Host "Backup ready: $BackupFile"
