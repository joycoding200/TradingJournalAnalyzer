# 代码全面审查报告

> 审查日期: 2026-06-23
> 审查范围: 全项目（后端 46 源文件 + 前端 39 源文件 + 测试套件）
> 审查维度: 金融专业领域正确性 + 软件工程（安全/性能/可维护性）
> 审查标准: 对照 FINANCE_DOMAIN.md、VERIFICATION_CHECKLIST.md、PROJECT_EXPERIENCE.md

---

## 整体印象

项目架构清晰，6 层数据管道（Trade → Position → Pattern → Insight → What-If → AI 诊断）设计合理。核心金融指标（PF、Expectancy、Max Drawdown、Profit Capture Ratio）的计算公式与 FINANCE_DOMAIN.md 定义一致，边界处理（平本交易归入亏损、cost_known 过滤、零分母保护）落实到位。代码注释质量高，关键决策有详细说明。AI Prompt 防幻觉机制设计周到。

发现阻塞项 3 个、建议项 14 个、小改进 8 个，详见下文。

---

## 一、金融领域审查

### 1.1 指标计算验证

| 指标 | 文件 | 验证结果 |
|------|------|----------|
| 胜率 | analysis.py:240 | ✅ win_count/valid_count，pnl>0 判盈利，pnl<=0 判亏损（含平本），与 FINANCE_DOMAIN.md §1 一致 |
| 总盈亏 | analysis.py:242 | ✅ sum(p.pnl)，已扣除双边手续费 |
| 总收益率 | analysis.py:342 | ✅ total_pnl/total_invested，total_invested=sum(avg_entry_price×total_quantity) |
| 盈亏比(PF) | analysis.py:328-333 | ✅ gross_profit/gross_loss，非 win_rate/(1-win_rate)；零亏损返回 None(→∞) |
| 预期收益 | insight.py:25-33 | ✅ win_rate×avg_win_pct - (1-win_rate)×avg_loss_pct，使用 pnl_pct 不用绝对金额 |
| 损益比 | analysis.py:326 | ✅ avg_win_amount/abs(avg_loss_amount)，零亏损返回 None |
| 最大回撤 | analysis.py:351-377 | ✅ 遍历 sorted_positions 跟踪 peak；同时输出绝对值+百分比；peak=0 时回退到 total_invested 作分母 |
| 止盈效率 | mae.py:103-110 | ✅ mean(pnl_pct/mfe_pct) per-position，非 sum/sum；过滤 MFE≤0.001 防畸变 |
| MAE/MFE | mae.py:18-67 | ✅ 基于日线 low/high，min((bar_low-entry)/entry) / max((bar_high-entry)/entry) |
| 连续亏损 | analysis.py:195-210 | ✅ pnl<=0 计入连亏，按 exit_date 排序 |
| 止损回测 | whatif.py:140-193 | ✅ 检查持仓期间日线 low；跳空低开 fill_price=min(open,stop)；扣除佣金保持一致性 |

### 1.2 行为标签验证

| 标签 | 文件 | 验证结果 |
|------|------|----------|
| BULL_TREND/BEAR_TREND | pattern.py:532-546 | ✅ MA20 vs MA60 + price 确认，归入 market_env 维度 |
| CHASE | pattern.py:418-446 | ✅ 5日涨幅>15% + MA20×1.10 + 20日高点×0.97，三条件全满足才标记 |
| BOTTOM | pattern.py:469-488 | ✅ 5日跌幅>15% + MA20<MA60（下跌趋势确认） |
| BREAKOUT | pattern.py:490-530 | � entry_close>20日最高价 + 成交量×1.5；无量数据时置信度降至0.5 |
| PYRAMID | pattern.py:168-198 | ✅ 交易级：加仓价>首次买入均价×1.02 + 验证已有持仓在开 |
| AVERAGE_DOWN (主路径) | pattern.py:200-220 | ✅ 交易级：加仓价<首次买入均价×0.95 + 验证亏损状态(is_loss_add) |
| TURN | pattern.py:251-287 | ✅ 同日有买卖（做T） |
| SCALP/SWING/POSITION | pattern.py:130-153 | ✅ <3天/3-30天/>30天 |
| FOMO | pattern.py:448-467 | ✅ 5日内≥3天上涨 + 入场价≥当日最高×0.98 |
| TIGHT_STOP | pattern.py:291 | ✅ 亏损2-5% + 持仓≤3天 |
| TRAILING_STOP | pattern.py:300 | ✅ 持仓>10天 + 0<盈利≤10% |
| TIME_EXIT | pattern.py:309 | ✅ 持仓>30天 + |盈亏|<5% |
| LARGE_LOSS_EXIT | pattern.py:318 | ✅ 亏损>20% |

### 1.3 数据隔离验证

| 检查项 | 文件 | 结果 |
|--------|------|------|
| cost_known=False 排除 | analysis.py:236, insight.py:106, attribution.py:41, whatif.py:41 | ✅ 所有统计路径均过滤 |
| is_deleted 软删除 | common.py:68 | ✅ load_trades 查询过滤 is_deleted=False |
| 小样本标记 | analysis.py:238 | ✅ is_small_sample = valid_count < 5 |
| 净值曲线起点 | analysis.py:358-363 | ✅ 首点 {exit_date, 0.0, 0.0} |
| symbol_summary 口径 | analysis.py:272-295 | ✅ 仅统计 valid_positions |

---

## 二、问题清单

### 🔴 阻塞项（必须修复）

#### B1. AVERAGE_DOWN 回退路径未验证亏损状态
- **文件**: `backend/app/engine/pattern.py` 第 239-249 行
- **问题**: 当 `all_trades` 未提供时，AVERAGE_DOWN 回退路径仅检查 `pos.avg_entry_price < first.avg_entry_price * 0.95`，未验证前序持仓是否处于亏损状态
- **违反**: FINANCE_DOMAIN.md §二 AVERAGE_DOWN 定义："已有**亏损**持仓时以更低价格加仓"
- **影响**: 正常回调后加仓可能被误标为"摊薄补仓"，导致行为分析失真
- **注意**: 当前 API 代码路径（analysis.py `_build_category_map`）始终传入 `all_trades`，因此实际运行时不触发回退。但回退路径作为公共 API 的一部分，存在被其他调用方触发的风险
- **建议**: 在回退路径中增加持仓状态检查，或标注该路径为 deprecated 并在文档中声明必须传入 all_trades

#### B2. stats/insight/whatif 端点无速率限制
- **文件**: `backend/app/api/analysis.py` 第 213、514、589 行
- **问题**: `get_stats`、`get_insight`、`get_whatif` 三个端点执行重量级计算（持仓重建 + 行情拉取 + 模式标注 + Shapley 蒙特卡洛），但均无 `@limiter.limit` 装饰器
- **影响**: 认证用户可通过高频请求消耗服务器 CPU 和数据库连接池，构成 DoS 向量
- **对比**: `run_analysis`(10/min)、`upload_file`(10/min)、`register`(5/min)、`login`(5/min) 均有速率限制
- **建议**: 添加 `@limiter.limit("30/minute")` 或类似限制

#### B3. CORS 配置硬编码，生产环境不可用
- **文件**: `backend/app/main.py` 第 69 行
- **问题**: `allow_origins=["http://localhost:5173"]` 硬编码为开发环境地址，部署后前端域名不匹配将被 CORS 拦截
- **建议**: 从环境变量读取，如 `settings.cors_origins`，默认值为 `["http://localhost:5173"]`

---

### 🟡 建议项（应该修复）

#### S1. 登录时序攻击 — 用户枚举风险
- **文件**: `backend/app/api/auth.py` 第 80-87 行
- **问题**: `login` 先查询用户再验密。不存在的用户立即返回（~1ms），存在的用户需 bcrypt 验证（~200ms），时序差异可探测用户是否存在
- **缓解**: 注册接口已用通用错误消息"注册失败，请检查输入"防枚举，但登录接口的时序差异仍存在
- **建议**: 用户不存在时执行一次 dummy bcrypt verify（`verify_password(body.password, "$2b$$dummy_hash")`）以消除时序差异

#### S2. admin.py search_users 存在 N+1 查询
- **文件**: `backend/app/api/admin.py` 第 106-116 行
- **问题**: 对每个用户执行 3 次独立 count 查询（RawFile/Analysis/Report），50 个用户 = 150 次查询
- **建议**: 使用 `func.count` + `outerjoin` 聚合为单次查询，或使用子查询

#### S3. JWT Token 存储在 localStorage
- **文件**: `frontend/src/context/AuthContext.tsx` 第 21 行、`frontend/src/api/client.ts` 第 4 行
- **问题**: Token 存在 localStorage，XSS 攻击可直接读取。httpOnly cookie 不受 XSS 影响
- **权衡**: 当前架构（Bearer token in header）不受 CSRF 影响，且前后端分离场景下 httpOnly cookie 较复杂。可作为中期安全加固项

#### S4. 数据库 URL 默认值含密码占位符
- **文件**: `backend/app/config.py` 第 8 行
- **问题**: `postgresql://postgres:***@localhost:5432/tradelens` 虽然是占位符，但密码出现在源码中可能被误用
- **建议**: 默认值改为不含密码的格式 `postgresql://localhost:5432/tradelens`，强制通过环境变量配置

#### S5. 生产环境使用 create_all 而非迁移工具
- **文件**: `backend/app/main.py` 第 22 行
- **问题**: `Base.metadata.create_all(bind=engine)` 在每次启动时执行，无法处理 schema 变更（新增列/修改列类型）
- **注意**: 代码注释已提到应使用 Alembic，但未实际配置
- **建议**: 配置 Alembic 并在部署流程中用 `alembic upgrade head` 替代

#### S6. _backfill_analysis_files 每次启动都执行
- **文件**: `backend/app/main.py` 第 25、30-59 行
- **问题**: 每次应用启动都执行数据回填 SQL，即使没有需要回填的数据。对于已稳定运行的生产环境，这是不必要的开销
- **建议**: 添加版本标记表或配置项，回填完成后不再执行

#### S7. whatif.py 与 attribution.py 命名易混淆
- **文件**: `backend/app/engine/whatif.py`（含 ProfitAttribution 类）、`backend/app/engine/attribution.py`（含 shapley_attribution 函数）
- **问题**: 文件名与内容语义不直观。"whatif" 通常指假设分析，但文件内是利润归因；"attribution" 通常指归因分析，但文件内是 Shapley 值
- **建议**: 重命名或合并，如将 ProfitAttribution 移入 attribution.py，whatif.py 专注规则回测

#### S8. SmartParser _sample_values 仅采样 20 条
- **文件**: `backend/app/parsers/smart.py` 第 41-43 行
- **问题**: `series.dropna().head(20).tolist()` 仅取前 20 行值进行列类型推断。如果前 20 行不具代表性（如某些列前几行为空或异常），分类可能出错
- **建议**: 改为随机采样或增大样本量到 50-100

#### S9. market_fetcher 全局客户端无线程安全
- **文件**: `backend/app/engine/market_fetcher.py` 第 32-39 行
- **问题**: `_get_client()` 中 `_CLIENT` 的 None 检查和赋值不是原子操作。多个线程同时调用可能创建多个客户端实例
- **缓解**: `_fetch_lock` 保护了 fetch 操作，但 `_get_client()` 本身未加锁
- **建议**: 使用 `threading.Lock()` 保护 `_get_client()`，或使用 `@functools.lru_cache`

#### S10. pattern.py 文件过长（775 行）
- **文件**: `backend/app/engine/pattern.py`
- **问题**: 单文件包含标签定义、持仓标签、市场标签、层级解析、心理推测 5 大功能模块
- **建议**: 按维度拆分为 `pattern_holding.py`、`pattern_market.py`、`pattern_psychology.py`

#### S11. 缺少 Shapley 归因的测试
- **文件**: `backend/tests/` 目录
- **问题**: `shapley_attribution` 函数无单元测试。Monte Carlo 采样的收敛性和公平性（Σ Shapley_i ≈ total_pnl）未被验证
- **建议**: 添加测试验证：1) 各标签 Shapley 值之和 ≈ 总 PnL；2) 单标签场景 Shapley 值 = 总 PnL

#### S12. 缺少 admin API 的测试
- **文件**: `backend/tests/` 目录
- **问题**: admin.py 有 235 行代码、6 个端点，但无任何测试覆盖
- **建议**: 添加 admin 登录、用户搜索、文件下载的集成测试

#### S13. 缺少 market_data/market_fetcher 的测试
- **文件**: `backend/tests/` 目录
- **问题**: 行情数据缓存和拉取逻辑无测试，包括并发锁、分页拉取、均线计算
- **建议**: Mock mootdx 客户端，测试缓存命中/未命中、并发安全、MA 计算正确性

#### S14. compute_outcome 产生非标准标签
- **文件**: `backend/app/engine/pattern.py` 第 87-105 行
- **问题**: `compute_outcome` 产生 BIG_WIN/NORMAL_PROFIT/QUICK_PROFIT/SMALL_LOSS/LARGE_LOSS 标签，这些不在 FINANCE_DOMAIN.md 的标签体系中。标准的 outcome 维度标签是 TIGHT_STOP/TRAILING_STOP/TIME_EXIT/LARGE_LOSS_EXIT
- **影响**: 两套分类系统并存可能导致混淆。`compute_outcome` 用于 `outcome_distribution` 展示，而 outcome 维度标签用于行为分析
- **建议**: 在文档中明确区分两套分类系统的用途，或统一为一套

---

### 💭 小改进

#### M1. 数据库连接池未配置
- **文件**: `backend/app/database.py`
- **现状**: `create_engine(settings.database_url, connect_args=_connect_args)` 使用默认连接池参数
- **建议**: 显式配置 `pool_size`、`max_overflow`、`pool_recycle`，避免长连接超时

#### M2. 错误日志缺失
- **文件**: 多个 API 端点
- **现状**: HTTPException 直接抛出，未记录日志
- **建议**: 添加 `logger.exception()` 记录异常堆栈，便于生产排查

#### M3. 前端 apiGet 错误处理不一致
- **文件**: `frontend/src/api/client.ts` 第 47-51 行
- **问题**: `apiGet` 不解析错误详情（`throw new Error("Request failed")`），而 `apiPost` 和 `apiPut` 会解析 `err.detail`
- **建议**: 统一错误处理逻辑

#### M4. pattern_config.py 在模块加载时读取 YAML
- **文件**: `backend/app/engine/pattern_config.py` 第 8 行
- **问题**: `with open(_yaml_path, ...)` 在模块导入时执行，如果文件不存在会导致整个应用启动失败
- **建议**: 延迟加载或添加异常处理

#### M5. PositionBuilder 有两套构建方法
- **文件**: `backend/app/engine/position.py`
- **问题**: `build()` (FIFO) 和 `build_grouped()` (分组) 两个方法，但 API 只使用 `build()`。`build_grouped()` 可能是遗留代码
- **建议**: 如果不再使用，移除 `build_grouped()` 减少维护负担；如果保留，添加文档说明何时使用

#### M6. 前端无错误边界（Error Boundary）
- **文件**: `frontend/src/App.tsx`
- **问题**: React 组件树无 Error Boundary，渲染错误会导致白屏
- **建议**: 添加 `ErrorBoundary` 组件包裹主要路由

#### M7. AI Provider 重试逻辑缺少指数退避
- **文件**: `backend/app/ai/validator.py` `generate_with_retry` 函数
- **问题**: 重试间隔固定为 1 秒，无指数退避
- **建议**: 使用 `2^attempt` 秒退避，避免对 LLM API 造成突发负载

#### M8. 清空数据端点未见实现
- **文件**: CLAUDE.md 提到"清空数据 = 软删除（is_deleted=True）"
- **问题**: 在 API 层未找到对应的清空数据端点。Trade 模型有 `is_deleted` 字段，但无 API 调用它
- **建议**: 确认是否已实现，或补充实现

---

## 三、值得肯定的设计

1. **PnL 计算扣除双边手续费** — position.py 的 FIFO 匹配正确按比例分摊买卖佣金，回测也保持一致费率基准
2. **平本交易归入亏损** — 全链路口径一致（`pnl <= 0` 判亏损），符合扣费后真实小幅亏损的语义
3. **Profit Capture Ratio 用 per-position 均值** — 避免大 MFE 交易主导聚合，这是比 TradesViz 更精确的做法
4. **最大回撤 peak=0 回退** — 当账户从未盈利时回退到 total_invested 作分母，避免 0/0 的假"优秀"评级
5. **SmartParser 值推断** — 不依赖列名，基于数据特征推断列类型，这是对多券商兼容的正确方向
6. **AI Prompt 防幻觉** — 明确禁止编造日期/股票名/百分比/资金，validator 做软校验不阻断
7. **admin 鉴权双层** — `is_admin` + `scope=admin` 双重验证，文件名 CRLF 注入防护到位
8. **并发锁防行情重复拉取** — `_fetching` set + `_fetch_lock` 防止同一 symbol 并行拉取

---

## 四、修复优先级建议

| 优先级 | 编号 | 工作量 | 影响范围 |
|--------|------|--------|----------|
| P0 | B2 | 3 行代码 | 生产安全 |
| P0 | B3 | 5 行代码 | 生产部署 |
| P1 | B1 | 10 行代码 | 金融正确性 |
| P1 | S1 | 5 行代码 | 安全 |
| P1 | S2 | 20 行代码 | 性能 |
| P2 | S5 | 中等 | 运维 |
| P2 | S7 | 小 | 可维护性 |
| P2 | S11-S13 | 中等 | 测试覆盖 |
| P3 | 其他 | 小 | 代码质量 |
