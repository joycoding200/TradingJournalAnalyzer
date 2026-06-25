#!/bin/bash
# ============================================================
# TradingJournalAnalyzer — 本地构建 + rsync 全量代码部署
# ============================================================
# 用法：
#   bash deploy/local-deploy.sh                 # 完整流程
#   bash deploy/local-deploy.sh --skip-build    # 跳过 npm build
#   bash deploy/local-deploy.sh --dry-run       # 只显示 rsync 影响不实际执行
#
# 工作流程：
#   1. 本地构建前端 → 2. rsync 整个项目（含源码+dist）到服务器
#   → 3. SSH 触发服务器端更新（pip install + 备份 + alembic + 重启 + 健康检查）
# ============================================================
set -euo pipefail

# ============ 配置区 ============
SERVER_USER="root"
SERVER_HOST="47.109.159.232"
PROJECT_PATH="/opt/TradingJournalAnalyzer"
# ================================

G='\033[0;32m'; Y='\033[0;33m'; R='\033[0;31m'; B='\033[0;34m'; N='\033[0m'
log()  { echo -e "${G}[deploy]${N} $1"; }
warn() { echo -e "${Y}[warn]${N} $1"; }
err()  { echo -e "${R}[error]${N} $1"; }
step() { echo -e "${B}[${1}]${N} $2"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
START_TIME=$SECONDS

# 解析参数
SKIP_BUILD=false
DRY_RUN=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-build) SKIP_BUILD=true; shift ;;
        --dry-run)    DRY_RUN=true; shift ;;
        *) err "未知参数: $1"; exit 1 ;;
    esac
done

# ---- 1. 本地构建前端 ----
if [ "$SKIP_BUILD" = false ]; then
    step "1/3" "本地构建前端..."
    cd "$PROJECT_DIR/frontend"
    if [ ! -d node_modules ]; then
        log "安装 npm 依赖..."
        npm install
    fi
    log "VITE_API_BASE 不设置，前端走相对路径，依赖 nginx /api 反代"
    npm run build
    cd "$PROJECT_DIR"
    log "前端构建完成: frontend/dist/"
else
    step "1/3" "跳过前端构建（使用已有 dist/）"
fi
echo ""

# ---- 2. rsync 整个项目到服务器 ----
step "2/3" "同步代码到服务器..."
SSH_TARGET="${SERVER_USER}@${SERVER_HOST}:${PROJECT_PATH}/"

RSYNC_EXCLUDES=(
    --exclude='.git'
    --exclude='__pycache__'
    --exclude='*.pyc'
    --exclude='*.pyo'
    --exclude='frontend/node_modules'
    --exclude='backend/.venv'
    --exclude='backend/venv'
    --exclude='backend/uploads'      # 用户数据，不过期
    --exclude='.env'                 # 生产环境配置，不覆盖
    --exclude='.claude'
)

if [ "$DRY_RUN" = true ]; then
    log "DRY RUN — 仅列出会被同步的文件："
    rsync -avz --delete --dry-run \
        "${RSYNC_EXCLUDES[@]}" \
        "$PROJECT_DIR/" \
        "$SSH_TARGET" \
        | grep -v '/$' | head -50
    echo "    ..."
    log "DRY RUN 完成，未实际传输"
    exit 0
fi

rsync -avz --delete \
    "${RSYNC_EXCLUDES[@]}" \
    "$PROJECT_DIR/" \
    "$SSH_TARGET"

log "代码同步完成"

# 检查服务器端 deploy/update.sh 是否存在
if ssh "${SERVER_USER}@${SERVER_HOST}" "test -f ${PROJECT_PATH}/deploy/update.sh"; then
    log "服务器端 update.sh 存在"
else
    err "服务器上找不到 ${PROJECT_PATH}/deploy/update.sh！"
    echo "  请先手动在服务器上创建项目目录并上传初始代码"
    exit 1
fi
echo ""

# ---- 3. SSH 触发服务器端更新 ----
step "3/3" "触发服务器端更新..."
ssh "${SERVER_USER}@${SERVER_HOST}" \
    "bash ${PROJECT_PATH}/deploy/update.sh"

ELAPSED=$((SECONDS - START_TIME))
echo ""
log "部署完成！耗时 ${ELAPSED}s"
log "  前端构建: $([ "$SKIP_BUILD" = true ] && echo '跳过' || echo '已构建')"
log "  代码同步: rsync 全量（排除 node_modules/.venv/uploads/.env/.git）"
log "  服务端:   pip install + 备份 + alembic + 重启 + 健康检查"
