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
   from core.state import QuantSentinelState

   class YourAgent(BaseAgent[YourOutput]):
       role: ClassVar[str] = "your_role"
       output_schema: ClassVar[type[YourOutput]] = YourOutput
       state_key: ClassVar[str] = "your_report"

       def build_messages(self, state: QuantSentinelState) -> list[dict[str, str]]:
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

## 4. 新增示例脚本规范

示例脚本放在 `examples/`，与核心代码隔离，要求：

- **头部注释四字段**：用途、适用场景、是否需要 API Key、是否依赖本地 parquet 缓存。
- **复用公共底座**：`import _common`，调用 `run_backtest` / `run_debate` /
  `run_audit` / `build_html` / `run_full_pipeline`，不要复制流程逻辑。
- **默认 mock**：`_common.py` 已在导入前设置 `QUANTSENTINEL_LLM_MOCK` 兜底，无需重复设置。
- **路径兼容**：不在脚本内硬编码绝对路径或 `chdir`；统一由 `_common.ensure_project_root()`
  保证工作目录为项目根，路径全部经 `pathlib` 处理（Windows / POSIX 分隔符通用）。
- **可清理**：产物落入 `output/`；可用 `examples/clean_examples_output.py` 一键清理。
- **被测试覆盖**：新示例应加入 `tests/test_examples.py` 的 `_CASES` 列表，
  确保子进程可独立运行。

## 5. 常见问题

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

### 本地沙箱警告

`--sandbox local` 会在 CLI、日志与执行结果中强制展示红色警告，这是预期行为，
提示该模式仅用于开发调试，禁止生产使用。Release 请使用 `--sandbox docker`。

## 6. 提交前检查清单

- [ ] `uv run pytest` 全量通过；
- [ ] 涉及核心逻辑改动时同步更新 `core/schemas.py` 与相关测试；
- [ ] 文档命令与 `cli.py` / `examples/` 实际文件名一致，无编造命令；
- [ ] `output/`、`var/`、`.env`、`*.parquet` 未被纳入提交（`.gitignore` 已覆盖）；
- [ ] 文档保持工程化文风，无 emoji、无口语化表述。
