<div align="center">

<img src="assets/brand/logo-color.svg" alt="Quant Asst logo" width="96" height="96">

# Quant Asst

**LLM Quant Analysis Agent**

<p>
  <img src="https://img.shields.io/badge/License-MIT-2ea44f" alt="License MIT">
  <img src="https://img.shields.io/badge/Python-%E2%89%A53.11-3776ab" alt="Python &gt;= 3.11">
  <img src="https://img.shields.io/badge/tests-pending-lightgrey" alt="tests status">
  <a href="https://github.com/zyh798-cell/quant-asst">
    <img src="https://img.shields.io/badge/zyh798--cell%2Fquant--ast-3776ab" alt="zyh798-cell/quant-asst">
  </a>
</p>

</div>

Quant Asst 是一个基于多 Agent 协作的量化策略研究与风控审计框架。它把自然语言策略假设解析为可执行代码，在本地沙箱内完成事件驱动回测，再经多空辩论、红队对抗审计与确定性风控分级，最终输出可归档的 Markdown 与可交互的 HTML 报告。项目仅用于研究与技术演示，不构成任何投资建议，不含实盘下单功能。

## 核心能力

- **自然语言策略解析**：把「双均线策略，5 日线上穿 20 日线买入」等描述解析为结构化假设（标的 / 区间 / 开平仓规则 / 参数），再生成符合契约的策略代码。
- **本地沙箱回测**：事件驱动引擎在沙箱内执行策略，输出总收益、年化收益、最大回撤、夏普比率、按笔胜率、成交笔数等指标，并做样本内 / 样本外切分。
- **多空辩论**：多头、空头、风控核验、最终裁决四类 Agent 多轮对抗，逐轮留痕，产出结构化裁决与可回测的修订建议。
- **红队审计**：独立于辩论的审计 Agent，挖掘逻辑漏洞、过拟合、未来函数、幸存者偏差、流动性陷阱等风险并定级（`low` / `medium` / `high` / `critical`）。
- **风控分级拦截**：确定性门控（不依赖 LLM、可复现）；致命风险恒拦截交易建议、决策为 `blocked`，高风险及以上强制标注并写明约束边界。
- **Markdown / HTML 双报告**：工程归档版 Markdown + 静态单文件 Plotly 交互式 HTML（K 线 / 买卖信号 / 净值 / 回撤）。
- **离线 mock 模式**：无需 LLM 密钥、不消耗 token，脚本化后端返回确定性且 schema 合法的样例输出，适合 CI 与新手体验。
- **行情本地缓存**：日线缓存优先读本地 Parquet，未命中经适配器抓取并写回，重复运行不重复联网。

## 快速开始

### 环境要求

- Python **3.11 或更高版本**（`pyproject.toml` 声明 `requires-python = ">=3.11"`）。
- [uv](https://docs.astral.sh/uv/) 作为依赖与虚拟环境管理器。

### 安装

```bash
git clone https://github.com/zyh798-cell/quant-asst.git
cd quant-asst
uv sync
```

### 配置密钥

```bash
cp .env.example .env    # 填写 DEEPSEEK_API_KEY
```

密钥按 LiteLLM 约定从进程环境变量读取，不进入配置对象、运行轨迹或日志。未配置密钥时，`debate` / `audit` 自动进入 mock 离线模式。

### 最小可运行示例

```bash
# 零密钥离线跑通全流程（推荐入口）
uv run python examples/example_4_mock_offline.py

# 配置密钥后：自然语言策略 -> 代码 -> 沙箱回测
uv run python cli.py run "双均线策略，5日线上穿20日线买入，死叉卖出"
```

`run` 默认使用 Docker 沙箱（Release 级隔离）；开发调试可加 `--sandbox local`（弱隔离，仅限本地）。

### CLI 子命令

| 命令 | 用途 |
| --- | --- |
| `run` | 从自然语言策略假设出发运行完整研究流水线（解析 → 代码 → 沙箱回测）。 |
| `debate` | 多智能体多空辩论，输出逐轮辩论 + 风控核验 + 裁决结论与修订建议。 |
| `audit` | 对已有辩论报告执行红队审计 + 风控综合，产出审计报告与最终量化分析报告。 |
| `fetch` | 抓取日线行情并写入本地 Parquet / DuckDB 缓存。 |
| `backtest` | 把策略文件送入沙箱执行回测，验证引擎链路。 |
| `doctor` | 环境自检：配置、依赖、Docker、Qdrant、运行时目录。 |
| `settings` | 打印当前生效配置（不含任何密钥）。 |

## 示例

`examples/` 提供 5 组开箱即用脚本，默认 mock 离线，无需密钥。完整说明与推荐运行顺序见 [`examples/README.md`](examples/README.md)。

| 脚本 | 用途 | 需要密钥 | 产物位置 |
| --- | --- | --- | --- |
| `example_1_basic_debate.py` | 基础多空辩论 | 否 | `output/debate_reports/` |
| `example_2_audit_only.py` | 单独红队审计 + 风控综合 | 否 | `output/audit/` |
| `example_3_full_pipeline.py` | 全链路（含 HTML 报告） | 否 | `output/`（三类） |
| `example_4_mock_offline.py` | 零密钥离线全流程（推荐入口） | 否 | `output/`（三类） |
| `example_5_custom_threshold.py` | 风控阈值边界调试 | 否 | `output/audit/` + 终端 |

示例 03 / 04 首次取数需联网经 AkShare 抓取一次并写入 `var/market/`，此后完全离线。

## 目录结构

```
quant-asst/
├── cli.py               # 命令行入口（typer）：run / debate / audit / fetch / backtest / doctor / settings
├── core/                # 配置、状态机（LangGraph）、LLM 封装与 mock 后端、schema、风控门控、轨迹
├── agents/              # 假设 / 多头 / 空头 / 风控核验 / 裁决 / 红队审计 / 风控综合
├── backtest/            # 事件驱动回测引擎、绩效指标、各市场规则
├── tools/               # 行情工具、沙箱执行器（docker / local）、回测沙箱
├── data/                # 行情适配器与本地 parquet 缓存层
├── report/              # 报告渲染：Markdown / Plotly HTML / 取数编排
├── audit/               # 审计编排与报告落盘
├── examples/            # 示例脚本集（5 组演示 + 策略模板 + 校验 + 清理）与 _common 公共底座
├── tests/               # pytest 单元测试与示例回归
├── docs/                # 架构、开发与品牌文档
├── assets/              # 品牌资产（Logo）
├── var/                 # 运行时数据（轨迹 / 行情缓存 / 沙箱工作区，不入库）
└── output/              # 交付物（辩论 / 审计 / HTML 报告，不入库）
```

源码以扁平包组织（`core` / `agents` / `tools` / `data` / `backtest` / `report` / `audit`），不使用 `src/` 容器。

## 文档

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)：分层结构、模块职责、数据流与设计约束。
- [`docs/DEVELOP.md`](docs/DEVELOP.md)：项目初始化、新增 Agent / 示例规范、测试约定与排查。
- [`docs/BRAND.md`](docs/BRAND.md)：品牌名称、Logo 资产、色彩与使用约定。
- [`examples/README.md`](examples/README.md)：示例脚本一览、推荐运行顺序与产物说明。

## 风险声明

**本项目仅用于量化研究与技术演示，不构成任何投资建议，不含实盘下单功能。**

- 所有回测、辩论、审计与风控结论均基于给定假设、数据口径与模型参数，**历史回测结果不代表未来收益**。
- 策略代码由 LLM 生成并在沙箱内执行；本地受限沙箱（`--sandbox local`）安全隔离不足，仅用于开发调试，禁止生产使用。
- 风控分级拦截是研究流程内的确定性规则，用于暴露风险与约束边界，不构成对任何标的安全性的背书或交易建议。
- 使用者应自行核实数据与结论，独立承担决策后果。

## 许可

本项目采用 [MIT License](LICENSE) 发布，署名 [zyh798-cell](https://github.com/zyh798-cell)。

行情数据来自 [AkShare](https://akshare.akfamily.xyz/) 与 [CCXT](https://github.com/ccxt/ccxt)，仅作研究用途；模型调用基于 [LiteLLM](https://docs.litellm.ai/)，状态机编排基于 [LangGraph](https://github.com/langchain-ai/langgraph)，可视化基于 [Plotly](https://plotly.com/python/)。
