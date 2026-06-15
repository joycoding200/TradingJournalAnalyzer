# 项目经验教训 — TradingJournalAnalyzer

## 1. 解析器：永远不要精确匹配用户输入

**现象**：上传东方财富交割单后，所有 KPI 显示为 0，只有"成交记录"和"完整交易"有数字。

**根因**：5 个解析器（dfcf/qmt/boyi/ctp/ths）使用 `== "买入"` 精确匹配买卖方向，但实际券商导出的 Excel 数据是 `证券买入`/`买入开仓` 等变体。

**教训**：
- 用户输入数据**永远不会干净**。字段值可能有前缀、后缀、空格、编码差异
- 字符串匹配优先级：集合成员判断 > 子串匹配 (`in`) > 正则 > 精确匹配 (`==`)
- SmartParser 的值分类器设计是正确的方向——看数据值而非字段名

**涉及文件**：`backend/app/parsers/{dfcf,qmt,boyi,ctp,ths}.py`

---

## 2. 前后端接口：必须契约先行

**现象**："生成 AI 报告"按钮点击后静默失效，History 页面永远为空。

**根因**：3 处前后端 URL 不匹配：
- `POST /api/report/${id}/generate` → 后端是 `/api/report/generate`
- `GET /api/report` → 后端是 `/api/reports`
- `ReportResponse` 缺少 `analysis_id` 字段导致"返回分析面板"链接失效

**教训**：
- API 契约必须在编码前明确定义，不能前后端各自实现后"碰运气"
- OpenAPI/Swagger 文档应作为集成测试的断言依据
- E2E 测试能发现单元测试永远覆盖不到的 URL 不匹配
- 前端字段名 (`data.content`) 必须与后端响应字段 (`report_content`) 严格一致

**涉及文件**：`frontend/src/api/report.ts`, `backend/app/api/report.py`, `backend/app/schemas/report.py`, `backend/app/models/report.py`, `frontend/src/pages/Report.tsx`

---

## 3. What If 回测：Category 过滤器与数据源对齐

**现象**：What If 选项卡始终显示"暂无回测数据"。

**根因**：`get_whatif()` 只过滤 `"entry"` 类别标签，但 `_build_category_map()` 只调用 `tag_position()`（产生 `holding` + `risk` 标签），从不调用 `tag_market_patterns()`（产生 `entry` + `market` 标签）。过滤器与数据生产方不匹配。

**教训**：
- 消费者和生产者必须对齐数据契约，不能各自假设对方会提供/消费什么
- 当一份数据按 category 分类时，所有消费者都应使用全量 category，而不是硬编码某一个
- 附带修复：`CATEGORY_MAP` 中 exit 标签错归为 `"risk"`，应为 `"exit"`

**涉及文件**：`backend/app/api/analysis.py`, `backend/app/engine/pattern.py`

---

## 4. 上传流程：不要让用户做机器能做的事

**现象**：上传文件需要经过 3 步向导（上传→选择格式→预览→确认导入），用户体验差。

**根因**：过度设计。SmartParser 置信度 ≥ 0.7 时完全可以自动流水线处理：upload → confirm → import → analysis。

**改进**：拖入文件后自动串联全流程，仅当置信度 < 0.7 时才让用户手动选择格式。

**教训**：
- 能自动化的步骤不要让用户参与
- 中间确认页面（交易预览）对普通用户无价值，只在解析失败时需要
- 加载状态文案（"正在解析交易记录..."）比空白页面友好得多

**涉及文件**：`frontend/src/pages/Upload.tsx`

---

## 5. 分析数据范围：用实际数据驱动而非硬编码

**现象**：上传第二个表格后分析数字混合了两个表格的数据。

**根因**：`runAnalysis("2020-01-01", today)` 硬编码全时间范围，每次分析查询数据库中的所有交易。

**改进**：从已解析的交易数据中提取实际日期范围作为分析窗口。

**教训**：
- 硬编码的"足够大"范围在生产中永远不够精确
- 用户上传的新数据应默认成为分析焦点，旧数据不应自动混入
- 更好的方案：分析应关联 `raw_file_id` 而非日期范围

**涉及文件**：`frontend/src/pages/Upload.tsx`

---

## 6. E2E 测试 > 单元测试 用于集成验证

**现象**：345 个单元测试全部通过，但用户上传文件后 KPI 全为 0、AI 报告按钮无效。

**根因**：
- 单元测试使用模拟的干净数据（`side="BUY"`），不会触发解析器的 `== "买入"` bug
- 单元测试不经过 HTTP 层，不会发现 URL 路径不匹配
- 单元测试不经过浏览器，不会发现字段名不匹配（`report_content` vs `content`）

**教训**：
- API 契约测试（56 个）+ 用户流程 E2E（19 个）至少应覆盖基本路径
- 每次修改 API 接口后必须同步更新 E2E 测试
- 前端后端集成点（上传、报告生成）是 E2E 测试的最高优先级

---

## 7. JWT 与数据库独立

**现象**：清空数据库后用户登录状态仍在。

**解释**：JWT token 存储在浏览器 `localStorage`，与数据库无关。清库不影响已签发的 token。

**这不是 bug**，是 JWT 无状态设计的固有特性。如果需要强制登出，需要 token 黑名单机制或缩短过期时间。

---

## 修改统计

本次会话共修改 **22 个文件**，涉及：
- 6 个 Bug 修复（解析器硬匹配 ×5、category 过滤器、URL 对齐 ×3、字段名错误、CATEGORY_MAP、报告渲染）
- 2 个功能新增（清空数据按钮、OpenRouter AI provider 支持）
- 2 个体验优化（上传流程简化、导航栏用户菜单）

---

## 8. 金融领域知识缺失是最大的技术债（2026-06-15 审计会话）

**现象**：经历 3 轮代码审计 + 2 轮 UI 审计，发现 ~70% 的问题不是代码 bug，而是金融定义错误或行业标准不一致：
- COUNTER_TREND 识别的是"空头环境"而非"逆势交易"
- Expectancy 用绝对金额而非 R-multiple
- 最大回撤用绝对金额而非行业标准的百分比
- PF 列用 `win_rate/(1-win_rate)` 而非 `gross_profit/gross_loss`
- What-If 止损用最终 PnL 截断而非持仓期间日线 low 判断
- 归因分析存在 Attribution Overlap

**根因**：
- CLAUDE.md 只有架构和技术栈，没有金融领域约束
- E2E 测试能验证"算出了数字"，不能验证"数字的含义是否正确"
- 单人开发 + 缺少金融领域 review 环节

**教训**：
- 项目文档必须包含领域知识，不能只有架构
- 每个指标必须定义：公式、行业标准格式、TradesViz/Edgewonk 参照
- 每个行为标签必须定义边界：它是什么、不是什么的明确正反例
- 新功能开发完成后必须逐项检查领域知识，不能只跑 E2E
- E2E 测试通过 ≠ 结果正确，需要独立的金融逻辑验证环节

**改进**：
- 新增 `docs/superpowers/FINANCE_DOMAIN.md` — 14 个指标词典 + 标签边界 + 行业标准
- 新增 `docs/superpowers/VERIFICATION_CHECKLIST.md` — 6 类 30 项开发自检清单
- CLAUDE.md 增加领域知识引用

**涉及文件**：`docs/superpowers/FINANCE_DOMAIN.md`, `docs/superpowers/VERIFICATION_CHECKLIST.md`, `CLAUDE.md`
