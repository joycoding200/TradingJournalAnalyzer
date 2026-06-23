#!/bin/bash
# TradingJournalAnalyzer 重启脚本
# 用法: bash restart.sh
# 默认端口: 后端 8001, 前端 5173

BACKEND_PORT=8000
FRONTEND_PORT=5173
ROOT="/d/Dev/Projects/TradingJournalAnalyzer"

echo "=== 重启 TradingJournalAnalyzer ==="

# 1. 释放端口 (用 Python 调用 netstat，兼容 Git Bash)
echo "[1/3] 释放端口..."
python -c "
import subprocess
r = subprocess.run(['netstat','-ano'], capture_output=True, text=True)
for port in ['$BACKEND_PORT', '$FRONTEND_PORT']:
    for l in r.stdout.split('\n'):
        if f':{port} ' in l and 'LISTENING' in l:
            pid = l.strip().split()[-1]
            subprocess.run(['taskkill','/F','/PID', pid], capture_output=True)
            print(f'  :{port} PID={pid} killed')
print('  done')
"
sleep 1

# 2. 后端
echo "[2/3] 启动后端 :$BACKEND_PORT..."
cd "$ROOT/backend"
source .venv/Scripts/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT > /dev/null 2>&1 &
echo "  PID=$!"

# 3. 前端
echo "[3/3] 启动前端 :$FRONTEND_PORT..."
cd "$ROOT/frontend"
npm run dev -- --port $FRONTEND_PORT > /dev/null 2>&1 &
echo "  PID=$!"

# 等后端就绪
for i in $(seq 1 15); do
    curl -s "http://localhost:$BACKEND_PORT/api/health" > /dev/null 2>&1 && break
    sleep 0.5
done

echo ""
echo "  http://localhost:$FRONTEND_PORT  ← 前端"
echo "  http://localhost:$BACKEND_PORT/api/health  ← 后端"
echo "=== 完成 ==="
