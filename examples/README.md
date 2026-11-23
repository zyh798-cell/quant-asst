# Examples 示例集（Step 7）

5 组可直接运行的示例脚本，用于 GitHub 仓库演示与快速上手。所有示例：

- 硬编码标的与参数，开箱即用；
- 默认启用 **mock 离线模式**（`QUANT_ASST_LLM_MOCK=1`），**无需 LLM 密钥、不消耗 token**；
- 仅依赖 `examples/` 目录内的脚本与公共底座 `_common.py`，不改动 `core` / `agents` / `report` 核心业务代码。

> 本项目仅用于教育与研究，不构成投资建议，不含实盘下单功能。

## 前置依赖

1. 安装依赖：

   ```powershell
   cd quant-asst
   uv sync
   ```

2. 环境自检（可选）：

   ```powershell
   uv run python cli.py doctor
   ```

3. `.env` 配置（可选）：示例默认走 mock，**无需配置任何密钥**。
   若需切换真实 LLM，再复制 `.env.example` 为 `.env` 并填写 `DEEPSEEK_API_KEY`。

4. 行情缓存（示例 03 / 04 需要）：示例标的是 `cn:600519`（贵州茅台），
   回测区间 `2024-11-17 ~ 2026-11-17`。本地已有缓存时完全离线；
   无缓存时会经 AkShare 联网抓取一次并写入 `var/market/`。

## 示例一览

| 示例 | 脚本 | 演示内容 | 适用场景 |
| --- | --- | --- | --- |
| 01 | `example_1_basic_debate.py` | 基础多空辩论，输出辩论 Markdown 报告 | 首次了解多 Agent 辩论链路 |
| 02 | `example_2_audit_only.py` | 对一份辩论报告单独执行红队审计 + 风控综合 | 只关心风险审计与定级 |
| 03 | `example_3_full_pipeline.py` | 回测 -> 辩论 -> 审计 -> 风控定级 -> md + HTML | 查看完整研究流水线 |
| 04 | `example_4_mock_offline.py` | 零密钥离线跑通全流程 | **新用户推荐入口** |
| 05 | `example_5_custom_threshold.py` | high / medium 阈值对比，演示严格模式拦截规则 | 理解风控门控阈值语义 |

## 推荐运行顺序

按以下顺序体验，可由点到线再到全链路，逐步理解各模块：

1. `example_1_basic_debate.py`：先看最基础的多空辩论，理解角色与裁决产物。
2. `example_2_audit_only.py`：在辩论基础上单独看红队审计与风控定级。
3. `example_3_full_pipeline.py`：把回测、辩论、审计、报告串成完整流水线。

其余两个示例按场景选用：

- `example_4_mock_offline.py`：**无密钥离线演示**，新用户推荐入口，零配置即可跑通全流程。
- `example_5_custom_threshold.py`：**风控阈值边界调试**，对比 high / medium 的拦截差异。

## 运行命令

在项目根目录执行（Windows PowerShell）：

```powershell
# 推荐：零密钥离线全流程演示
uv run python examples/example_4_mock_offline.py

# 其余示例
uv run python examples/example_1_basic_debate.py
uv run python examples/example_2_audit_only.py
uv run python examples/example_3_full_pipeline.py
uv run python examples/example_5_custom_threshold.py
```

Git Bash 等价写法：

```bash
cd ~/quant-asst
uv run python examples/example_4_mock_offline.py
```

## 各示例说明

### 示例 01：基础多空辩论

- 输入标的 `cn:600519` 与双均线策略描述，经 3 轮多空交替辩论、逐轮风控核验，
  输出裁决结论与修订策略建议。
- 预期产出：`output/debate_reports/<run_id>.md` 与 `.json`、`var/trajectories/<run_id>.jsonl`。

### 示例 02：单独红队审计

- 自动跑一场辩论生成输入，再执行红队审计（逻辑漏洞 / 过拟合 / 未来函数 /
  幸存者偏差 / 流动性陷阱五类）+ 风控综合，输出审计意见书与最终量化分析报告。
- 也可把脚本内 `SOURCE_JSON` 指向已有辩论报告 JSON，跳过自动辩论。
- 预期产出：`output/audit/audit_<ticker>_<timestamp>.md` 与 `final_<ticker>_<timestamp>.md`。

### 示例 03：全链路一键跑

- 依次执行：回测（自然语言 -> 假设 -> 代码 -> 沙箱）-> 辩论 -> 审计 -> 风控定级 ->
  输出 Markdown 双报告 + Plotly 交互式 HTML 报告。
- HTML 为静态单文件（内嵌 plotly.js，约 4.8 MB），浏览器直接打开即可查看
  K 线 / 买卖信号 / 净值 / 回撤交互图表。
- 预期产出：`output/debate_reports/` + `output/audit/` + `output/html/` 三类产物。

### 示例 04：离线 mock 模式演示

- 在**完全不配置 API 密钥**的前提下跑通全流程，所有 LLM 调用由脚本化 mock 后端接管，
  返回确定性、schema 合法的占位内容，无任何网络请求与真实模型消耗。
- 这是新用户推荐入口：零密钥、零 token、可安全重复执行。

### 示例 05：自定义风控阈值

- 对同一份辩论报告分别用 `high`（默认）与 `medium`（收紧）阈值执行审计，
  对比风险提示与约束边界的差异。
- mock 审计定级为「中（medium）」：`high` 阈值下不触发提示，`medium` 阈值下
  强制标注并列出约束边界；致命风险则与阈值无关，恒被拦截。
- 预期产出：两组 `output/audit/` 报告 + 终端对比结论。

## mock 模式说明

- 示例通过 `examples/_common.py` 在导入 `core` 之前设置 `QUANT_ASST_LLM_MOCK=1`，
  由 `MockCompletionBackend` 按 prompt 首行特征词判定角色并返回确定性 JSON。
- mock 同时设置 `LITELLM_OFFLINE_MODE=true`，禁止 LiteLLM 后台拉取远端 cost 映射，
  从而屏蔽离线场景下的网络重试告警。
- 如需真实 LLM：删除 `_common.py` 顶部的 `setdefault` 行，并在 `.env` 配置有效
  `DEEPSEEK_API_KEY`。示例脚本本身无需改动。

## 产物输出位置

| 产物 | 路径 |
| --- | --- |
| 辩论报告 md / json | `output/debate_reports/` |
| 审计意见书 / 最终分析报告 md | `output/audit/` |
| 交互式 HTML 报告 + 结构化 json | `output/html/` |
| 运行轨迹 | `var/trajectories/` |
| 行情缓存 | `var/market/` |

`output/` 与 `var/` 均已由 `.gitignore` 排除，不会提交到仓库。

## 现有策略模板

除示例外，`examples/` 另有两个策略契约模板，供回测引擎直接使用：

- `dual_ma.py`：双均线趋势跟踪策略（`generate_positions(df)` 契约合规模板）。
- `run_dual_ma_check.py`：硬编码双均线直跑校验（合成数据 + 本地缓存回归），
  用于验证引擎在「有趋势」行情下必然产生成交，防「零成交」事故回归。

```powershell
uv run python examples/run_dual_ma_check.py
```
