<div align="center">

<img src="assets/brand/logo-color.svg" alt="Quant Asst logo" width="96" height="96">

# Quant Asst

**LLM Quant Analysis Agent**

<p>
  <img src="https://img.shields.io/badge/License-MIT-2ea44f" alt="License MIT">
  <img src="https://img.shields.io/badge/Python-%E2%89%A53.11-3776ab" alt="Python &gt;= 3.11">
  <a href="https://github.com/zyh798-cell/quant-asst/actions/workflows/ci.yml">
    <img src="https://github.com/zyh798-cell/quant-asst/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
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
├── docs/                # 架构、开发、品牌与前端设计规范文档
├── assets/              # 品牌资产（Logo）与首屏场景参考图
├── web/app/             # 官网首页 + 动态工具站（Vite + React 19 + TS + Tailwind v4）
├── server/              # FastAPI 薄接口层（Step B：复用 core/backtest/report/audit）
├── var/                 # 运行时数据（轨迹 / 行情缓存 / 沙箱工作区，不入库）
└── output/              # 交付物（辩论 / 审计 / HTML 报告，不入库）
```

源码以扁平包组织（`core` / `agents` / `tools` / `data` / `backtest` / `report` / `audit`），不使用 `src/` 容器。

## Web 应用（官网首页 + 工具站）

前端位于 [`web/app/`](web/app/)，技术栈为 **Vite 8 + React 19 + TypeScript + Tailwind CSS v4 + shadcn 风格组件 + Zustand + TanStack Query + Recharts**，滚动叙事使用 GSAP ScrollTrigger + Lenis。

- **`/`** 官网首页：分层构建的动漫工作台首屏（人物 / 桌椅 / 三台显示器 / 屏幕内容 / 桌面道具各自独立 SVG 层，屏幕内容为可替换的 canvas 区域），K 线逐根生长的确定性动画，全流程能力、流水线、多空辩论、风控分级、双格式报告五个叙事区块。
- **`/studio`** 动态工具站：策略配置 → 流水线状态 → 回测指标与净值 / 回撤曲线 / 成交记录 → 辩论审计视图 → Markdown 报告下载。默认走本地确定性 mock，无需密钥。

本地预览：

```bash
cd web/app
npm install
npm run dev        # http://localhost:5173
```

生产构建：

```bash
cd web/app
npm run build      # 产物在 web/app/dist/
npm run preview
```

### Step B：双端联调（接口层 + 工具站）

接口层位于 [`server/`](server/)，是**薄编排层**：只做 HTTP 契约、任务状态机与产物 DTO 转换，策略逻辑全部复用 `core` / `agents` / `tools` / `backtest` / `report` / `audit`，不新写策略代码，也不接触密钥。

启动顺序（两个终端，先后端后前端）：

```bash
# 终端 1：接口层
uv run uvicorn server.main:app --reload --port 8000

# 终端 2：工具站
cd web/app
npm run dev        # http://localhost:5173
```

- 前端默认直连 `http://localhost:8000`，可用环境变量 `VITE_API_BASE` 覆盖；后端 CORS 已放行 `http://localhost:5173` 与 `http://127.0.0.1:5173`。`vite.config.ts` 另配了 `/api` 代理作为备选。
- 工具站的运行模式由配置切换：**mock 离线**在浏览器本地生成确定性样例（无需密钥、无需后端）；**真实模式**把请求发往后端接口层。真实模式创建任务后每 1.5 秒轮询一次状态，**阶段完成即增量渲染**，不等全流程结束。
- 密钥按 LiteLLM 约定从进程环境变量读取；接口层对已知密钥值与 `sk-*` / `api_key=` 字面量做脱敏，**密钥不会出现在任何响应字段、任务快照或错误文本中**（见 `tests/test_api.py` 的泄漏断言）。

接口简表：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/analyses` | 创建分析任务，后台执行，返回 `201` + 初始状态 |
| `GET` | `/api/analyses` | 任务列表（按创建时间倒序，便于调试） |
| `GET` | `/api/analyses/{id}` | 任务状态 + 已完成阶段产物（前端轮询） |
| `GET` | `/api/analyses/{id}/report?format=md\|html` | 报告正文，`Content-Type` 为 `text/markdown` 或 `text/html` |
| `GET` | `/api/health` | 健康检查，返回 `{"status":"ok","mode":"mock\|real"}` |

任务状态机：`pending → running → stage_done → completed`，异常转 `failed` 并写入脱敏后的错误信息；六个阶段 `parse → backtest → debate → audit → risk → report` 各自独立记录 `pending / running / done / failed / skipped` 与结构化产物。任务执行串行化，保证进程级 `QUANTSENTINEL_LLM_MOCK` / `LITELLM_OFFLINE_MODE` 不与并发任务互串。报告落盘于 `var/reports/<task_id>/`（Markdown + JSON + 单文件 HTML）。

### 素材与裂图根因

首屏场景素材统一放在 `web/app/src/assets/hero/`，按层命名（`person` / `desk` / `monitor-main` / `monitor-side-1` / `monitor-side-2` / `screen-content-*` / `props-desk`），屏幕内容区单独透明遮罩容器，可整体替换。

**品牌资产一律通过 Vite import 引入**（如 `import logo from '@/assets/brand/logo-color.svg'`），禁止在 `index.html` 或 CSS 中写 `../../assets/...` 相对路径——GitHub Pages 子路径部署时 `..` 会被服务器拒绝，导致 Logo 裂图。旧静态落地页方案即因此废弃，目录已移除，避免出现双首页。

视觉规范见 [`docs/design/`](docs/design/)：色值、间距、字体、圆角、阴影、动效参数只在 `TOKENS.md` 定义一次，前端通过 Tailwind v4 的 `@theme`（CSS variables）映射，页面样式全部引用令牌。

## 文档

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)：分层结构、模块职责、数据流与设计约束。
- [`docs/DEVELOP.md`](docs/DEVELOP.md)：项目初始化、新增 Agent / 示例规范、测试约定与排查。
- [`docs/BRAND.md`](docs/BRAND.md)：品牌名称、Logo 资产、色彩与使用约定。
- [`docs/design/README.md`](docs/design/README.md)：前端设计规范入口（设计令牌、禁用清单、金融数据产品准则）。
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
