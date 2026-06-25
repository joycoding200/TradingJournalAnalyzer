#!/bin/bash
# ============================================================
# TradingJournalAnalyzer — 服务器端更新脚本
# ============================================================
# 由本地 deploy/local-deploy.sh SSH 触发，在服务器端执行。
# 代码已通过 rsync 同步到服务器，此脚本只做后端更新操作。
#
# 用法：
#   bash deploy/update.sh
#
# 或从本地通过 SSH 触发（由 local-deploy.sh 自动执行）：
#   ssh root@server "bash /opt/TradingJournalAnalyzer/deploy/update.sh"
# ============================================================
set -euo pipefail

# ============ 配置区 ============
SERVICE_NAME="tja-backend"
HEALTH_URL="http://localhost/api/health"
BACKUP_DIR="/opt/backups"
# ================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

G='\033[0;32m'; Y='\033[0;33m'; R='\033[0;31m'; B='\033[0;34m'; N='\033[0m'
log()  { echo -e "${G}[update]${N} $1"; }
warn() { echo -e "${Y}[warn]${N} $1"; }
err()  { echo -e "${R}[error]${N} $1"; }
step() { echo -e "${B}[${1}]${N} $2"; }

START_TIME=$SECONDS

# ============================================================
# 前置检查
# ============================================================
step "1/6" "前置检查..."

# 1a. backend/.env 必须存在
if [ ! -f "backend/.env" ]; then
    err "backend/.env 不存在！服务器无法启动。"
    echo "  请从 .env.example 复制并填入生产环境配置："
    echo "  cp backend/.env.example backend/.env && vim backend/.env"
    exit 1
fi
log "  backend/.env 存在"

# 1b. backend/uploads/ 目录存在
if [ ! -d "backend/uploads" ]; then
    warn "  backend/uploads/ 不存在，创建中..."
    mkdir -p backend/uploads
    chmod 755 backend/uploads
fi

# 1c. 前端 dist/ 必须存在（由 local-deploy.sh rsync 上传）
if [ ! -d "frontend/dist" ]; then
    err "  frontend/dist/ 不存在！请先执行 local-deploy.sh 上传前端"
    exit 1
fi
log "  frontend/dist/ 存在"
echo ""

# ============================================================
# 后端依赖
# ============================================================
step "2/6" "同步后端依赖..."
cd backend
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
elif [ -f venv/bin/activate ]; then
    source venv/bin/activate
else
    err "未找到虚拟环境！请先创建: python3 -m venv .venv"
    exit 1
fi
pip install -r requirements.txt --quiet 2>&1 | tail -5
cd "$PROJECT_DIR"
echo ""

# ============================================================
# 迁移前数据库备份
# ============================================================
step "3/6" "数据库备份..."
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="${BACKUP_DIR}/tradelens_$(date +%Y%m%d_%H%M%S).sql"
DB_URL=$(grep -E "^DATABASE_URL=" backend/.env 2>/dev/null | cut -d= -f2- || echo "")
if [ -n "$DB_URL" ] && command -v pg_dump &>/dev/null; then
    if pg_dump "$DB_URL" > "$BACKUP_FILE" 2>/dev/null; then
        FILESIZE=$(du -h "$BACKUP_FILE" | cut -f1)
        log "  备份完成: ${BACKUP_FILE} (${FILESIZE})"
        # 保留最近 7 个备份
        ls -t "${BACKUP_DIR}"/tradelens_*.sql 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null || true
    else
        warn "  数据库备份失败（非致命，继续部署）"
    fi
else
    warn "  跳过备份（pg_dump 不可用或 DATABASE_URL 未设置）"
fi
echo ""

# ============================================================
# 数据库迁移
# ============================================================
step "4/6" "数据库迁移..."
cd backend
source .venv/bin/activate

if command -v alembic &>/dev/null && [ -d "alembic" ]; then
    # 检查 alembic_version 表是否存在（服务器之前可能用 create_all 而非迁移建表）
    ALEMBIC_STAMPED=$(python -c "
from app.config import settings
from sqlalchemy import create_engine, inspect
engine = create_engine(settings.database_url)
insp = inspect(engine)
print('yes' if 'alembic_version' in insp.get_table_names() else 'no')
" 2>/dev/null || echo "unknown")

    if [ "$ALEMBIC_STAMPED" = "no" ]; then
        log "  alembic_version 表不存在 — 执行 alembic stamp head..."
        alembic stamp head
    fi
    alembic upgrade head || warn "Alembic 迁移失败，请手动检查: alembic upgrade head"
else
    echo "  跳过（未安装 Alembic 或无迁移目录）"
fi
cd "$PROJECT_DIR"
echo ""

# ============================================================
# 重启后端
# ============================================================
step "5/6" "重启后端服务..."
systemctl restart "$SERVICE_NAME"
echo ""

# ============================================================
# 健康检查
# ============================================================
step "6/6" "健康检查..."
READY=false
for i in $(seq 1 20); do
    if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
        ELAPSED=$((SECONDS - START_TIME))
        log "服务就绪！耗时 ${ELAPSED}s"
        READY=true
        break
    fi
    printf "."
    sleep 1
done
echo ""

if [ "$READY" = false ]; then
    err "服务未在 20 秒内就绪，排查命令："
    echo "  systemctl status $SERVICE_NAME"
    echo "  journalctl -u $SERVICE_NAME -n 50"
    echo "  如需回滚迁移: cd backend && source .venv/bin/activate && alembic downgrade -1"
    exit 1
fi

# 摘要
echo ""
log "更新完成！"
echo "  耗时:   $((SECONDS - START_TIME))s"
echo "  备份:   ${BACKUP_FILE:-无}"
echo ""
echo "  提示："
echo "    查看日志:   journalctl -u $SERVICE_NAME -f"
echo "    管理员账户: bash deploy/init-admin.sh"
echo "    配置检查:   bash deploy/config-check.sh"
