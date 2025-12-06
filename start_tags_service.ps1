# Starts the lightweight FastAPI tags service on port 8001
$ErrorActionPreference = "Stop"

$python = Get-Command py -ErrorAction SilentlyContinue
if (-not $python) {
  Write-Host "Python bulunamadı. Lütfen Python 3.9+ kurun." -ForegroundColor Red
  exit 1
}

Write-Host "Tags servisi başlatılıyor: http://127.0.0.1:8001" -ForegroundColor Green

py -m pip show fastapi >$null 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host "fastapi kuruluyor..." -ForegroundColor Yellow
  py -m pip install fastapi uvicorn >$null
}

py -m uvicorn tags_api:app --host 127.0.0.1 --port 8001 --reload
