# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

TradeLens（交易日志分析器）— 上传交易记录，AI 分析亏损原因并生成改善建议。目标用户为 A 股散户。

## 技术栈

- **前端**: Next.js + Tailwind CSS + shadcn/ui
- **后端**: FastAPI (Python) + Pandas + Polars
- **AI**: OpenAI / Claude / DeepSeek（可切换）
- **数据库**: PostgreSQL
- **部署**: Vercel（前端）/ Railway（后端）

## 核心架构（6层数据管道）

AI 只占最后 10%，核心是数据管道：

```
原始交割单 → Trade → Position → Pattern → Insight Engine → What If Engine → AI 解释器
```

1. **Trade（成交记录）** — 原始数据统一格式。多券商 CSV/Excel 导入，统一为标准 Trade schema（trade_id, account_id, datetime, symbol, side, quantity, price, commission）。**必须永远保存 raw_file 原始数据。**

2. **Position（持仓重建）** — 将离散的买卖记录重建为完整交易（entry_date, exit_date, holding_days, avg_entry_price, avg_exit_price, pnl, pnl_pct）。后续所有分析都基于 Position。

3. **Pattern（行为标签）** — 为每笔交易打标签。MVP 只做 10 个：CHASE（追涨）、BOTTOM（抄底）、BREAKOUT（突破）、TREND（趋势）、COUNTER_TREND（逆势）、SCALP（短线 <3天）、SWING（波段 3-30天）、POSITION（长持 >30天）、PYRAMID（加仓）、AVERAGE_DOWN（补仓）。

4. **Insight Engine（归因引擎）** — 统计每种行为标签的胜率、收益率，找出 best_pattern 和 worst_pattern。

5. **What If Engine（反事实回测）** — 核心卖点功能。删除特定行为标签后回测账户收益变化，量化每种行为对账户的伤害程度。

6. **AI 层** — 接收归因数据，生成《交易行为诊断书》（优势、劣势、最危险行为、改善建议）。不预测市场，不推荐股票。

## 核心设计原则

**AI 负责解释，程序负责计算。** 先把交割单兼容、Position 重建和 What If 回测做扎实，AI 只做最后一层的自然语言报告生成。

## 开发命令

项目尚未初始化。预期命令：

```bash
# 后端
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
pytest

# 前端
cd frontend
npm install
npm run dev
npm run build
npm run lint
```

## V1 MVP 范围（2周）

- 上传交割单（CSV/Excel），支持拖拽
- 自动识别券商格式（QMT、VN.PY、东方财富、同花顺），统一清洗
- 交易统计（总次数、胜率、盈亏比、最大盈/亏、平均持仓天数、连续亏损次数）
- 最赚钱行为 / 最亏钱行为
- What If 回测
- AI 生成一句话核心结论
