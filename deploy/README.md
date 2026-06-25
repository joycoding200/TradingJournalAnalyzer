# TradingJournalAnalyzer 部署指南

## 你的环境

- 阿里云轻量应用服务器 + 宝塔面板
- 前端：本地构建 → rsync 上传 → nginx 托管 dist/ 静态文件
- 后端：systemd service 托管 FastAPI（uvicorn）
- Nginx：80 端口统一入口（静态文件 + /api 反代）
- 数据库：PostgreSQL 17
- 代码仓库：GitHub

## 文件说明

```
deploy/
├── local-deploy.sh    # 【推荐】日常部署：本地 build + rsync 全量代码 + SSH 更新
├── update.sh          # 服务器端更新：pip install + 备份 + alembic + 重启 + 健康检查
├── server-setup.sh    # 首次安装：一键配好 PG + Python + venv + systemd
├── init-admin.sh      # 管理员账户初始化（shell 包装）
├── init-admin.py      # 管理员账户初始化（Python 实现）
├── nginx-tja.conf     # Nginx 配置模板
├── config-check.sh    # 生产配置校验：6 维检查
├── deploy.yml         # GitHub Actions 自动部署（可选）
├── local-push.sh      # 【废弃】旧版方案，不再使用
└── README.md          # 本文件
```

## 首次部署（从零开始）

### 前提：服务器已有宝塔面板

### 步骤 1：SSH 到服务器，执行首次安装

```bash
ssh root@你的服务器IP

# 克隆项目（首次需要一次 git clone）
cd /opt
git clone https://github.com/joycoding200/TradingJournalAnalyzer.git
cd TradingJournalAnalyzer

# 执行首次安装脚本
bash deploy/server-setup.sh
```

这个脚本会自动完成：
1. 安装系统依赖（Python、编译工具、rsync）
2. 安装 PostgreSQL 17
3. 创建数据库 tradelens 和用户
4. 创建 Python 虚拟环境 + 安装后端依赖
5. 生成 backend/.env（含随机密钥）
6. 初始化数据库表
7. 创建 systemd 服务
8. 启动后端并健康检查

安装完成后，脚本会输出数据库密码和后续步骤提示。

### 步骤 2：配置 .env

```bash
vim /opt/TradingJournalAnalyzer/backend/.env
```

确认以下配置（脚本已自动生成，你只需补填 API Key）：

| 配置项 | 值 | 说明 |
|--------|-----|------|
| DATABASE_URL | postgresql://tradelens:***@localhost:5432/tradelens | 脚本已生成 |
| SECRET_KEY | 64 字符随机串 | 脚本已生成 |
| CORS_ORIGINS | http://服务器IP | 脚本已生成 |
| AI_PROVIDER | deepseek | 脚本已设置 |
| DEEPSEEK_API_KEY | 你的 Key | **需要手动填入** |

### 步骤 3：创建管理员账户

```bash
cd /opt/TradingJournalAnalyzer
ADMIN_PASSWORD=你的密码123 bash deploy/init-admin.sh --email admin@你的邮箱.com
```

### 步骤 4：配置 Nginx

宝塔面板 → 网站 → 添加站点
- 域名填：你的服务器 IP（或域名）
- 根目录设为：`/opt/TradingJournalAnalyzer/frontend/dist`
- 设置 → 反向代理 → 添加：
  - 代理名称：tja-api
  - 目标URL：`http://127.0.0.1:8000`
  - 发送域名：`$host`
- 设置 → 配置文件，在 location / 下添加：
  ```nginx
  location / {
      try_files $uri $uri/ /index.html;
  }
  ```

### 步骤 5：配置 SSH 免密

```bash
# 本地电脑执行
ssh-keygen -t ed25519   # 已有则跳过
ssh-copy-id root@你的服务器IP
```

### 步骤 6：验证

```bash
curl http://localhost/api/health
# 应返回 {"status":"ok"}

# 浏览器打开
http://你的服务器IP/
```

---

## 日常更新流程

### 方式 1：（推荐）本地构建 + rsync 全量代码

SSH 免密配置好后，本地改完代码，一条命令：

```bash
bash deploy/local-deploy.sh
```

**工作流程：**
1. 本地 `npm run build` 构建前端
2. `rsync -avz --delete` 同步整个项目（含源码+dist/）到服务器
   - 自动排除：`.git`、`node_modules`、`.venv`、`uploads/`、`.env`
3. SSH 触发服务器 `update.sh`：
   - pip install（更新 Python 依赖）
   - pg_dump 备份数据库（保留最近 7 份）
   - alembic upgrade head（数据库迁移）
   - systemctl restart tja-backend（重启后端）
   - 健康检查（最多等 20 秒）

**特点：** 服务器不需要 Node.js，不需要 git pull，从本地同步完整代码。

可选参数：
```bash
bash deploy/local-deploy.sh --skip-build  # dist/ 已是最新，跳过构建
bash deploy/local-deploy.sh --dry-run     # 只查看将同步的文件，不实际执行
```

### 方式 2：GitHub Actions 全自动

1. GitHub 仓库 Settings → Secrets → Actions，添加：
   - SSH_HOST：服务器 IP
   - SSH_USER：SSH 用户名
   - SSH_KEY：SSH 私钥全文
   - PROJECT_PATH：服务器项目路径

2. 复制 workflow 文件：
```bash
mkdir -p .github/workflows
cp deploy/deploy.yml .github/workflows/deploy.yml
```

3. push 到 main 分支自动触发：
   - GitHub Action 会 SSH 到服务器执行 `update.sh`
   - 注意：`update.sh` 不再包含 git pull，需提前通过 rsync 同步代码

---

## 服务器上脚本不会碰的配置

### 1. backend/.env
.env 被 rsync 排除（`--exclude='.env'`），生产配置安全。

### 2. 管理员账户
手动创建的 admin 用户。如需重置密码：
```bash
bash deploy/init-admin.sh --email admin@你的邮箱.com --password 新密码456 --update
```

### 3. uploads/ 目录
用户上传的交割单文件，rsync 排除，不会丢失。

---

## 可选操作

### 配置校验
```bash
bash deploy/config-check.sh
```
检查 6 个维度：.env、关键配置项、AI 配置、数据库连接、管理员账户、systemd 服务。

### 数据库备份
update.sh 已自动在每次迁移前备份到 `/opt/backups/`，保留最近 7 个。

手动备份：
```bash
pg_dump -U postgres tradelens > backup_$(date +%Y%m%d).sql
```

自动备份（crontab -e）：
```
0 2 * * * pg_dump -U postgres tradelens > /opt/backups/tradelens_$(date +\%Y\%m\%d).sql
```

### HTTPS 配置

宝塔面板 → 网站 → 你的站点 → SSL → Let's Encrypt → 申请

---

## 防火墙

宝塔面板 → 安全 → 放行端口：
- 80（HTTP）
- 443（HTTPS，如配了 SSL）
- 22（SSH）

**不要**放行 8000 端口（后端只通过 nginx 反代访问）。
