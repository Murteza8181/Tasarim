# Starts the local FastAPI variants service on port 5055
$ErrorActionPreference = "Stop"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  Write-Host "Python bulunamadı. Lütfen Python 3.9+ yükleyin." -ForegroundColor Red
  exit 1
}

$env:VARYANT_KLASORU = "\\192.168.1.36\TasarımVeSablonuOlanDesenler\VARYANT - Şablonu Olan Desenler"
Write-Host "VARYANT_KLASORU: $env:VARYANT_KLASORU"

# Ensure uvicorn installed
$uv = python -c "import uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "uvicorn kuruluyor..." -ForegroundColor Yellow
  python -m pip install --upgrade pip | Out-Null
  python -m pip install uvicorn fastapi | Out-Null
}

Write-Host "Servis başlatılıyor: http://127.0.0.1:5055" -ForegroundColor Green
python -m uvicorn variants_api:app --host 127.0.0.1 --port 5055 --reload
