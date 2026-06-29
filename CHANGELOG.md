# 变更日志

本项目所有重要变更记录在此文件中。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [V1.2.0] — 2026-06-29

### 概述

本版本聚焦 **AI 诊断报告的质量与准确性**。起因：用户上传中信 2025 全年交割单后，发现报告存在"反事实回测方向说反""标签漏报""指标算未喂"三类系统性缺陷。经真实数据离线复算（211 笔成交 → 87 有效持仓）逐项核对后，修复 prompt 表述、补齐输入字段，并建立《AI 输入字段契约》从制度上根治"采集/渲染脱节"。

### 修复的 Bug

#### 1. 反事实回测方向说反（高危）

**现象**：报告称"移除金字塔加仓（PYRAMID）和逆势交易（TURN），收益会分别增加 -0.0391 和 -0.0252（即收益会更高），这些行为在拖累整体表现"。

**根因**：`prompt.py` 喂给 AI 的 `收益变化 {delta:+.4f}` 对 LLM 太暧昧——delta 为负实为"移除后少赚=利润来源"，AI 却读成"收益增加 -0.0391"，动词与负数打架后顺势推了相反结论。真实复算证实 PYRAMID(-0.0375)/TURN(-0.0235) 均为负 delta，是**利润来源**而非拖累；真正的拖累是 AVERAGE_DOWN(+0.0159, -7187元) 和 POSITION(+0.0165)，报告完全没提。

**修复**：whatif 段补判读口径说明——"delta 为负=在帮你赚钱（利润来源），delta 为正=在亏钱（拖累），不可把负数说成收益增加"。

#### 2. 优势/风险清单漏报高效标签

**现象**：报告优势清单只列了 SWING/SIDEWAYS/TRAILING_STOP（按总盈亏绝对额排序），漏掉了单笔均收益最高的 OVERTRADING（+13.08%）和 PSY_FOMO（32笔/+11793）。

**根因**：①SYSTEM_PROMPT 硬限"优势/风险各 2-3 个"，按绝对额排序挤掉小额高效标签；②只引导看总额不看效率；③patterns 只传 count/win_rate/total_pnl，**漏传 avg_pnl_pct**，AI 想看效率也没数据。

**修复**：优势/风险放宽为"覆盖各维度代表性标签，优先单笔效率最高者"；核心原则新增 #6 效率优先、#7 区分确定结论与低置信度推测（PSY_ 前缀须标"推测，置信度低"）；`_build_analysis_data` patterns 补 `avg_pnl_pct`，prompt 渲染"单笔均收益"。

#### 3. 指标采集了却没渲染（漏渲染 bug）

**现象**：`win_loss_ratio`（损益比）、`pnl_distribution`（盈亏量级分布）进了 `analysis_data`，但 `build_user_prompt` 没有对应渲染分支——数据算了等于白算。

**修复**：补渲染。损益比挂在盈亏比后，量级分布挂风险指标段末。

### 新增功能

#### 1. AI 输入字段契约（`docs/superpowers/AI_INPUT_CONTRACT.md`）

根治"哪些指标喂给 AI"长期无文档、按需零散加出导致的系统性缺陷。含 5 条筛选原则（采集=渲染一致 / 聚合优先 / 护栏字段必传 / 维度覆盖 / 系统算好的优先）、4 层字段清单（基础KPI / 风险指标 / 行为与归因 / 不喂及理由）、维护规则（新增字段三同步）。`CLAUDE.md` 加为第四份必读文档。

#### 2. 喂给 AI 的指标扩充（稳健档）

按契约补 5 项此前未喂的高诊断价值字段：
- `is_small_sample`：护栏，<5 笔提示"样本不足不评价"（落实 FINANCE_DOMAIN §四规范）
- `baseline_expectancy`：评价各行为盈亏的基准线
- `avg_win_holding_days` / `avg_loss_holding_days`：盈亏持仓天数对比，诊断"死扛"
- `shapley`：招牌功能"赚钱来源分析"（Shapley 归因），各行为对总盈亏的公平贡献
- patterns `dimension`：每标签后缀维度归属，防 AI 漏看某维度

### 验证

- 真实数据离线复算：PYRAMID(-0.0375)/TURN(-0.0235)/TIGHT_STOP(+0.0029) 与报告引用值逐项吻合，方向经代码口径证伪后纠正
- `tests/test_ai/` + `tests/test_api/test_report.py`：44 passed，无回归

---


## [V1.1.3] — 2026-06-29

### 概述

本版本是对 `V1.1_IMPROVEMENT_PLAN.md`（前端审查报告）中 **P0 优先级任务**的实施，外加实施过程中发现并修复的 3 个回归/缺陷、1 个 dev 环境陷阱、1 项结构重构。源自一次 Playwright 端到端全流程审查（注册→登录→上传 3 种券商 .xls→分析→报告→历史→管理员→移动端），审查产物归档于 `docs/review/frontend/`。

### 新增功能（P0，4 个 EPIC）

#### 1. 路由补齐与登录回跳（A1）

- `/analysis`、`/report` 无 id 时重定向到 `/history`（之前直接 404）
- `ProtectedRoute` 把当前 URL 作为 `?redirect=` 传给登录页，登录后回跳原页（防 open redirect：仅允许 `/` 开头且非 `//` 的内部路径）
- 404 页增加「热门目的地」入口（首页/上传/历史/登录），登录态隐藏登录入口

#### 2. 黄色警告 banner 整改（B1）

- 「N 笔持仓起始于交割单外」警告改为**可折叠徽章**，默认收起、点击展开，不再占用整屏视觉重心
- 文案中性化：「如需更准确结果，可补传更早期的交割单」（去掉「建议导入更早期以获得完整分析」的归咎语气）
- 展开后内嵌「一键添加更早的交割单」按钮 → 打开 `AddFileModal`（与顶部「+ 添加交割单」同路径，不跳转 `/upload`）

#### 3. 股票维度盈亏表升级（B2）

- **股票中文名**：`Trade` 表新增 `symbol_name` 字段 + alembic 迁移；SmartParser 识别 `证券名称`/`股票名称` 列（CJK 字符启发式 + 排除代码列/方向列）；`compute_stats` 与 `get_stats` 慢路径聚合时构建 `symbol → name` 映射。华西/中信/天风三券商 100% 命中。
- **移动端卡片视图**（≤768px）：每只股票一张卡，不再横向溢出
- **搜索框 + X 清空按钮**：按代码或名称即时过滤，一键清空恢复完整列表

#### 4. 注册/登录一致性与安全（D1）

- 注册/登录 placeholder 统一：「邮箱」/「11位手机号」/「密码（至少8位）」
- 登录页增加「邮箱登录 | 手机号登录」tab，与注册页对称
- 邮箱正则严格化：`/^[^\s@]+@[^\s@]+\.[^\s@]+$/`（拒绝 `a@.com` 等畸形值，两表一致）
- 防账号枚举：登录错误文案统一为「账号或密码错误」，不区分「账号不存在」与「密码错误」

### 修复的 Bug

#### 1. 添加交割单后股票名称全部消失（V1.1.3 引入的回归）

**现象**：通过「+ 添加交割单」上传第二份文件后，股票维度盈亏表所有股票名称消失，刷新页面也无效。

**根因**：`compute.py`（run_analysis 路径）和 `analysis.py`（get_stats 慢路径）**两处各自独立构建 symbol_summary**。P0 只在 `compute.py` 加了 `symbol_name_map`，`link_files_to_analysis` 清空 snapshot 后，下次 GET 走慢路径重算漏了 `symbol_name`，无 name 的 snapshot 覆盖了好的。

**修复**：`get_stats` 慢路径补 `symbol_name_map` 构建。验证：添加文件2 → 18/18 symbols 保留 name（之前 0/18）。

#### 2. AddFileModal 上传后 filenames 不刷新

**现象**：上传文件2 后，header 仍只显示「文件1」，需手动刷新页面才出现「文件1 + 文件2」。

**根因**：`onSuccess` 仅 `invalidateQueries`，但 modal 立即关闭 + `useStats` 有 5 分钟 `staleTime`，background refetch 可能没及时更新 UI。

**修复**：`onSuccess` 改为先 `removeQueries` 再 `invalidateQueries`，强制下次渲染重新请求后端。

#### 3. restart.py 后端启动崩溃（slowapi ModuleNotFoundError）

**根因**：`restart.py` 调用裸 `uvicorn`，PATH 解析到系统级 Python（无 slowapi）而非项目 venv。

**修复**：显式指向 `backend/.venv/{Scripts,bin}/uvicorn`，强制使用项目解释器。

### 重构

#### dedupe symbol_name_map（R1，code review 发现）

`compute.py:225` 和 `analysis.py:307` 原有逐字相同的 5 行 `symbol_name_map` 构建逻辑——正是回归 #1 的根因。抽取为 `common.py:build_symbol_name_map(trades)` 公共函数，两处调用同一实现，杜绝再次漂移。

#### 移除死 prop（R2）

`StatsCards.analysisId` 是 banner 改用 `onAddFile` 后的遗留死代码（声明但从不读）。从 `StatsCards` 接口、`StatsTab` 透传、`Analysis.tsx` 调用点三处移除。

### 文档与沉淀

- **前端审查报告**归档于 `docs/review/frontend/`：Playwright 审查脚本 `audit.py`、22 张截图、`audit_report.json`、`V1.1_IMPROVEMENT_PLAN.md`（5 主题 / 12 EPIC / 47 任务）
- **PROJECT_EXPERIENCE.md** 新增「uvicorn --reload 僵尸 worker 陷阱」章节：记录调试绕圈 1 小时的根因（`taskkill //IM uvicorn.exe` 只杀 reloader 不杀 worker）、Windows 双进程模型、判定「代码 bug vs 环境假象」的排查清单

### 验证

- SmartParser：华西/中信/天风三券商 388/388 笔交易正确解析证券名称
- 后端测试：parsers + engine + auth **232/232 通过**
- 前端 TypeScript：0 错误
- Playwright 端到端：注册→登录→上传→分析→tab 切换→生成报告→历史全流程通过

### 未做（按用户决策）

- **C1 弹窗时序**（P0）：用户要求「保持现状，用户看报告前需做选择」，未改动 `Report.tsx` 的 consent 弹窗逻辑

---

## [V1.1.2] — 2026-06-28

### 概述

本版本源自一次**线上实例端到端数据准确性验证**：投资研究员上传真实华西证券交割单（GBK / 伪 `.xls` / `="..."` 外壳），逐项核对分析面板，发现 2 处必改缺陷 + 1 处口径设计问题。三者共同特征是——**只在"账户整体亏损"场景下才暴露**，单文件盈利分析无法触发，属典型的"测试数据分布 ≠ 生产数据分布"盲区（见 `PROJECT_EXPERIENCE.md`）。全量 415 passed / 0 failed。

### 修复的 Bug

#### 1. 最大回撤百分比超过 100%（金融上不成立）

**现象**：合并两份华西交割单后（86 笔完整交易，总盈亏 -8475.39），分析面板显示"最大回撤 147.5%"。净值从峰值约 +1.8万 跌穿零轴到 -8550，导致 `max_dd / peak > 100%`。

**根因**：`compute.py:349`（`compute_stats` 主路径，写 `stats_snapshot`）与 `analysis.py:453`（`get_stats` 慢路径）两处 `max_drawdown_pct = max_dd / peak`。当 `cum_pnl` 从正峰值跌穿零轴变为负数时，`dd = peak - (负值) > peak`，于是百分比 >100%。原 fallback 仅处理 `peak==0`（从头亏到尾）场景，未覆盖"peak>0 但 trough 跌穿零轴"。

> **副本教训**：研究员初轮只指认了 `analysis.py` 慢路径，漏报 `compute.py` 主路径。若只修 API 端点，`run_analysis` 仍写错误快照，`get_stats` 走快路径返回旧值——修复无效。两处必须同步改。

**修复**：分母改用峰值账户净值 `total_invested + peak`（本金 + 峰值浮盈）。该口径在 trough 跌穿零轴时仍 ≤100%（除非亏损超本金即爆仓，此时 >100% 反而合理），且**完全吞并原 fallback**——`peak==0` 时分母退化为 `total_invested`，与原行为一致，不破坏"全程亏损"回归。`max_drawdown` 绝对值字段保持不变（仍反映真实跌幅金额）。新增红测试 `test_max_drawdown_pct_capped_at_100_when_trough_crosses_zero`（红 150.16% → 绿 ≤100%）。

#### 2. 诊断结论把正贡献标签误判为"最大问题"

**现象**：归因分析 tab 顶部"诊断结论"显示"最大问题是「害怕错过(心理)」，贡献 +2893元"——但该标签 57.1% 胜率、Expectancy +4.0%、PF 2.04，明明是**盈利**标签，正贡献金额却被定性为"最大问题"。

**根因**：`compute.py:415`（`compute_insight`）与 `analysis.py:642`（`get_insight`）两处 `significant[0] / significant[-1]`，取的是**跨维度拼接后的首尾**而非贡献极值。`analyze_by_category` 只对单维度内排序，多维度 `extend` 后整体不再有序，于是 `PSY_FOMO`（+2893）恰好排在末尾被选为 `worst_pattern`。前端 `InsightTab.tsx` 仅渲染后端字段，无 bug。

**修复**：提取模块级纯函数 `_select_best_worst_patterns`，显式按 `total_pnl` 排序——`best` 取正贡献最大、`worst` 取最负。全正时 `worst` 降级为"正贡献最小者"，全负时 `best` 降级为"负贡献最小者"，仅 1 个显著标签时 `worst=None`。两处调用点共用，消除重复。新增 `test_select_best_worst.py` 5 个单元测试（正负混合 / 全正 / 全负 / 单标签 / count<5 过滤）。

### 口径修复

#### 3. Shapley 归因百分比符号取反

**现象**：What-If tab"赚钱来源分析"中，总收益为负时**正贡献标签显示负百分比**（震荡市 +3999.54 渲染为 -47.2%），**负贡献标签显示正百分比**（大亏离场 -5547.22 渲染为 +65.5%）。散户会误以为赚钱的模式在亏钱。

**根因**：`compute.py:545`（主路径）与 `analysis.py:775`（慢路径）两处 `pct_of_total = shapley_value / total_pnl * 100`。`shapley_value` 带符号（正贡献为正），但 `total_pnl` 为负时除法反转符号。Shapley 值本身计算正确，问题在百分比口径。

**修复**：分母改 `abs(total_pnl)`，使百分比符号跟随 `shapley_value`——正贡献恒显正%、负贡献恒显负%。带符号和 = ±100%（因 `sum(shapley) == total_pnl`），仍符合"总和=100%"的绝对占比语义。前端 `ShapleyPanel.tsx` 颜色本就按 `shapley_value` 判断（正确），无需改动。新增 `test_shapley_pct_sign.py` 3 个测试（负总收益下符号一致 / 正总收益下不破坏 / 带符号和=±100%）。

### 验证方式

线上实例（`http://47.109.159.232/`）上传华西 2025-10~12 + 2026-01~03 两份交割单复现全部三处问题，本地修复后回归确认。SmartParser 对真实券商格式（GBK 编码 / 伪 `.xls` TSV / `="..."` 外壳）解析稳健，核心 KPI（PF、Expectancy、净值曲线、止损回测）计算准确。

---

## [V1.1.1] — 2026-06-28

### 概述

本版本是 V1.1.0 的**代码审查收尾**：对 V1.1.0 提交做深度审查后，修复了 1 个发版阻断项、3 个合规/质量问题、2 个性能项，并根治了 1 个既有 flaky 测试。新增 5 个回归测试，全量 404 passed / 0 failed。审查过程覆盖金融定义口径、DB 事务边界、用户隐私合规、性能热路径。

### 修复的 Bug

#### 1. 存量脏快照永久 422（发版阻断项）

**现象**：V1.1.0 修复了"新写入快照完整"的问题，但**部署前已存在的 12 字段不完整快照**（truthy dict）无任何处理——快路径 `if analysis.stats_snapshot:` 为真 → `StatsResponse(**不完整dict)` 缺必填字段 → ValidationError → 422 永久卡死，存量分析无自然恢复路径。

**根因**：`get_stats` 快路径只处理 `None`（跳过），不处理"truthy 但不完整"的存量脏快照。

**修复**：快路径加 `try/except`，捕获 `ValidationError` 后置 `stats_snapshot=None` → fall through 到慢路径 → 慢路径重算并写回完整快照，**自愈**存量分析。新增红测试 `test_stale_partial_snapshot_self_heals`（TDD：旧实现 `4 validation errors` → 修复后 200）。

#### 2. clear_trades 删除 consent_log 审计记录

**现象**：`clear_trades`（清空用户数据）物理删除 `ConsentLog` 行，但 `consent_log` 是"immutable compliance audit trail"（不可变合规审计留痕）。

**根因**：用户同意贡献案例后，案例数据已复制进 `case_library` 表独立留存；用户清空的是自己账户的原始交割单/分析，**不应也不需**删掉已贡献案例的副本。但 consent_log 被一并删除，导致"案例在库、同意证据没了"的不一致——同意证据销毁，无法事后举证授权。

**修复**：`clear_trades` 不再删除 `ConsentLog`，保留全部同意/拒绝记录作为合规证据（与用户讨论确认方案 A）。新增红测试 `test_clear_trades_preserves_consent_log`（旧实现 `0 = len([])` 删光 → 修复后保留 2 条）。`ConsentLog.user_id` 的 `ondelete=CASCADE` 暂不动（当前无账户注销，不会触发）。

#### 3. report 与 /insight 端点的行情竞态 flaky（根治）

**现象**：`test_report_insight_matches_insight_endpoint` 是既有 flaky 测试，连跑原代码 8 次中 4 pass / 4 fail（50%）。

**根因**：report 端点每次用**当前行情** `compute_insight` 重算 `insight_items`，而 `/insight` 端点命中快路径读 `run_analysis` 时生成的 `insight_snapshot`（历史行情）。mootdx 行情抖动时两端 market_env 标签（SIDEWAYS 等）偶发不一致 → patterns 集合差异 → 断言 flake。

**修复**：report 的 `insight_items` 优先读 `analysis.insight_snapshot`（与 `/insight` 端点**同源**），无快照才回退 `compute_insight`（legacy 分析）。从源头消除重算竞态，附带省掉一次 PatternEngine 打标。连跑 10 次全绿，flaky 根治。新增 `test_report_recomputes_insight_when_no_snapshot` 锁定回退分支。

### 性能优化

#### 4. report.py 复用打标结果（PatternEngine 成本减半）

**根因**：report.py 打标一次供 WhatIf 的 `patterns_map`，`_build_category_map` 内部又完整重算一次 `tag_position`/`tag_market_patterns`/心理学检测，PatternEngine 成本翻倍。

**修复**：`_build_category_map` 新增 `precomputed` 参数，传入已打标的 PatternResult 列表时跳过重复打标，只跑 `resolve_per_category`。report.py 打标一次复用。新增 `test_build_category_map.py` 锁定 precomputed 路径与非 precomputed 路径输出**恒等**（相同输入下，防止 report 与 /insight 数据源漂移）。

#### 5. run_analysis 省 redundant SELECT

`run_analysis` 的 `except` 块 `db.rollback()` 后，return 处改用预捕获的 `aid` 替代 `analysis.id`，省一次 refresh SELECT（rollback 后访问 `analysis.id` 会触发额外查询）。

### 测试加固

- drift 等价性测试补 `LARGE_CSV` 大样本夹具（5 position / 全 SWING / 3 盈 2 亏），让 `best_pattern`（count≥5）与 `stop_loss`（亏损持仓 pnl_pct<-5%）非空，Insight/WhatIf 等价性断言不再退化为 `None==None` 平凡通过。覆盖 V4.0 的 `equity_curve` 逐点值、`pnl_distribution`、MAE/MFE 字段。

## [V1.1.0] — 2026-06-27

### 概述

本版本是一次**深度代码审查与质量加固**，起因是用户报告的「生成 AI 报告后返回分析面板数据丢失」故障。围绕该故障定位根因后，顺藤摸瓜展开全量审查，按用户操作路径（认证→上传→分析→查看→AI 报告→案例库→管理）补全了所有缺失测试，清理了死代码，并追查修复了 3 个此前潜伏的 bug。新增 63 个测试，全量 398 passed / 0 failed。

### 修复的 Bug

#### 1. 分析面板数据丢失（422 ValidationError）—— 本次审查的起点

**现象**：用户在服务器上上传交割单 → 看分析面板正常 → 生成 AI 报告 → 返回分析面板 → 页面报错看不到数据 → 点历史报告再进仍看不到。

**根因**：`get_stats` 端点的两个路径写入的快照不一致：
- 快路径 `StatsResponse(**analysis.stats_snapshot)` 要求 40 个字段（含必填 `positions`/`max_win`/`max_loss`/`consecutive_losses`）
- 慢路径（`analysis.py` 旧 line 449-463）只保存 **12 个字段**的 dict

当 `run_analysis` 的 `compute_all` 在服务器上因 mootdx TCP 异常失败时，快照保持 `None`；首次 `get_stats` 走慢路径返回完整数据（用户看到正常）**+ 用 12 字段不完整快照覆盖**；第二次走快路径 → `StatsResponse(**12字段)` 缺必填字段 → ValidationError → 422 → 前端显示"加载失败"，快照被永久污染。

**修复**：
- `get_stats` 慢路径改为存完整的 `response.model_dump()`（而非手写 12 字段 dict）
- `run_analysis` 的 `except` 块新增 `db.rollback()`（失败后 session 污染是 pre-existing 缺陷，导致后续查询全部 `PendingRollbackError`），且 `aid` 在 try 前捕获（避免在 poisoned session 上访问 `analysis.id` 再次崩溃）
- `link_files_to_analysis` 删除冗余的第二次清空+commit（双重清空无意义）
- `MarketDataCache.store_bars` 的 SQLite 路径原本假设所有 bars 同一 symbol（`symbol = bars[0]["symbol"]`），且不处理 within-batch 重复 → 多 symbol 场景漏存 + mootdx 分页重复触发 UNIQUE 冲突。改为按 `(symbol, date)` 元组去重，与 PostgreSQL 的 `ON CONFLICT DO NOTHING` 语义一致

#### 2. 追加交割单后 date 范围未更新

**根因**：`link_files_to_analysis` 在 `db.add(AnalysisFile(...))` 后调用 `get_raw_file_ids` 查询，但测试环境 `autoflush=False`，查不到未提交的新行 → `date_start/end` 不扩展到新文件的交易日期。

**修复**：查询前显式 `db.flush()`。被新测试 `test_link_files_adds_files_and_invalidates_snapshot` 抓出。

#### 3. 上传去重拒绝重传（409 Conflict）

**现象**：两个测试（`test_reimporting_same_statement_does_not_double_count`、`test_multiple_contributions_add_rows`）长期失败，经 stash 对比确认在干净 master 上也失败。

**根因**：`upload_file` 检测到相同 sha256 内容时返回 **409 拒绝**，而非幂等返回已有文件。用户误传同一交割单（改名重传）会被拒绝，无法继续。

**修复**：检测到重复 hash 时**幂等返回已有 RawFile 的 id**。`import_trades` 本身已做交易去重，`_load_trades` 按 `raw_file_id` 过滤，不会双倍计数。

#### 4. AI 报告与 Insight 面板数据源不一致

**根因**：`report.py` 用 `InsightEngine.analyze`（单主模式：每笔交易只归一个主模式，按 `total_pnl` 原始值排序，无样本量门槛），而 `/insight` 面板用 `analyze_by_category`（多桶：每笔交易归入所有匹配模式，按 `total_pnl * log(count)/log(5)` 加权排序，`best_pattern` 还要 `count>=5` 过滤）。

**用户可见影响**：AI 报告可能把 `count=1` 的高盈利模式列为"最佳"，而面板因 `count<5` 过滤掉它，显示另一个模式。

**修复**：`report.py` 改用 `compute_insight`（与面板/`compute_all` 同一数据源），AI 报告与 `/insight` 面板用完全相同的 insight 数据。删除未使用的 `InsightEngine` import。

### 测试补全（新增 63 个测试，6 个文件）

按用户操作路径补全所有零覆盖端点：

| 用户路径 | 测试文件 | 覆盖端点 | 测试数 |
|---|---|---|---|
| 认证 | `test_auth_extra.py` | logout / PUT /me / password-strength | 12 |
| 上传清理 | `test_upload_lifecycle.py` | DELETE /trades（FK-safe 删除） | 4 |
| 分析列表+追加 | `test_analysis_list_and_link.py` | GET /analysis / link-files | 8 |
| 报告查询下载 | `test_report_download.py` | check by-analysis / download .md | 7 |
| 管理 | `test_admin.py` | 全 7 个 admin 端点 | 23 |
| drift 防护 | `test_compute_equivalence.py` | 慢路径 == compute_all | 3 |
| 报告一致性 | `test_report.py`（追加） | report insight == /insight | 2 |
| 快照回归 | `test_analysis.py`（追加） | TestSnapshotRoundTrip | 4 |

**drift 防护网**（`test_compute_equivalence.py`）：清空快照 → GET /stats/insight/whatif（慢路径）→ 与 `compute_all` 直接计算结果比较。这是防止再次出现 422 那类 drift 的核心防护。

> 注：whatif 等价性测试初版用了错误 JSON key（`attribution`/`rule_simulation`，schema 实际是 `items`/`stop_loss`），导致断言恒为空通过——已修复为正确字段名 + 实际值比较。shapley 因蒙特卡洛采样（`random.shuffle` 无种子）有算法随机性，改为容差比较（5% 或 1.0 绝对值）。

### 代码清理（删除死代码）

| 死代码 | 位置 | 处理 |
|---|---|---|
| `pattern_config.py` 整模块（70 行） | `engine/pattern_config.py` | 删除（零引用 + 引用不存在的 `pattern_definition.yaml`，一旦触发 FileNotFoundError） |
| `PatternEngine.detect_cooldowns` | `pattern.py:368-407` | 删除 + 删除 3 个独占测试；不变量测试迁移到 `TestTagCoexistence` |
| `_get_multiplier` | `parsers/__init__.py` | 删除 + 删除独占测试（SmartParser 用自己的 `_get_futures_multiplier_smart`） |
| `BaseParser._column_match_score` | `parsers/base.py:157` | 删除 + 删除独占测试（SmartParser 用自己的 `_classify_column`） |

> `PositionBuilder.build_grouped`（~130 行）仅 golden_runner + 测试用，自身注释承认是"参考实现"——保留（golden_runner 依赖）。

### 记录但未改动的隐患（供未来审查参考）

以下隐患经调查确认，本次未改动（风险/范围考量），已用测试锁住或记录归档：

#### A. get_stats/get_insight/get_whatif 慢路径与 compute.py 重复（~280 行）

`analysis.py` 的三个 GET 慢路径是 `compute.py`（`compute_stats`/`compute_insight`/`compute_whatif`）的手工副本。`get_stats` 副本**已导致过 422 bug**（本次已修）。

- **现状**：当前副本与 engine 行为一致，由 `test_compute_equivalence.py` 锁住。
- **未重构原因**：`compute_all` 用并行 fetcher（`ensure_market_data_parallel` + ThreadPoolExecutor），慢路径用串行 `ensure_market_data`；上轮尝试用 `compute_all` 替换触发 `PendingRollbackError`（daily_bars 重复插入），并发模型变更风险较高。
- **建议**：未来若要消除重复，需先评估并行 fetcher 的 session 安全性，并在 GET 端点包裹 `try/except db.rollback()`（镜像 `run_analysis` 的模式）。

#### B. get_insight / get_whatif 慢路径不写快照

与 `get_stats`（写快照）和 `run_analysis`（写全部三个快照）不同，`get_insight`/`get_whatif` 的慢路径**不持久化快照** → 每次请求重复全量计算。这是性能问题，非正确性问题。

#### C. get_whatif 的 rule_type guard 是死代码

`get_whatif` 用 `if rule_type == "stop_loss":` guard 止损模拟（`analysis.py`），而 `compute_whatif` 无此 guard。但前端**从不传非默认值**，且即使传了，`analyze_rule` 也只处理 `stop_loss`。当前行为一致，guard 无害，保留以防前端未来扩展。

#### D. MAE/MFE 的 lookback 范围差异（理论性）

慢路径的 `ensure_market_data` 返回 120 天 lookback 扩展的 market_data，`compute_all` 的 `get_market_data` 用原始窗口。但 `compute_mae_mfe` 的 position 窗口过滤（`entry_date <= bar_date <= exit_date`）恰好掩盖了差异——当前不触发。若未来 position 的 `entry_date` 早于 `analysis.date_start`，两边会 diverge。

#### E. report.py 的内联 stats 计算（B2，未处理）

`report.py` 的 `_build_analysis_data` + `generate_report` 内联重算了 profit_factor/max_drawdown/consecutive_losses/MAE/MFE/expectancy 等（~200 行），与 `compute.py` 重复。本次仅统一了 insight 数据源（问题 4），stats 计算仍重复。建议未来复用 `compute_all` 的 stats 结果。

#### F. 三个近似的 raw-file 读取器

`upload.py:_read_raw_content`、`admin.py:_read_raw_file_bytes`、`case_library.py:_read_and_decode_raw_file` 三个读取器逻辑近似，建议未来合并到 `common.py`。

### 变更文件清单

```
修改:
  backend/app/api/analysis.py        # get_stats 完整快照 + run_analysis rollback + link_files flush
  backend/app/api/report.py          # analyze → compute_insight 统一数据源
  backend/app/api/upload.py          # 去重 409 → 幂等返回
  backend/app/engine/market_data.py  # store_bars (symbol,date) 去重
  backend/app/engine/pattern.py     # 删除 detect_cooldowns
  backend/app/parsers/__init__.py   # 删除 _get_multiplier
  backend/app/parsers/base.py       # 删除 _column_match_score
  backend/tests/test_api/test_analysis.py       # +TestSnapshotRoundTrip
  backend/tests/test_api/test_report.py         # +TestReportInsightConsistency
  backend/tests/test_api/test_upload.py         # 更新去重测试断言
  backend/tests/test_engine/test_pattern.py     # 迁移 detect_cooldowns 测试
  backend/tests/test_parsers/test_helpers.py    # 删除 _get_multiplier 测试
  backend/tests/test_parsers/test_registry.py  # 删除 _column_match_score 测试
删除:
  backend/app/engine/pattern_config.py
新增:
  backend/tests/test_api/test_auth_extra.py
  backend/tests/test_api/test_upload_lifecycle.py
  backend/tests/test_api/test_analysis_list_and_link.py
  backend/tests/test_api/test_report_download.py
  backend/tests/test_api/test_admin.py
  backend/tests/test_engine/test_compute_equivalence.py
```

---

## [V1.0.0] — 2026-06-26

### 首个正式版本

经过 6 个月的迭代开发（V0.1.1 → V0.5.0），TradeDoctor 达到 v1.0 里程碑。本版本具备完整的「交割单上传 → 持仓重建 → 行为标签 → 盈亏归因 → AI 诊断报告」分析链路，并提供匿名案例库贡献的数据闭环。

### 核心能力

- **SmartParser 自动解析**：基于数据值推断列类型，支持 6+ 券商格式，GBK 编码容错、伪 `.xls` 回退、`="..."` 外壳剥离
- **FIFO 持仓重建**：前序持仓 `cost_known` 标记，软删除 `is_deleted` 支持
- **4 维行为标签体系**：市场环境 / 交易行为 / 交易结果 / 心理推测，每持仓每维最多一个标签
- **Insight Engine**：PF、Expectancy(R)、Shapley 归因、Primary Pattern 识别
- **What-If 止损回测**：持仓期间日线 low 判断盘中触发，因子贡献分析
- **MAE/MFE 风险分析**：持仓期间最大浮亏/浮盈，止盈效率 `profit_capture_ratio`
- **AI 诊断报告**：自然语言报告，Prompt 携带 10+ 风险指标 + 关键交易摘要
- **净值曲线 + 股票盈亏表**：按持仓退出日累计，按个股汇总
- **匿名案例贡献**：用户主动同意的匿名交割单收集，consent_log 审计追踪确保合规

### V1.0 新增（自 V0.5.0 以来）

- **交割单去重**：SHA256 内容哈希 + 交易唯一键双重去重，防止重复导入
- **ConsentLog 合规审计**：用户同意/拒绝决策不可变记录，满足《个人信息保护法》合规证明需求
- **Landing 页内联认证**：注册/登录无需跳转页面
- **UI 全面优化**：设计令牌体系、焦点陷阱、ESC 关闭、Tailwind 迁移、性能优化
- **部署完善**：rsync 全量同步、server-setup.sh 首次安装、跨平台重启脚本

## [V0.4.0] — 2026-06-23

### 新增

- **净值曲线图**（Equity Curve）
  - 后端：`StatsResponse` 新增 `equity_curve: list[EquityPoint]` 字段
  - `EquityPoint = {date, cum_pnl, cum_pnl_pct}`，按持仓退出日期累计盈亏
  - 前端：新建 `EquityCurve.tsx`，使用 Recharts AreaChart 渲染
  - 盈利区域绿色半透明，亏损区域红色半透明，y=0 参考线
  - 放在统计概览页核心结果卡片上方

- **股票维度盈亏表**（Symbol Summary）
  - 后端：`StatsResponse` 新增 `symbol_summary: list[SymbolSummaryItem]` 字段
  - `SymbolSummaryItem = {symbol, trade_count, win_count, win_rate, total_pnl, avg_holding_days, first_trade_date, last_trade_date}`
  - 按个股汇总，仅统计 `cost_known=True` 的有效持仓（与 KPI 口径一致）
  - 前端：新建 `SymbolSummaryTable.tsx`，可排序表格，5 列
  - 默认按总盈亏降序，放在核心结果下方、进阶分析上方

- **AI Prompt 扩充**
  - `build_user_prompt()` 新增「风险指标」板块：profit_factor、expectancy、max_drawdown、max_drawdown_pct、consecutive_losses、avg_mae、avg_mfe、profit_capture_ratio、total_return_pct（共 10 项）
  - 新增「关键交易」板块：盈利 TOP3 + 亏损 TOP3
  - `_build_analysis_data()` 新增 `stats_data` 参数，从 StatsResponse 直接采集风险指标
  - Validator 新增 PF / max_drawdown_pct / consecutive_losses 软校验（±1% 容忍度）

- **测试**：`test_prompt.py` 新增 4 个测试，`test_validator.py` 新增 6 个测试（共 30 passed, 0 failed）

- **基础设施**：`.gitattributes`（统一行尾为 LF）、`vite.config.ts` 新增 `/api` proxy

### 变更

- `frontend/src/api/client.ts` BASE_URL 从 `http://localhost:8000` 改为 `""`（配合 vite proxy）
- `StatsCards.tsx` 集成 EquityCurve 和 SymbolSummaryTable 组件

---

## [V0.5.0] — 2026-06-25

### 新增

- **匿名案例贡献**：用户可提交匿名交割单用于产品改进，`entry_count` 修复，注册提示优化
- **设计令牌体系**：建立 CSS 变量基础，ToastContext / Layout / 认证 / 上传 / 分析面板全站组件迁移
- **ConfirmDialog** 焦点陷阱 / ESC 关闭 / 滚动锁定，提升无障碍体验
- **跨平台重启脚本** `restart.ps1`：PowerShell 原生实现，健康检查绕过代理，支持 Windows/Linux/macOS

### 变更

- **项目改名**：TradingJournalAnalyzer → TradeDoctor
- **部署流程重构**：服务器不再 git pull，改用本地 rsync 全量同步代码；新增 `server-setup.sh` 首次安装脚本 + nginx 配置模板
- **交割单存储**：文件从数据库 BLOB 迁移到磁盘存储，`.gitignore` 排除 `uploads/`
- **归因分析重构**：BREAKOUT 从 behavior 归位到 market_env（与 BREAKDOWN 对称），S14 区分 PnL 量级分桶与 outcome 行为标签，散户体验优化
- 统一后端端口为 8000，同步 vite proxy 和 restart 脚本
- `.env.example` 环境变量模板，`config.py` 绝对路径加载 `.env`
- `requirements.txt` 补全缺失依赖（pandas、slowapi、PyYAML）
- 前端标题与 SEO 描述更新，移除未使用的 WhatIfChart 组件

### 修复

- 修复 12 项高危缺陷（#11-#22）：手机号注册/上传报错、用户错误提示统一等
- 代码审查修复：3 阻塞 + 11 建议 + 8 小改进
- 密码改用环境变量传递，pin ssh-action SHA 防供应链攻击

---

## [V0.3.1] — 2026-06-22

### 修复

- 第三轮代码审查：8 阻塞 + 10 建议 + 4 小改进全量修复
- 前端 UI/UX 全面优化

---

## [V0.2.5] — 2026-06-20

### 新增

- `max_drawdown_pct`：最大回撤百分比（行业标准，对照 TradesViz/Edgewonk）
- `total_return_pct`：总收益率百分比
- `avg_win_pct` / `avg_loss_pct`：平均盈亏百分比

### 变更

- `is_small_sample` 字段：交易笔数 <5 时标记小样本，前端显示「样本不足」不评价

---

## [V0.2.3] — 2026-06-19

### 修复

- 真实券商导出适配（三层污染修复）：
  - GBK 编码探测（utf-8 → gb18030 → gbk）
  - 伪 `.xls` 文本格式回退（`read_excel` 失败后自动切换文本读取 + 分隔符探测）
  - `="..."` 外壳剥离（`_strip_formula_strings`）
  - 费用列 QUANTITY 守卫误杀修复（名称含费用关键词的列豁免）
- 新增 `tests/test_parsers/test_citic_xls.py` 固化真实 CITIC 特征为回归测试

---

## [V0.1.3] — 2026-06-15

### 新增

- **Expectancy（R-multiple）**：基于 pnl_pct 的预期收益，对照 TradesViz 标准
- **Shapley 归因**：公平归因各行为标签对总盈亏的贡献
- `baseline_expectancy` 字段用于标签对比

---

## [V0.1.2] — 2026-06-12

### 新增

- **MAE/MFE 风险分析**：持仓期间最大不利变动（浮亏）和最大有利变动（浮盈）
- `profit_capture_ratio`：止盈效率（浮盈兑现率）
- `mae_winners` / `mae_losers`：分盈亏组的 MAE 均值

### 修复

- PnL 计算扣除买卖双边费用
- 多费用列汇总（佣金、印花税、过户费、其他杂费）
- SmartParser 列类型推断修复（证券代码误选为数量列、价格列误判为费用列）

---

## [V0.1.1] — 2026-06-10

### 新增

- **4 维行为标签体系**：市场环境 / 交易行为 / 交易结果 / 心理推测
- **SmartParser**：基于数据值推断列类型，零配置自动识别券商格式
- **FIFO 持仓重建**：前序持仓标记（`cost_known`），软删除支持（`is_deleted`）
- **What-If 止损回测**：使用持仓期间日线 low 判断盘中触发
- JWT 认证（邮箱/手机号注册，密码强度校验）
- 支持多文件上传和历史分析记录
