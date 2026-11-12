$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Stopping Custom-CRM..."
docker compose down --remove-orphans 2>$null | Out-Null
docker compose -f docker-compose.yml -f docker-compose.postgres.yml down --remove-orphans 2>$null | Out-Null
$listeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
foreach ($listener in $listeners) {
    Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
}
Write-Host "Done."
