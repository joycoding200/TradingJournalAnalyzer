# TradingJournalAnalyzer — 交易日志分析器

上传交割单，AI 分析亏损原因并生成改善建议。A 股散户 + 期货散户的交易行为诊断工具。

**核心卖点：What If 反事实回测** — 删除特定行为后回测账户收益变化，量化每种行为对账户的伤害程度。

License: MIT + Commons Clause

This project is open source for non-commercial use only.

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | Vite + React 18 + Tailwind CSS + Recharts + React Query |
| 后端 | FastAPI + SQLAlchemy + Pandas |
| AI | OpenAI / Claude / DeepSeek（环境变量切换） |
| 数据库 | PostgreSQL 17 |
| 行情数据 | [a-stock-data](https://github.com/simonlin1212/a-stock-data)（mootdx + 腾讯优先，不封 IP） |

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+
- PostgreSQL 17

### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 创建数据库
psql -U postgres -c "CREATE DATABASE tradelens;"

# 配置环境变量
cp .env.example .env  # 编辑 .env 填入数据库连接和 AI API Key

# 启动
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173

### 运行测试

```bash
# 后端单元测试（222 个）
cd backend && pytest tests/ -q

# API 契约测试（56 个断言，无需浏览器）
python e2e/api_contract_tests.py

# E2E 用户流程测试（Playwright，需前后端均已启动）
python e2e/user_flow_e2e.py
```

## 核心架构：6 层数据管道

```
原始交割单 → Trade → Position → Pattern → Insight Engine → What If Engine → AI 解释器 → 验证层 → 诊断报告
```

1. **Trade** — 15+ 券商/期货终端格式统一解析
2. **Position** — FIFO 算法重建完整交易
3. **Pattern** — 15 个行为标签（追涨、抄底、突破、止损、做T…）
4. **Insight Engine** — 各行为胜率/收益率统计排名
5. **What If Engine** — 反事实回测，量化行为伤害程度
6. **AI 解释器 + 验证层** — 自然语言报告 + 数字校验（最多 3 次重试）

## 支持的券商/终端

| 类别 | 来源 |
|------|------|
| A 股 API 终端 | QMT、VN.PY、东方财富、同花顺 |
| 期货终端 | 文华财经、博易大师、CTP/快期/易盛 |
| 券商 APP | 华泰涨乐、中信信e投、国君君弘、广发易淘金、海通e海通财… |

## 项目结构

```
TradingJournalAnalyzer/
├── backend/
│   ├── app/
│   │   ├── api/          # REST 端点 (auth, upload, analysis, report)
│   │   ├── engine/        # 计算引擎 (position, pattern, insight, whatif)
│   │   ├── parsers/       # 解析器插件 (9 个)
│   │   ├── ai/            # AI 层 (provider, prompt, validator)
│   │   ├── models/        # SQLAlchemy 模型 (7 张表)
│   │   └── auth/          # JWT 认证
│   └── tests/             # 222 个单元测试
├── frontend/
│   └── src/
│       ├── pages/         # 7 个页面
│       ├── components/    # UI 组件
│       └── api/           # API 客户端
├── e2e/                   # E2E + 契约测试
└── docs/                  # 设计文档
```

## 设计原则

**AI 负责解释，程序负责计算。** 所有数字由 Python 计算，AI 只做自然语言文本生成。报告中的每个数字都经过验证层提取比对。

## License

MIT
