param(
    [string]$Mode = "sqlite"
)

$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "============================================================"
Write-Host " Custom-CRM launcher"
Write-Host "============================================================"

if (-not (Test-Path ".env")) {
    Write-Host "[1/7] .env not found - copying .env.example"
    Copy-Item ".env.example" ".env"
} else {
    Write-Host "[1/7] .env found"
}

Write-Host "[2/7] Stopping old containers and port 8000..."
docker compose down --remove-orphans 2>$null | Out-Null
docker compose -f docker-compose.yml -f docker-compose.postgres.yml down --remove-orphans 2>$null | Out-Null
$listeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
foreach ($listener in $listeners) {
    Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
}

Write-Host "[3/7] Clearing Python cache..."
Get-ChildItem -Path . -Recurse -Directory -Filter __pycache__ -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .pytest_cache, .ruff_cache -ErrorAction SilentlyContinue

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[4/7] Docker is not available. Starting locally with .venv..."
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Write-Host "Creating virtual environment..."
        py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) {
            python -m venv .venv
        }
    }
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Write-Host "[ERROR] Could not create .venv. Install Python 3.12."
        exit 1
    }
    Write-Host "[5/7] Installing dependencies..."
    & ".venv\Scripts\python.exe" -m pip install --upgrade pip | Out-Null
    & ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Dependency installation failed."
        exit 1
    }
    Write-Host "[6/7] Starting Uvicorn..."
    Start-Process "http://127.0.0.1:8000"
    & ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
    exit $LASTEXITCODE
}

Write-Host "[4/7] Docker is available. Building image..."
docker compose build
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Docker build failed."
    exit 1
}

$composeArgs = @("compose")
if ($Mode -eq "postgres") {
    Write-Host "[5/7] Starting with PostgreSQL..."
    $composeArgs += @("-f", "docker-compose.yml", "-f", "docker-compose.postgres.yml")
} else {
    Write-Host "[5/7] Starting with SQLite..."
}

& docker @composeArgs up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Docker Compose start failed."
    exit 1
}

Write-Host "[6/7] Waiting for healthcheck..."
$healthy = $false
for ($i = 0; $i -lt 90; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            $healthy = $true
            break
        }
    } catch {
        # still starting
    }
    Start-Sleep -Seconds 1
}

if (-not $healthy) {
    Write-Host "[ERROR] Healthcheck failed. Last logs:"
    & docker @composeArgs logs --tail=80 app
    exit 1
}

Write-Host "[7/7] Ready: http://127.0.0.1:8000"
Start-Process "http://127.0.0.1:8000"
Write-Host "Streaming logs. Press Ctrl+C to stop viewing (container keeps running)."
& docker @composeArgs logs -f app
