# Quant Asst 架构文档

本文档说明 Quant Asst 的分层结构、各模块职责、数据流与设计约束。
所有命名（风险等级、指标名、决策值）与 `core/schemas.py` 实现严格一致。

## 1. 整体分层

```
┌──────────────────────────────────────────────────────────────────────────┐
│  输入层                                                                   │
│  自然语言策略描述（CLI / examples），例如「双均线策略，5日线上穿20日线买入」      │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │  user_input + market
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  解析层（agents/hypothesis.py）                                            │
│  策略假设分析师：自然语言 -> HypothesisSpec -> 策略代码 generate_positions()   │
│  契约：仅 numpy/pandas；禁未来函数；输出逐行对齐的目标仓位序列                  │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │  generated_code + symbol + period
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  回测引擎层（backtest/ + tools/backtest_sandbox.py）                         │
│  事件驱动引擎在沙箱内执行策略，产出 BacktestResult（含样本内/外指标）            │
│  沙箱边界：DockerSandbox（Release）/ LocalRestrictedSandbox（开发调试）        │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │  BacktestResult（总收益/最大回撤/夏普/…）
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  辩论层（agents/bull|bear|risk_officer|reviewer.py, core/debate_graph.py）  │
│  START -> round_start -> bull -> bear -> risk_check -> (下一轮 | reviewer)   │
│  逐轮留痕；产出 DebateOutcome（裁决 + 修订策略文本）                          │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │  debate_outcome
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  审计层（agents/redteam.py, core/audit_graph.py）                           │
│  START -> redteam -> gate -> risk_officer -> END                           │
│  红队审计五类风险 + 确定性门控 + 风控综合官                                   │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │  AuditReport + FinalAnalysisReport
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  渲染层（report/markdown.py, report/html.py, report/build.py）              │
│  工程版 Markdown（归档） + Plotly 单文件 HTML（交互）                        │
└──────────────────────────────────────────────────────────────────────────┘
```

## 2. 各模块职责

| 层 | 模块 | 职责 |
| --- | --- | --- |
| Agent 基类 | `agents/base.py`、`core/base.py` | 统一 LiteLLM 结构化输出 + Pydantic 校验 + 失败重试 1 次（硬约束 2），并在 trajectory 中留痕 |
| LLM 调用层 | `core/llm.py` | `complete` / `complete_structured`；真实模式走 LiteLLM，mock 模式由 `MockCompletionBackend` 按 prompt 首行特征词判定角色并返回确定性样例 |
| 沙箱 | `tools/sandbox_docker.py` | Release 默认：一次性容器执行，禁网、内存/CPU 限额、非 root、用后即毁 |
| 沙箱 | `tools/sandbox_local.py` | 开发调试备选：子进程 + AST 静态安检 + 超时/内存限额；隔离不足，禁止生产 |
| 行情数据 | `tools/market_data.py`、`data/cache.py` | Agent 取数唯一入口；缓存优先读取本地 parquet（`var/market/<market>/<code>__<start>__<end>[__<adjust>].parquet`，复权口径由适配器 `ADJUST` 声明，A 股为 `qfq`、美股为空），未命中经适配器抓取并写缓存 |
| 数据模型 | `core/schemas.py` | 全部结构化输出的 Pydantic schema（`StrictModel` 禁止额外字段），保证 trajectory 可回放 |
| 轨迹日志 | `core/trajectory.py` | 每次运行一个 run_id，产出 `var/trajectories/<run_id>.jsonl`，逐事件追加写、实时 flush |
| 状态机 | `core/graph.py`、`core/debate_graph.py`、`core/audit_graph.py` | LangGraph 编排；节点异常写入 `State["error"]` 并短路，图不崩溃 |
| 风控门控 | `core/risk_gate.py` | 确定性规则（不依赖 LLM）：致命恒拦截、高风险及以上标注 + 约束边界 |

## 3. 数据流与产物落盘

一次完整研究的参数流转与各阶段产物如下：

| 阶段 | 输入 | 主要产物 | 落盘位置 |
| --- | --- | --- | --- |
| 回测（Step 3） | 自然语言 + 标的 + 区间 | `BacktestResult`（JSON 摘要） | State / 终端表格 |
| 参数寻优（Step J） | 策略代码 + 标的/区间 + 参数网格 | 全组合样本内/外指标对比 + 最优组合 + 劣化结论 | `output/optimization/optimization_<symbol>_<start>_<end>.md` |
| 辩论（Step 4） | 策略描述 + 标的 | `DebateOutcome` | `output/debate_reports/<run_id>.md` / `.json` |
| 审计（Step 5） | 辩论 JSON | `AuditReport` + `FinalAnalysisReport` | `output/audit/audit_<ticker>_<timestamp>.md` / `final_<ticker>_<timestamp>.md` |
| 可视化（Step 6） | 上述三类 + 参考回测明细 | 交互式 HTML + 结构化 JSON | `output/html/final_<ticker>_<timestamp>.html` / `.json` |
| 全程 | 每次 LLM 调用与角色输出 | trajectory 事件流 | `var/trajectories/<run_id>.jsonl` |
| 取数 | 标的 + 区间 + 复权口径 | parquet 缓存 | `var/market/<market>/<code>__<start>__<end>[__<adjust>].parquet` |

`<ticker>` 为统一 symbol 转文件名安全形式（`cn:600519` -> `cn_600519`）；
`<timestamp>` 为 `YYYYMMDD_HHMMSS`。HTML 图表的 K 线 / 信号 / 净值 / 回撤明细来自
一次参考回测（复用既有工具链，失败时降级为纯文本报告）。

参数寻优（`backtest/optimizer.py`）位于**回测引擎之上、报告渲染之前**：复用同一份策略代码
与同一切分点做确定性网格遍历，只读样本内指标选优、样本外仅用于最终劣化验证，
不进入辩论 / 审计链路（不调用 LLM）。

## 4. 关键数据模型（与代码一致）

- **风险定级**：`low` / `medium` / `high` / `critical`（`RISK_LEVELS`，中文标签 `低` / `中` / `高` / `致命`）。
- **最终决策**：`adopt` / `revise` / `reject` / `blocked`（致命风险恒为 `blocked`）。
- **审计发现类别**：`logic_flaw`（逻辑漏洞）、`overfitting`（过拟合）、`lookahead`（未来函数）、
  `survivorship`（幸存者偏差）、`liquidity_trap`（流动性陷阱）、`data_integrity`（数据完整性）、`other`。
- **回测指标**（`BacktestMetrics`）：`total_return`（区间总收益）、`annual_return`（年化收益）、
  `max_drawdown`（最大回撤，负值）、`sharpe`（夏普比率）、`win_rate`（按笔胜率）、
  `n_trades`（成交笔数）、`n_days`（交易日数）；分 `overall` / `in_sample` / `out_sample` 三段。
- **风控门控**（`RiskGate`）：`trade_suggestion_allowed`（是否允许生成交易建议）、
  `risk_banner`（报告顶部显著风险提示）、`constraint_boundaries`（强制约束边界清单）。

## 5. 设计约束

1. **沙箱边界**：`--sandbox local`（`LocalRestrictedSandbox`）仅用于开发调试，
   安全隔离不足（子进程 + AST 静态安检 + 资源限额 + 环境变量白名单的弱隔离），
   **属于缓释措施而非硬安全边界**——静态安检可被动态导入、编码混淆绕过，
   进程与文件系统均未真正隔离；执行不可信策略代码必须使用 Docker 沙箱。
   禁止生产使用，Release 默认 `DockerSandbox`（容器级隔离）。
   local 模式会在 CLI、日志与执行结果中强制展示红色警告。
   - **Docker 最小挂载**：容器只读挂载回测执行必需的 `backtest/` 与
     `core/markets.py`，不再整根挂载项目目录，并在挂载列表层面显式排除 `.env`
     及任何 `.env.*`；容器不接收宿主环境变量（仅白名单运行必需项）。
   - **local 密钥隔离**：子进程环境变量按白名单透传，名称含
     `KEY` / `TOKEN` / `SECRET` / `PRIVATE` 的宿主密钥一律剔除。
2. **mock 与真实模式切换**：环境变量 `QUANT_ASST_LLM_MOCK` 控制。真值
   （`1` / `true` / `yes` / `on`）启用 mock 离线后端，跳过真实 LLM、读本地预生成样例；
   假值（`0` / `false` / `no` / `off`）走真实 LiteLLM API。mock 模式同时设置
   `LITELLM_OFFLINE_MODE=true`，禁止 LiteLLM 后台拉取远端 cost 映射。
   `debate` / `audit` 在未检测到密钥时自动启用 mock，`--no-mock` 强制真实调用。
3. **数字来源约束**（硬约束 1）：Agent 不得在自由文本中编造财务数字；携带数字的
   schema（如 `BacktestResult`）由工具产出并序列化进 State，Agent 只读引用。
4. **产物不入库**：`output/` 与 `var/` 由 `.gitignore` 排除（锚定 `/output/`、`/var/`，
   并含 `*.parquet` 兜底），演示产物与本地缓存不会被提交到 GitHub。
