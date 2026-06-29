# 项目经验教训

## SmartParser 列类型推断陷阱（2026-06-12 修复）

SmartParser 使用基于数值特征（而非列名）的列类型推断。这套机制对常见券商格式有效，但存在以下边界情况：

### Bug 1: 证券代码被选为数量列
- **现象**: 600036 等 6 位数字码被当作成交数量，导致数量=600036（实际应为 1200）
- **原因**: 证券代码是全数字列（QUANTITY=0.4），和成交数量得分相同，排在前面被选中
- **修复**: `qty_col` 和 `price_col` 必须 `exclude` 已识别的 `symbol_col`

### Bug 2: 成交价格被纳入费用汇总
- **现象**: 股价 <100 元的 A 股，成交价格列被当作费用列，12.50 元被加到佣金里
- **原因**: `_classify_column` 给低价列 COMMISSION=0.5（avg<1000 +0.3, avg<100 +0.2），超 0.3 阈值
- **修复**: 费用列筛选增加 `PRICE < COMMISSION` 条件，排除价格主导列

### Bug 3: 序号/编号列被纳入费用
- **现象**: 序号=1 加到佣金中，导致每行佣金多 1 元
- **原因**: 序号列值小（1,2,3...），满足 COMMISSION 数值条件
- **修复**: 费用列按列名排除：`序号`、`编号`、`成交编号`、`委托编号`、`合同编号`、`股东代码`

### Bug 4: 旧券商解析器仍被调用
- **现象**: 删除旧解析器后 `source_type` 仍为 `dfcf`，佣金全为 0
- **原因**: 后端进程未完全终止，旧代码缓存未失效
- **修复**: `taskkill //F //IM python.exe` 确保所有进程重启
- **教训**: 详见下方「uvicorn --reload 僵尸 worker 陷阱」——`--reload` 双进程模型下只杀 reloader 不杀 worker 是 Windows 上最常见的"改了代码不生效"根因

## PnL 计算（2026-06-12 修复）

### 费用扣除
- PositionBuilder 的 `_build_for_symbol`（FIFO）和 `_group_for_symbol` 均使用 `(sell_price - buy_price) × qty`，未扣除佣金
- 修复后在 PnL 中扣除买卖双边费用，`pnl_pct` 分母使用含费投资成本

### 多费用列汇总
- A 股有 4 种独立费用：佣金、印花税、过户费、其他杂费
- SmartParser 只取 COMMISSION 评分最高的一列，其余丢失
- 修复为汇总所有 COMMISSION > 0.3 的列

## 测试文件数据一致性问题

- 部分 CSV 中 `清算金额 ≠ 成交金额 ± 费用`，数据生成时有计算误差
- 买卖方向标注错误（如卖出标为买入但有印花税）
- 占位符行（`...,...,...`）导致文件不完整
- 测试前应验证数据内部一致性，而非仅依赖预期值

## 真实券商导出 vs 模拟数据：三层污染（2026-06-19 修复）

真实导出的中信交割单 `20260619 交割单.xls` 一上传就报"无法识别"，而 `testfiles/` 下的模拟数据从未触发。根因：**模拟测试数据是手写的理想化 CSV，和券商程序真实导出的格式分布完全脱节，测试成了自我证明的闭环。**

真实 CITIC 导出与模拟数据的关键差异（每一项都击穿了原代码的隐含假设）：

| 维度 | 模拟数据（测试假设） | 真实 CITIC 导出 | 后果 |
|------|------|------|------|
| 编码 | UTF-8 | GBK | 中文表头乱码，列名匹配失败 |
| 格式 | 真 `.csv` 逗号分隔 | 扩展名 `.xls`，实为 Tab 分隔文本 | `read_excel` 抛异常，`detect` 返回 0 → "无法识别" |
| 单元格 | 裸值 `600519` | 每值裹 `="002471"`（Excel 文本保护公式，保留前导零） | 值正则/日期/`float()` 全失效 → 0 笔成交 |
| 费用列 | 无 / 简单 | `手续费=5.00` 小整数 | 误判为 QUANTITY，佣金**静默漏算** |

### Bug 5: `_read_df` 信任扩展名，不信任内容
- **现象**: `.xls` 文件"无法识别"
- **原因**: `base.py` 按扩展名分发——`.csv` 假设 UTF-8 逗号、`.xls` 假设真 Excel 工作簿。中信导出的是伪装成 `.xls` 的 GBK TSV 文本，`pd.read_excel` 直接 `ValueError`，无 try/except 回退，异常被 `detect` 吞掉返回 0.0
- **教训**: **券商导出的扩展名不可信**。`.xls` 常是 GBK/GB18030 文本（中信、华泰、QMT 等普遍如此），`.csv` 常非 UTF-8。必须"按内容探测格式 + 按字节探测编码"，而非按扩展名分发
- **修复**: `read_excel` 失败即回退文本读取；文本读取做编码探测（utf-8→gb18030→gbk）+ 分隔符探测（tab/逗号/分号/管道）

### Bug 6: 值分类器对 `="..."` 外壳零容忍
- **现象**: 文件能读进来，但 `parse` 返回 0 笔
- **原因**: SmartParser 的值推断（股票代码 `^\d{6}$`、日期 `^\d{4}[-/]\d{1,2}`、`float(v)`）都假设值是裸的；真实值是 `="002471"`，所有列 DATE/STOCK_SYMBOL/PRICE/QUANTITY 全 0 分
- **教训**: `="..."` 是 Excel 文本保护公式，券商为保留前导零代码刻意加的——真实导出常态，模拟数据绝不会出现。**值分类器必须先清洗外壳**
- **修复**: `base.py` 新增 `_strip_formula_strings`，用 `^="(.*)"$` 正则统一剥离，所有列无差别应用（不依赖 dtype，因 `dtype=str` 下列是 StringDtype 而非 object）

### Bug 7: 费用列 QUANTITY 守卫误杀小整数手续费
- **现象**: 成交识别成功，但佣金偏低（5 元券商手续费没计入 PnL）
- **原因**: `comm_cols` 的 `QUANTITY < 0.45` 守卫本意排除序号/编号列，但 `手续费=5.00` 这种小整数被打上 QUANTITY 0.6 分被误杀。比"无法识别"更危险——不报错，只静默算错盈亏
- **修复**: 对**名称含费用关键词**（费/佣/税）的列豁免 QUANTITY 守卫；ID 类列仍由名称黑名单排除
- **教训**: 启发式数值守卫要和列名语义交叉验证，不能只看数值分布

### 根因教训：测试数据分布 ≠ 生产数据分布
- `testfiles/` 的模拟数据是**按解析器当前能力反向定制**的——能过什么就生成什么，于是测试自证闭环，真实数据一来立刻穿帮
- 必须用**真实脱敏交割单**做夹具，覆盖三层污染（编码、伪装格式、`="..."` 外壳）
- 新增 `tests/test_parsers/test_citic_xls.py` 固化真实 CITIC 特征为回归测试
- 遗留脱节：`testfiles/` 目录已不存在（CLAUDE.md 仍引用）；`tests/test_api/test_upload.py` 仍断言已删除的 `qmt` 格式——均为"模拟时代"残留，待清理

## V4.0 P0 冲刺：净值曲线 + 股票维度盈亏 + AI Prompt 扩充（2026-06-23）

### 经验 1：净值曲线数据采集复用 max_dd 循环

- `get_stats()` 中计算最大回撤时已遍历 `sorted_positions` 累计 PnL，净值曲线数据点（`EquityPoint`）可在同一循环中收集，无需二次遍历
- 起点必须为 `{首笔 exit_date, 0.0, 0.0}`，后续逐笔累加 position.pnl
- `cum_pnl_pct` 基于初始资金计算，非交易收益率
- 前端 `EquityCurve.tsx` 用 Recharts `AreaChart`，颜色由最终 cum_pnl 正负决定（盈利绿/亏损红），`ReferenceLine y=0` 标记零线

### 经验 2：股票维度盈亏使用 valid_positions 口径

- `symbol_summary` 必须只统计 `cost_known=True` 的有效持仓，与 KPI 口径一致
- 按 `symbol` 分组后计算 `trade_count`、`win_count`、`win_rate`、`total_pnl`、`avg_holding_days`
- 前端 `SymbolSummaryTable.tsx` 默认按 `total_pnl` 降序排列，支持点击列头排序

### 经验 3：AI Prompt 扩充的数据流

- `report.py` 的 `_build_analysis_data()` 原本只接收 positions/market_data/insight/whatif，V4.0 新增 `stats_data` 参数
- 风险指标从 `StatsResponse` 字段直接采集，不经 AI 猜测，确保数值准确
- `build_user_prompt()` 新增「风险指标」和「关键交易」两个板块
- Validator（`validator.py`）对 PF、max_drawdown_pct、consecutive_losses 执行软校验（±1% 容忍度），不匹配仅记录 warning 不阻断报告生成
- 测试覆盖：`test_prompt.py` 新增 4 个测试，`test_validator.py` 新增 6 个测试

### 经验 4：WSL 环境下的 CRLF/LF 行尾问题

- Claude Code 在 WSL 环境中执行会导致 Windows 文件被转为 LF，与 git 仓库的 CRLF 产生大面积 diff
- 解决方案：添加 `.gitattributes`（`* text=auto eol=lf`），统一行尾为 LF
- `git rm --cached -r . && git add .` 可批量归一化行尾，但会产生大量 diff，需在功能提交前单独处理

## 快照一致性陷阱与代码审查经验（2026-06-28 修复，V1.1.1）

### 陷阱 1：快路径「truthy 但不完整」快照——422 永久卡死

**现象**：`get_stats` 快路径 `if analysis.stats_snapshot:` 只判断 truthy，存量 12 字段不完整 dict 是 truthy → `StatsResponse(**不完整dict)` 缺必填字段 → ValidationError → 422，且无自然恢复路径（用户不会为此去追加文件触发重算）。

**根因模式**：快路径只处理「None（跳过）」和「完整（命中）」两种状态，漏了第三种「truthy 但不完整」——这正是 V1.1.0 只修新写入、未修存量的盲区。

**教训**：任何「读快照 → 反序列化为严格 schema」的快路径，都必须 `try/except` 包裹反序列化，失败时 fall back 到慢路径重算并**覆盖**快照自愈。不能假设库里所有快照都是当前代码写出的完整格式——历史脏数据会长期存在。

**验证方法**：TDD 红测试先造一个 truthy 不完整快照，断言修复前 422、修复后 200 + 快照被重写完整。

### 陷阱 2：审计日志的删除边界——合规证据 vs 业务数据

**现象**：`clear_trades`（清空用户数据）物理删除 `ConsentLog`，但 consent_log 是「不可变合规审计留痕」。用户同意贡献案例后，案例数据已复制进 `case_library` 独立留存；清空原始数据不该连带删掉已贡献案例的同意证据。

**根因模式**：「清空用户数据」按表逐个删除时，把审计表也当业务表一起删了，导致「案例在库、同意证据没了」的不一致。

**教训**：区分两类表——业务数据表（trades/analyses/raw_files，可随用户清空）vs 审计/留痕表（consent_log，不可删）。审计表的生命周期独立于业务数据，除非用户注销账户且需满足「被遗忘权」时才单独处理。删除前先问：这张表删了，会不会让某条已发生的事失去证据？

### 陷阱 3：「重算 vs 读快照」的竞态 flaky——测试设计缺陷

**现象**：`test_report_insight_matches_insight_endpoint` 连跑原代码 8 次 4 pass / 4 fail（50% flaky）。

**根因模式**：report 端点每次用**当前行情** `compute_insight` 重算，而 `/insight` 端点读 **run_analysis 时**生成的 `insight_snapshot`（历史行情）。行情抖动（mootdx 网络波动）时两端 market_env 标签偶发不一致 → 断言 flake。测试在断言「两端数据源一致」，却让两端各自真实拉行情，把网络竞态引入了本应确定性的断言。

**教训**：
- 凡断言「A 端点 == B 端点」的一致性测试，两端必须**同源**（都读同一快照），不能各自重算依赖外部不稳定输入（网络/时间/随机）
- 「重算」本身就是 flaky 源：只要 A 重算、B 读快照，且重算依赖外部状态，就必然竞态。根治是让 A 也读快照，而非给测试 mock 外部状态（mock 行情会让快路径 snapshot 与重算结果反向不一致）
- 判断一个 flaky 是否「既有」：stash 掉自己的改动连跑 N 次，统计 pass/fail 比例。单次结果会误导

### 通用教训：性能优化要锁定「输出恒等」

- 给 `_build_category_map` 加 `precomputed` 参数（跳过重复打标）是纯性能优化，但必须用测试锁定「precomputed 路径 == 默认路径」恒等，否则会引入「report 与 /insight 数据源漂移」的隐性 bug
- 优化前后用同一输入做断言对照（不依赖外部网络），是「零行为变更」类优化的安全网

## uvicorn --reload 僵尸 worker 陷阱（2026-06-29 修复，V1.1.2）

### 踩坑案例：一个 bug 调查绕了一大圈，根因竟是旧进程没死

**现象**：`get_stats` 慢路径补了 `symbol_name` 后，验证脚本始终返回 0/18（无名称）。在函数入口加 `print`、加文件写日志、加 `logger.warning`——**全部不触发**。但 API 返回 200 + 真实 symbol_summary 数据。绕了 1 小时，怀疑过 schema、怀疑过 model_dump、怀疑过 reload 缓存、怀疑过 .pyc 缓存——全错。

**根因**：`taskkill //F //IM uvicorn.exe` 只杀了 `--reload` 的**父 reloader 进程**（`uvicorn.exe`），没杀掉它 fork 的 **worker 子进程**（`python.exe`）。这些僵尸 worker 继续监听 8000 端口，处理所有请求，跑的是**旧代码**。我新启动的 uvicorn 因端口被占用 `bind` 失败（`Errno 10048`），但 `curl /api/health` 仍返回 200（被僵尸 worker 处理），让我误以为新进程在跑最新代码。

**致命的误导链**：
1. health 200 → 以为新进程启动成功
2. API 返回真实数据 → 以为请求打到了新进程
3. 日志/print 不触发 → 误判为「代码没执行」，开始怀疑 schema/序列化/缓存
4. 实际是请求**根本没到新进程**，被僵尸 worker 拦截了

**正确排查顺序**（下次直接按这个走，省 1 小时）：
1. **先看新进程的启动日志有没有 bind 错误**（`Errno 10048` / `address already in use`）——这是第一个信号，但我跳过了
2. **`netstat -ano | grep :8000`** 看端口被几个 PID 占用——多个 PID 就是僵尸
3. **在函数入口加 print + 重启后立即 curl，看日志有没有出现**——没出现 = 请求没到这个进程 = 端口被旧进程占着
4. 杀进程要 `taskkill //F //IM python.exe`（杀 worker），不能只 `//IM uvicorn.exe`（只杀 reloader）

### 经验：Windows 上 uvicorn --reload 的进程模型

- `--reload` 模式下 uvicorn 是**双进程**：父进程 `uvicorn.exe`（reloader，监听文件变化）+ 子进程 `python.exe`（worker，实际跑 app）
- 杀父进程不会杀子进程（除非用 `taskkill //T` 树形杀）。worker 成为孤儿，继续监听端口
- Windows `taskkill //F //IM uvicorn.exe` **只匹配可执行文件名**，匹配不到 `python.exe` worker
- **彻底清理**：`taskkill //F //IM python.exe`（开发机可全杀）；或按 PID 杀：先 `netstat -ano | grep :8000` 拿 PID，再 `taskkill //F //PID <pid>`

### 经验：区分「代码 bug」vs「环境假象」的快速判定法

当一个修复**明明在磁盘上、`inspect.getsource` 也确认了、但运行时不生效**时，立刻检查环境而非继续改代码：

| 信号 | 含义 | 下一步 |
|------|------|--------|
| 新进程日志有 `bind`/`address in use` 错误 | 端口被旧进程占 | 杀僵尸 worker |
| 函数入口的 `print` 不触发，但 API 返回 200 | 请求没打到新进程 | 同上 |
| `netstat` 显示端口被多个 PID 监听 | 多个 worker 僵尸 | 全杀重启 |
| 改了代码、清了 `__pycache__`、重启了，行为不变 | 跑的不是这份代码 | 确认进程加载路径 |

**反模式**（我踩的）：跳过 bind 错误日志，直接怀疑业务代码 → 在 schema/序列化/缓存层反复打转 → 越改越困惑。应该先用最简单的「入口 print + curl」确认请求是否到达新进程，不到 = 环境问题，到了但行为不对 = 代码问题。

### 关联：get_stats 慢路径漏 symbol_name（这次真正的代码 bug）

僵尸 worker 问题解决后，真正的代码 bug 才被验证：`compute.py`（run_analysis 路径）和 `analysis.py`（get_stats 慢路径）**两处各自独立构建 symbol_summary**，我只改了前者。`link_files_to_analysis` 清空 snapshot 后，下次 GET 走慢路径重算，漏了 `symbol_name`，无 name 的 snapshot 覆盖了好的。

**教训**：当一个聚合逻辑在**多个函数里各写一份**（compute_stats vs get_stats 慢路径）时，改一个必须同步另一个。最好抽公共函数，否则至少用 grep 列出所有 `symbol_summary_data.append` 调用点逐一核对。

## 错误诊断流程

1. 先本地跑 SmartParser 验证列类型推断和佣金
2. 手工计算 1-2 笔 PnL 作基准
3. 与程序结果逐笔比对
4. 最后通过 UI 端到端验证

## "改了代码不生效"排查清单（先走这个，再怀疑业务逻辑）

当磁盘代码已改、`inspect.getsource` 确认、但运行时行为不变时，按此顺序排查**环境**而非业务代码：

1. **新进程启动日志有没有 bind 错误**（`Errno 10048` / `address already in use`）→ 有 = 端口被旧进程占，新进程没起来
2. **`netstat -ano | grep :8000`** → 多个 PID 监听同一端口 = 僵尸 worker
3. **函数入口加 `print` + 重启 + curl，看日志有没有出现** → 没出现 = 请求没到新进程（最可靠的判定法）
4. **`taskkill //F //IM python.exe`** 全杀 worker（`uvicorn.exe` 只杀 reloader，不杀 worker）
5. **清 `__pycache__`** 后重启（防止 .pyc 缓存，虽然 Python 3 一般会按 mtime 判定，但保险起见）
6. 以上都排除后，**再**怀疑业务代码

判定原则：**入口 print 是分水岭**——print 触发说明请求到了新进程，问题在业务代码；print 不触发说明请求被旧进程拦截，问题在环境。先确定是哪一类，再往下查，避免在错误的层绕圈。

