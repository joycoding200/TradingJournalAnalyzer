# TradeDoctor dev restart script
# Usage: .\restart.ps1

$ErrorActionPreference = "Stop"

$BACKEND_PORT = 8000
$FRONTEND_PORT = 5173
$ROOT = $PSScriptRoot

$PYTHON = "$ROOT\backend\.venv\Scripts\python.exe"
$LOG_DIR = "$ROOT\.tmp"
New-Item -Force -ItemType Directory $LOG_DIR | Out-Null

function ok($msg)   { Write-Host "  " -NoNewline; Write-Host "[ok]" -ForegroundColor Green -NoNewline; Write-Host " $msg" }
function fail($msg) { Write-Host "  " -NoNewline; Write-Host "[fail]" -ForegroundColor Red -NoNewline; Write-Host " $msg" }

Write-Host "=== Restarting TradeDoctor (dev) ==="

# 1. Kill existing processes on target ports
Write-Host "[1/3] Freeing ports $BACKEND_PORT $FRONTEND_PORT ..."
& $PYTHON -c @"
import subprocess
r = subprocess.run(['netstat','-ano'], capture_output=True, text=True)
for port in ['8000', '5173']:
    for line in r.stdout.split('\n'):
        if f':{port} ' in line and 'LISTENING' in line:
            pid = line.strip().split()[-1]
            subprocess.run(['taskkill','/F','/PID', pid], capture_output=True)
            print(f'  :{port} PID={pid} killed')
print('  done')
"@
Start-Sleep 1

# 2. Start backend (cmd /c merges stderr into stdout)
Write-Host "[2/3] Starting backend :$BACKEND_PORT ..."
Push-Location "$ROOT\backend"
$backendJob = Start-Process -NoNewWindow -PassThru -FilePath "cmd" `
    -ArgumentList "/c","$PYTHON -m uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT > `"$LOG_DIR\backend.log`" 2>&1"
Pop-Location
ok "PID=$($backendJob.Id)  log: $LOG_DIR\backend.log"

# 3. Start frontend
Write-Host "[3/3] Starting frontend :$FRONTEND_PORT ..."
Push-Location "$ROOT\frontend"
$frontendJob = Start-Process -NoNewWindow -PassThru -FilePath "cmd" `
    -ArgumentList "/c","npm run dev -- --port $FRONTEND_PORT > `"$LOG_DIR\frontend.log`" 2>&1"
Pop-Location
ok "PID=$($frontendJob.Id)  log: $LOG_DIR\frontend.log"

# 4. Wait for backend to be ready (curl.exe bypasses PowerShell proxy)
Write-Host ""
Write-Host -NoNewline "  Waiting for backend"
$ready = $false
for ($i = 1; $i -le 20; $i++) {
    $result = curl.exe -s -o NUL -w "%{http_code}" "http://localhost:$BACKEND_PORT/api/health" 2>$null
    if ($result -eq "200") {
        Write-Host ""
        ok "Backend ready"
        $ready = $true
        break
    }
    Write-Host -NoNewline "."
    Start-Sleep 0.5
}

if (-not $ready) {
    fail "Backend did not start within 10s, check log: $LOG_DIR\backend.log"
    exit 1
}

Write-Host ""
Write-Host "  http://localhost:${FRONTEND_PORT}  <- Frontend"
Write-Host "  http://localhost:${BACKEND_PORT}/api/health  <- Backend health"
Write-Host "  Logs: $LOG_DIR"
Write-Host "=== Done ==="
