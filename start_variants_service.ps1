# Starts the local FastAPI variants service on port 8001
$ErrorActionPreference = "Stop"

# py.exe kullan (Windows Python Launcher)
$python = Get-Command py -ErrorAction SilentlyContinue
if (-not $python) {
  Write-Host "Python bulunamadı. Lütfen Python 3.9+ yükleyin." -ForegroundColor Red
  exit 1
}

$env:VARYANT_KLASORU = "\\192.168.1.36\TasarımVeSablonuOlanDesenler\VARYANT - Şablonu Olan Desenler"
$env:DESEN_KLASORU = "\\192.168.1.36\TasarımVeSablonuOlanDesenler\Karakoç Tasarımlar"
Write-Host "VARYANT_KLASORU: $env:VARYANT_KLASORU"
Write-Host "DESEN_KLASORU: $env:DESEN_KLASORU"

# Ensure uvicorn installed
py -c "import uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "uvicorn kuruluyor..." -ForegroundColor Yellow
  py -m pip install --upgrade pip | Out-Null
  py -m pip install uvicorn fastapi | Out-Null
}

Write-Host "Servis başlatılıyor: http://0.0.0.0:8001" -ForegroundColor Green
Write-Host "Network erişimi aktif - tüm kullanıcılar erişebilir" -ForegroundColor Cyan
py -m uvicorn variants_api:app --host 0.0.0.0 --port 8001 --reload
