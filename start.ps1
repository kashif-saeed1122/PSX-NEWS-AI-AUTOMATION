# PSX Dashboard — Start both backend and frontend
# Run: .\start.ps1

Write-Host "Starting PSX Automation Dashboard..." -ForegroundColor Cyan
Write-Host ""

# Start FastAPI backend in background
Write-Host "[1/2] Starting backend (FastAPI) on http://localhost:8000 ..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& {Set-Location '$PSScriptRoot'; .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload}" -WindowStyle Normal

Start-Sleep -Seconds 2

# Start React frontend
Write-Host "[2/2] Starting frontend (Vite) on http://localhost:5173 ..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& {Set-Location '$PSScriptRoot\frontend'; npm run dev}" -WindowStyle Normal

Write-Host ""
Write-Host "Dashboard ready at: http://localhost:5173" -ForegroundColor Green
Write-Host "API running at:     http://localhost:8000" -ForegroundColor Green
Write-Host ""
Write-Host "Default login: admin / admin123" -ForegroundColor Cyan
Write-Host "(or set ADMIN_USERNAME / ADMIN_PASSWORD in .env)" -ForegroundColor Gray
