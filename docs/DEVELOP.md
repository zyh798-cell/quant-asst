# Quant Asst 开发指南

面向贡献者与二次开发者。本文说明项目初始化、新增 Agent / 示例脚本的规范、
测试约定与常见问题排查。架构背景见 [`ARCHITECTURE.md`](ARCHITECTURE.md)。

## 1. 项目初始化

```powershell
cd quant-asst
uv sync                # 创建 .venv 并安装依赖
uv run python cli.py doctor   # 环境自检（依赖 / Docker / 密钥 / 运行时目录）
```

未配置 `DEEPSEEK_API_KEY` 时，`debate` / `audit` 会自动切换 mock 离线模式，可无密钥跑通全流程。

## 2. 测试命令

```powershell
# 全量运行（含 examples 子进程回归，耗时较长）
uv run pytest

# 覆盖率
uv run pytest --cov=core --cov=agents --cov=backtest --cov=tools --cov=report

# 仅校验示例脚本可独立运行（mock 离线，不消耗 LLM token）
uv run pytest tests/test_examples.py

# 单模块调试
uv run pytest tests/test_audit.py -v
```

测试规范：

- **离线优先**：所有测试在 mock 模式下可跑，不依赖真实 API 密钥、不消耗 token、
  不产生网络请求（示例测试以子进程方式运行 5 个脚本）。
- **目录与命名**：测试置于 `tests/`，文件以 `test_` 开头，函数以 `test_` 开头；
  模块名与被测模块对应（如 `test_audit.py` 对应 `core/audit_graph.py` 与 `agents/redteam.py`）。
- **夹具隔离**：使用 `conftest.py` 的 `test_settings`（指向 `tmp_path`，不读 `.env`、
  不污染真实 `var/`）；固定环境变量用 `os.environ.setdefault` 设置。
- **命名一致性**：断言中的指标名、风险等级须与 `core/schemas.py` 一致
  （`low` / `medium` / `high` / `critical`；决策 `adopt` / `revise` / `reject` / `blocked`）。

### 持续集成（GitHub Actions）

- 工作流：`.github/workflows/ci.yml`，运行环境 `ubuntu-latest`。
- 触发时机：`push` 到 `main`、向 `main` 发起 `pull_request`。
- 步骤：`actions/checkout@v4` → `astral-sh/setup-uv@v5`（缓存 uv 与虚拟环境）→
  `uv python install 3.11` → `uv sync` → `uv run pytest`。
- 后端与 mock：单元测试用 `monkeypatch` 替换 `litellm.completion` 注入确定性响应，
  走真实 LiteLLM 后端路径，无需密钥；`tests/conftest.py` 会清除外部注入的
  `QUANT_ASST_LLM_MOCK`，保证本地与 CI 一致。示例测试由 `tests/test_examples.py`
  在子进程内自设 `QUANT_ASST_LLM_MOCK=1`。因此工作流**不注入全局 mock**——
  注入会切换到 `MockCompletionBackend`，使依赖 `litellm.completion` 注入的单元测试
  收不到响应而失败；工作流仅设置 `LITELLM_OFFLINE_MODE=true` 避免 litellm 导入期网络请求。
- 测试报告：`pytest --junitxml=pytest.xml`，并上传为 `pytest-report` artifact。
- badge：README 头部 tests 徽章指向该工作流状态；失败时 job 退出码非 0，徽章变红。
- 本地复现：`uv sync && uv run pytest`。

## 3. 新增一个 Agent

以「新增一个独立分析角色」为例，步骤如下（不改动既有 Agent 行为）：

1. **定义输出模型**：在 `core/schemas.py` 继承 `StrictModel`，声明字段与约束
   （`Field(description=...)`），禁止额外字段。
2. **实现 Agent 类**：在 `agents/<role>.py` 继承 `BaseAgent[S]`，声明三个类变量
   并实现 `build_messages`：

   ```python
   from typing import Any, ClassVar
   from agents.context import backtest_context
   from core.base import BaseAgent
   from core.schemas import YourOutput
   from core.state import QuantAsstState

   class YourAgent(BaseAgent[YourOutput]):
       role: ClassVar[str] = "your_role"
       output_schema: ClassVar[type[YourOutput]] = YourOutput
       state_key: ClassVar[str] = "your_report"

       def build_messages(self, state: QuantAsstState) -> list[dict[str, str]]:
           system = self.render_system(today="...", market_label="A股")
           user = backtest_context(state)          # 只注入工具返回的数据（硬约束 1）
           return [{"role": "system", "content": system},
                   {"role": "user", "content": user}]
   ```

3. **注册 prompt 模板**：新增 `core/prompts/templates/<role>.md`（首行须包含
   角色标识词，供 `MockCompletionBackend.infer_role` 判定；占位符用 `$var`），
   并在 `core/prompts/registry.py` 的 `ROLES` 中加入该角色名。
4. **接入状态机**：在 `core/*_graph.py` 增加节点（异常写入 `State["error"]`，图不崩溃），
   需要轮次累积时覆写 `merge_keys`。
5. **补 mock 语料**：在 `core/llm.py` 增加 `_mock_<role>_payload` 与角色分支，
   保证离线测试可跑。
6. **注册到 CLI 流程**：若需独立命令，在 `cli.py` 增加 `@app.command()`；
   参数与现有命令风格保持一致（`--no-mock` / `--threshold` / `--html`）。
7. **补单元测试**：在 `tests/` 增加 `test_<role>.py`，覆盖 schema 校验、
   mock 输出合法性、门控规则与端到端链路。

## 4. 行情缓存结构与复权口径

### 缓存文件

```
var/market/<market>/<code>__<start>__<end>[__<adjust>].parquet
```

- `start` / `end` 统一为 `YYYYMMDD`，便于 `YYYY-MM-DD` 与 `YYYYMMDD` 两种入参命中同一文件。
- `<adjust>` 为复权口径段，由适配器的 `ADJUST` 类属性声明（见 `data/adapters/base.py`）：
  - A 股 `cn_stock` → `qfq`（前复权），文件名形如
    `var/market/cn_stock/600519__20240101__20261128__qfq.parquet`；
  - 美股 `us_stock` → 空串（实际成交价、无复权概念），文件名形如
    `var/market/us_stock/AAPL__20240101__20261128.parquet`。
- 口径写入文件名的目的是**隔离**：切换复权口径必然落到不同文件，不会读到另一口径的数据。
  旧版本遗留的无口径文件（`<code>__<start>__<end>.parquet`）不再命中，会自动失效重建，
  无需手动清理（也不应手动改名复用）。

### 复权口径约定

| 市场 | 口径 | 说明 |
| --- | --- | --- |
| A 股 | `qfq` 前复权 | 回测口径。消除分红除权日的向下跳空，避免双均线等策略产生假金叉/死叉 |
| 美股 | 不复权 | 实际成交价。拆股/分红的连续性由数据源自带处理，本框架不做二次调整 |
| 港股 / 期货 / 加密 | 不复权 | 各适配器按原始行情归一 |

### 涨跌停价的推算

涨跌停价由「前收 × 板块系数」推算，并以最小报价单位（0.01）取**保守边界**：涨停上取整、
跌停下取整（`data/adapters/cn_stock.py`）。这样即便前复权价本身带有舍入误差，也不会把
一字涨停误判为可买入。比例关系在复权前后保持不变，因此引擎基于绝对价的涨跌停比较
（`backtest/engine.py`）在 qfq 数据下结论一致。

### 相关测试

- `tests/test_cn_stock_adapter.py`：qfq 透传、板块系数、保守边界、停牌补齐；
- `tests/test_adjust_regression.py`：合成除权跳空序列，对照「qfq 不产生假信号 /
  未复权会产生假信号」，并验证涨跌停判定在两种口径下一致；
- `tests/test_cache.py`：缓存路径含口径段、不同口径互不命中、遗留旧缓存自动失效。

## 5. 新增示例脚本规范

示例脚本放在 `examples/`，与核心代码隔离，要求：

- **头部注释四字段**：用途、适用场景、是否需要 API Key、是否依赖本地 parquet 缓存。
- **复用公共底座**：`import _common`，调用 `run_backtest` / `run_debate` /
  `run_audit` / `build_html` / `run_full_pipeline`，不要复制流程逻辑。
- **默认 mock**：`_common.py` 已在导入前设置 `QUANT_ASST_LLM_MOCK` 兜底，无需重复设置。
- **路径兼容**：不在脚本内硬编码绝对路径或 `chdir`；统一由 `_common.ensure_project_root()`
  保证工作目录为项目根，路径全部经 `pathlib` 处理（Windows / POSIX 分隔符通用）。
- **可清理**：产物落入 `output/`；可用 `examples/clean_examples_output.py` 一键清理。
- **被测试覆盖**：新示例应加入 `tests/test_examples.py` 的 `_CASES` 列表，
  确保子进程可独立运行。

## 6. 常见问题

### Windows PowerShell 目录切换

`cli.py` 依赖相对路径（`.env`、`var/`、`output/`、`data/`），必须先进入项目根目录：

```powershell
cd quant-asst
Get-Location                     # 确认当前位置
Get-ChildItem cli.py            # 应能看到 cli.py
```

判断是否在项目根：目录下应能看到 `cli.py`、`pyproject.toml`、`.env.example`。

### 环境变量不生效

- 确认使用的是**新开的终端窗口**：用户级永久变量写入后，已有进程不会自动读取。
- 确认没有同名进程级临时变量覆盖 `.env`：`$env:XXX` 优先于 `.env`。
- `.env` 只在项目根目录加载：先 `cd` 到项目根再运行。
- 检查变量名拼写与 LiteLLM 约定的密钥名（`DEEPSEEK_API_KEY` 等）。

### 密钥脱敏日志说明

- CLI 启动只打印密钥「存在 / 不存在」，绝不输出明文。
- 密钥不进入 `Settings`、trajectory、日志或报告；`describe_keys()` / `mask_secret()`
  仅用于展示存在性。请勿把密钥粘贴到聊天、issue 或录屏中。

### LiteLLM 离线告警处理

- mock 模式会在 `import litellm` 前设置 `LITELLM_OFFLINE_MODE=true`，
  禁止后台拉取远端 model cost 映射（GitHub raw），从而屏蔽网络重试告警。
- 若其他模块先于 `core.llm` 导入 litellm，导入期告警无法追溯消除（已用常量置 0 兜底）。
- 真实模式下该告警属正常行为，不影响功能。

### 未来函数确定性检查

`backtest/lookahead.py` 提供截断历史一致性审计：把数据截断到前 k 行重跑同一策略，
若截断窗口内的信号与全量运行不一致，说明策略引用了当时不可见的未来数据。

```bash
uv run python cli.py backtest cn:600519 --lookahead-check   # 检查不通过即中止回测（退出码 2）
```

默认关闭（成本考量：每个检查点多跑一次策略）。测试基建见 `tests/test_lookahead.py`：
对 `examples/dual_ma.py` 断言通过，对 ``shift(-n)`` / 全局统计量泄漏 / 反序引用
构造的作弊 fixture 断言必被抓到。

### 本地沙箱警告与密钥隔离

`--sandbox local` 会在 CLI、日志与执行结果中强制展示红色警告，这是预期行为，
提示该模式仅用于开发调试，禁止生产使用。Release 请使用 `--sandbox docker`。

⚠️ local 沙箱的定位是**缓释措施而非硬安全边界**：AST 静态安检可被动态导入、
编码混淆绕过，进程与文件系统也没有真正隔离。执行不可信策略代码必须使用 Docker 沙箱。

已实现的隔离加固（外部代码 review 第 3 项）：

- **环境变量白名单透传**：子进程只接收 `PATH` / `HOME` / `PYTHONPATH` 等运行必需项；
  名称含 `KEY` / `TOKEN` / `SECRET` / `PRIVATE` 的宿主密钥一律剔除，
  包括显式注入的疑似密钥变量。
- **Docker 最小挂载**：容器只读挂载 `backtest/` 与 `core/markets.py`，
  不再整根挂载项目目录；挂载列表层面显式排除 `.env` 及 `.env.*`；
  容器不接收宿主环境变量。

## 7. 参数网格寻优（optimize）

`cli.py optimize` 对策略参数做纯确定性网格遍历 + 样本外验证，不调用 LLM。
策略代码须遵守扩展后的契约：模块级 `PARAMS` 字典 + `generate_positions(df, params=None)`，
同一份代码因此可被不同参数组合重复调用（参考模板见 `examples/dual_ma.py`）。

```bash
# 花括号可省略；分号或空格分隔多个参数；也支持 JSON 写法
uv run python cli.py optimize cn:600519 --start 2024-01-01 --end 2024-12-31 \
    --strategy examples/dual_ma.py \
    --grid "short_window=5,10;long_window=20,30" \
    --train-ratio 0.7 --sandbox local
```

- **选优口径**：主指标固定为样本内夏普；另按样本内总收益给出对照排名，
  两者结论冲突时并列呈现，不做加权综合。
- **准入门槛**：样本内成交笔数 `< 5` 的组合标记 ineligible、不参与选优，
  报告单独列出并写明原因（避免「零成交 + 零回撤」噪声组合靠指标当选）。
- **防泄漏**：切分点在寻优开始前一次性固定，并校验各组合样本外起点一致；
  选优只读样本内指标，样本外仅在最终劣化判定时使用一次。
- **劣化判定**（命中任一即标注 `degraded`）：样本外夏普低于样本内的 50%；
  样本内正收益而样本外非正；样本外最大回撤比样本内更深超过 10 个百分点。
- **确定性**：无随机数、无时间戳；同一输入重复运行报告逐字节一致，
  文件名同样不含时间戳。组合数上限 100，超限拒绝执行并提示缩小网格。
- **产物**：`output/optimization/optimization_<symbol>_<start>_<end>.md`。
- **测试**：`tests/test_optimizer.py`（解析/展开、准入门槛、双指标对照、
  劣化触发、确定性、真实沙箱参数透传）。

## 8. 提交前检查清单

- [ ] `uv run pytest` 全量通过；
- [ ] 涉及核心逻辑改动时同步更新 `core/schemas.py` 与相关测试；
- [ ] 文档命令与 `cli.py` / `examples/` 实际文件名一致，无编造命令；
- [ ] `output/`、`var/`、`.env`、`*.parquet` 未被纳入提交（`.gitignore` 已覆盖）；
- [ ] 文档保持工程化文风，无 emoji、无口语化表述。
