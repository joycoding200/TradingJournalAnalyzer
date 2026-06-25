#!/bin/bash
# TradeDoctor 重启脚本（开发环境）
# 用法: bash restart.sh
# 环境: Windows Git Bash / PowerShell 中 bash restart.sh

set -euo pipefail

BACKEND_PORT=8000
FRONTEND_PORT=5173
ROOT="$(cd "$(dirname "$0")" && pwd)"

PYTHON="$ROOT/backend/.venv/Scripts/python.exe"
LOG_DIR="$ROOT/.tmp"
mkdir -p "$LOG_DIR"

G='\033[0;32m'; R='\033[0;31m'; N='\033[0m'
ok()  { echo -e "  ${G}[ok]${N} $1"; }
fail() { echo -e "  ${R}[fail]${N} $1"; }

echo "=== 重启 TradeDoctor (开发环境) ==="

# 1. 释放端口
echo "[1/3] 释放端口 $BACKEND_PORT $FRONTEND_PORT ..."
"$PYTHON" -c "
import subprocess
r = subprocess.run(['netstat','-ano'], capture_output=True, text=True)
for port in ['8000', '5173']:
    for line in r.stdout.split('\n'):
        if f':{port} ' in line and 'LISTENING' in line:
            pid = line.strip().split()[-1]
            subprocess.run(['taskkill','/F','/PID', pid], capture_output=True)
            print(f'  :{port} PID={pid} killed')
print('  done')
"
sleep 1

# 2. 启动后端
echo "[2/3] 启动后端 :$BACKEND_PORT ..."
"$PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT \
    > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "  PID=$BACKEND_PID  日志: $LOG_DIR/backend.log"

# 3. 启动前端
echo "[3/3] 启动前端 :$FRONTEND_PORT ..."
cd "$ROOT/frontend"
npm run dev -- --port $FRONTEND_PORT > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "  PID=$FRONTEND_PID  日志: $LOG_DIR/frontend.log"

# 4. 等后端就绪
echo ""
printf "  等待后端就绪"
for i in $(seq 1 20); do
    if curl -sf "http://localhost:$BACKEND_PORT/api/health" > /dev/null 2>&1; then
        echo ""
        ok "后端就绪"
        break
    fi
    printf "."
    sleep 0.5
done

if ! curl -sf "http://localhost:$BACKEND_PORT/api/health" > /dev/null 2>&1; then
    fail "后端未能在 10s 内启动，查看日志: $LOG_DIR/backend.log"
    exit 1
fi

echo ""
echo "  http://localhost:$FRONTEND_PORT  ← 前端"
echo "  http://localhost:$BACKEND_PORT/api/health  ← 后端健康检查"
echo "  日志目录: $LOG_DIR"
echo "=== 完成 ==="
