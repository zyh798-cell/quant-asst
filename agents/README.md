# 多空辩论模块（Step 4）

多角色多 Agent 辩论系统。输入标的与自然语言策略描述，经多轮多空交替辩论、逐轮风控核验，
输出结构化裁决结论与可直接回测的策略修订建议。

仅用于研究与教育，不构成投资建议。

## 角色与职责

| 角色 | 类 | prompt 模板 | 输出 schema |
| --- | --- | --- | --- |
| 多头分析师 | `agents/bull.py` `BullAgent` | `core/prompts/templates/bull.md` | `BullArgument` |
| 空头分析师 | `agents/bear.py` `BearAgent` | `core/prompts/templates/bear.md` | `BearArgument` |
| 风控核验员 | `agents/risk_officer.py` `RiskCheckAgent` | `core/prompts/templates/risk.md` | `RiskCheckReport` |
| 最终裁决员 | `agents/reviewer.py` `ReviewerAgent` | `core/prompts/templates/reviewer.md` | `DebateVerdict` |

各角色继承 `core/base.BaseAgent`，统一走 LiteLLM 结构化输出 + Pydantic 校验 +
失败重试 1 次（硬约束 2），并在 trajectory 中留痕（硬约束 4）。

## 红队审计 + 风控综合（Step 5）

辩论完成后，可对辩论纪要做**独立**反向压力审计与最终风控综合，两个新角色
均不参与多空辩论：

| 角色 | 类 | prompt 模板 | 输出 schema |
| --- | --- | --- | --- |
| 红队审计员 | `agents/redteam.py` `RedTeamAgent` | `core/prompts/templates/redteam.md` | `AuditReport` |
| 风控综合官 | `agents/final_risk_officer.py` `FinalRiskOfficerAgent` | `core/prompts/templates/risk_officer.md` | `FinalAnalysisDraft` |

流程链路（独立于辩论图，由 `core/audit_graph.py` 编排）：

```
多Agent辩论完成 -> 辩论报告 md -> 红队审计 Agent -> 审计报告 md
              -> 确定性风控门控 -> 风控综合官 -> 最终量化分析报告 md
```

**风控门控（确定性规则，不依赖 LLM，可复现）见 `core/risk_gate.py`：**
- 致命（critical）：禁止生成交易建议，最终决策恒为 `blocked`，报告顶部显著标注；
- 高（high）及以上：允许交易建议，但报告顶部显著标注风险提示并强制写明约束边界；
- 阈值可用 CLI `--threshold` 收紧（默认 `high`，收紧为 `medium` 时中风险也触发标注）。

红队审计挖掘五类风险：逻辑漏洞、过拟合、未来函数、幸存者偏差、流动性陷阱，
并做风险定级（低/中/高/致命）。

### 命令

```powershell
# 先做一场辩论（产出 output/debate_reports/<run_id>.json）
uv run python cli.py debate "宁德时代双均线策略，5日线上穿20日线买入，死叉卖出，测近两年"

# 对已有辩论报告 JSON 执行审计 + 风控综合
uv run python cli.py audit "output/debate_reports/<run_id>.json" --threshold high
# 收紧阈值（中风险即触发风险提示）
uv run python cli.py audit "output/debate_reports/<run_id>.json" --threshold medium
```

### 产物

| 产物 | 路径 |
| --- | --- |
| 红队审计意见书 | `output/audit/audit_<ticker>_<timestamp>.md` |
| 最终量化分析报告 | `output/audit/final_<ticker>_<timestamp>.md` |
| 审计轨迹 | `var/trajectories/<audit_run_id>.jsonl` |

`ticker` 为统一 symbol 转文件名安全形式（`cn:300750` -> `cn_300750`），
`timestamp` 为 `YYYYMMDD_HHMMSS`。所有 md 为工程文档风格，无 emoji、无口语化话术。

## Reviewer 可视化输出（Step 6）

在 Markdown 双报告（工程归档版 + 最终量化分析报告）基础上，新增 **Plotly 交互式
HTML 最终报告**，与 md 并行输出。渲染层为独立模块 `report/html.py`，
**不侵入回测引擎 / 辩论 Agent / 红队审计 / 风控网关**原有逻辑，只消费工具产出的数据。

### 输出内容（单文件 HTML，plotly.js 内联）

- 标的 K 线行情图 + 买卖信号标记（买入 triangle-up / 卖出 triangle-down）；
- 回测净值曲线（含初始资金基准线 + 样本外起点 vline 标注）；
- 最大回撤曲线（相对历史峰值，负值填充）；
- 风险指标汇总面板：区间总收益 / 年化收益 / 最大回撤 / 夏普比率 / 按笔胜率 /
  成交笔数 / 初始资金 / 期末净值 / 累计成本 / 样本外起点；
- 决策条：最终决策（adopt / revise / reject / blocked）+ 综合风险定级；
- 高风险 banner 与强制约束边界（致命风险时交易建议显示为已拦截）；
- 三段文本摘要：辩论摘要、红队审计风险结论、风控综合结论；
- 页脚注释：数据来源与回测约束边界（样本内/外 70/30、次开盘价撮合、双边成本与滑点、
  历史回测不预示未来收益）。

### 取数与降级

HTML 图表数据来自一次**参考回测**：按裁决的 `revised_strategy_text`，
复用 `HypothesisAgent` + `backtest_sandbox` + `market_data` 工具链，
由 `report/build.py` 编排；轨迹留痕使用自建专用 `TrajectoryRecorder`
（不依赖 CLI 主 recorder 的生命周期，避免 close 后写入失败）。

取数失败不阻断报告生成：降级为「仅文本摘要 + 指标面板」，图区注明缺失原因。

### 命令

```powershell
# 辩论链路 + HTML 报告（额外生成 output/html/final_<ticker>_<timestamp>.html）
uv run python cli.py debate "宁德时代双均线策略，5日线上穿20日线买入，死叉卖出，测近两年" --html

# 审计链路 + HTML 报告
uv run python cli.py audit "output/debate_reports/<run_id>.json" --html
```

`--html` 为可选开关，默认只输出 md，原有行为不变。产物归类 `output/html/`，
同时写一份结构化 JSON 便于审计回放；历史临时/半成品文件（`.tmp`/`.part`/`~`
开头）在每次落盘时自动清理。

### 图表规范

配色克制专业（深蓝净值 / 暗红回撤 / 深绿买入 / 深红卖出 / A 股口径红涨绿跌），
金融量化风格，图表自带注释（数据来源与回测约束边界），无花哨动画
（`displayModeBar:false`，静态单文件，浏览器直接打开）。

## 辩论流程

每轮三个节点，最多 `debate_rounds` 轮（默认 3，上限 3）：

```
START -> round_start -> bull -> bear -> risk_check -> (下一轮 | reviewer) -> END
```

- `round_start`：轮次计数递增，清空当轮草稿。
- `bull` / `bear`：分别产出当轮观点；第 2 轮起自动带入对方上一轮材料与已通过校验的论据索引。
- `risk_check`：中立校验双方本轮论点，输出发现清单与「留存论点索引」，并累积逐轮原文。
- `reviewer`：汇总全部材料，给出可信度打分（0~100）、共识/分歧、裁决（adopt/reject/revise）
  与可选 `StrategyRevision`。

状态机对异常做短路保护：任一节点失败写入 `State["error"]` 并直接进入裁决，不崩溃。

## 使用方法

> 前置：`cli.py` 依赖相对路径，**必须在项目根目录运行**。
> Windows PowerShell 示例（路径按实际安装位置修改）：
>
> ```powershell
> cd quant-asst
> uv run python cli.py debate "双均线策略" --symbol cn:300750
> ```

```bash
# 完整链路：先由 HypothesisAgent 推断标的，再进入辩论
uv run python cli.py debate "宁德时代双均线策略，5日线上穿20日线买入，死叉卖出，测近两年"

# 显式指定标的与轮次
uv run python cli.py debate "双均线策略" --symbol cn:300750 --rounds 2

# 离线 mock 模式（不调用真实 LLM，CI 可用）
QUANT_ASST_LLM_MOCK=1 uv run python cli.py debate "双均线策略" --symbol cn:300750

# 强制真实 LLM（缺省在未检测到 DEEPSEEK_API_KEY 时自动启用 mock）
uv run python cli.py debate "双均线策略" --symbol cn:300750 --no-mock
```

## 产物

命令运行后输出三类文件：

| 产物 | 路径 | 说明 |
| --- | --- | --- |
| Markdown 报告 | `output/debate_reports/<run_id>.md` | 逐轮多空原文、风控意见、裁决打分、结论与修订建议；目录自动创建 |
| 结构化 JSON | `output/debate_reports/<run_id>.json` | `DebateOutcome` 完整纪要 |
| 轨迹 | `var/trajectories/<run_id>.jsonl` | 每次 LLM 调用与角色输出的完整留痕 |

## 参数

| 参数 | 配置项 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--rounds` | `debate_rounds` | 3 | 最大辩论轮次（1~3），超出按 3 处理 |
| `--symbol` / `-s` | — | 由假设解析推断 | 标的，格式 `<market>:<code>` |
| `--market` / `-m` | `default_market` | `cn_stock` | 市场前缀 cn/us/hk/futures/crypto |
| `--no-mock` | — | 关闭 | 强制真实 LLM 调用 |
| `QUANT_ASST_LLM_MOCK` | 环境变量 | 未设置 | 置 1/true/yes/on 启用脚本化离线后端 |

## Mock 离线模式

`QUANT_ASST_LLM_MOCK=1` 时，`core.llm.get_completion_backend()` 返回
`MockCompletionBackend`：按 prompt 首行特征词判定角色（多头分析师/空头分析师/
风控核验/最终裁决员/红队审计员/风控综合官等），返回确定性且 schema 合法的占位 JSON。
用于单元测试与 CI，不产生任何网络请求与真实模型消耗。真实密钥存在且未显式指定时仍走 LiteLLM。

mock 模式会在 `import litellm` **之前**设置 `LITELLM_OFFLINE_MODE=true`，
禁止 LiteLLM 后台拉取远端 model cost 映射（GitHub raw），
从而屏蔽离线场景下的网络重试告警；真实模式下该开关不生效，行为不变。

## 与回测引擎的衔接

裁决的 `revision.revised_strategy_text` 会补全标的标识，可直接作为 `cli.py run` 的输入：

```bash
uv run python cli.py debate "..." --symbol cn:300750        # 得到 revised_strategy_text
uv run python cli.py run "<revised_strategy_text>"          # 送入回测引擎验证
```

`cli.py debate` 会在终端打印第二条命令作为提示；JSON 中的 `revised_strategy_text`
字段同样可直接取用。
