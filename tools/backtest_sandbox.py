"""回测沙箱工具：SandboxExecutor 抽象接口 + 双实现工厂 + 高层执行 API。

架构（shu 确认的沙箱方案）：
- **DockerSandbox**（``tools/sandbox_docker.py``）：Release 正式版本默认沙箱。
  LLM 生成代码在一次性容器内执行 —— 禁网、内存/CPU 限额、非 root、用后即毁。
- **LocalRestrictedSandbox**（``tools/sandbox_local.py``）：开发调试备选。
  独立子进程 + AST 静态安检（禁 os/subprocess/socket/requests 等高危模块）+
  超时与内存限额 + 仅允许读写沙箱工作区。
  ⚠️ 安全隔离不足，禁止生产使用，全程红色警告。

硬约束 3 的口径：默认形态为 Docker 容器执行；local 沙箱是需求方确认的
开发期例外（WSL 部署受阻），不得在 Release/生产环境启用。
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, Field

from backtest.market_rules import MarketRules, get_rules
from core.config import Settings
from core.markets import Market, Symbol
from core.schemas import BacktestResult

#: runner.py 模板：沙箱内唯一执行入口（宿主生成，属可信代码）
RUNNER_TEMPLATE = '''\
# -*- coding: utf-8 -*-
"""Quant Asst 沙箱执行入口（宿主生成，勿手改）。

流程：读 data.parquet -> 加载 strategy.generate_positions -> 事件回测 -> 写 result.json
"""
import json

import pandas as pd

from backtest.engine import run_event_backtest
from backtest.market_rules import MarketRules


def main() -> None:
    df = pd.read_parquet("data.parquet")
    with open("spec.json", encoding="utf-8") as f:
        spec = json.load(f)

    import strategy  # 被审计的策略代码（安检已通过）
    position_fn = strategy.generate_positions

    rules = MarketRules.load(spec["rules"])
    result = run_event_backtest(
        df,
        position_fn,
        rules,
        initial_capital=spec["initial_capital"],
        train_ratio=spec["train_ratio"],
        periods_per_year=spec["periods_per_year"],
    )
    with open("result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
'''


class SandboxResult(BaseModel):
    """沙箱执行结果（进程级信息，业务结果由 result.json 承载）。"""

    exit_code: int = Field(description="0 表示成功")
    stdout: str = Field(default="")
    stderr: str = Field(default="")
    duration_ms: int = Field(default=0)
    warnings: list[str] = Field(default_factory=list, description="安全警告（local 沙箱必带）")


class SandboxExecutor(ABC):
    """沙箱执行器抽象接口：双实现（Docker / Local）共存。"""

    @property
    @abstractmethod
    def mode(self) -> str:
        """沙箱模式标识：docker | local。"""

    @abstractmethod
    def execute(self, workdir: Path, entrypoint: str = "runner.py") -> SandboxResult:
        """在沙箱内执行 ``workdir`` 下的 ``entrypoint``。

        约定：工作区已由宿主备好 data.parquet / strategy.py / runner.py / spec.json；
        执行产物 result.json 写回同一工作区。
        """

    @abstractmethod
    def healthcheck(self) -> str:
        """返回沙箱可用性描述；不可用时抛异常。"""


class SandboxExecutionError(RuntimeError):
    """沙箱执行失败（非零退出 / 超时 / 结果文件缺失）。"""


class BacktestOutput(BaseModel):
    """回测工具完整输出：校验后的指标 + 沙箱执行信息 + 大体积明细。"""

    result: BacktestResult = Field(description="通过 schema 校验的回测指标")
    sandbox: SandboxResult = Field(description="沙箱执行信息（退出码/耗时/警告）")
    sandbox_mode: str = Field(description="沙箱模式：docker | local")
    details: dict = Field(
        default_factory=dict, description="明细：equity_curve（净值曲线）/ trades（成交列表）"
    )


def get_executor(settings: Settings, mode: str | None = None) -> SandboxExecutor:
    """沙箱工厂：mode 缺省取配置（默认 docker）。

    Raises:
        ValueError: mode 不支持。
    """
    resolved = (mode or "docker").lower()
    if resolved == "docker":
        # 延迟导入：本地环境未装 docker SDK 依赖时仍可用 local 沙箱
        from tools.sandbox_docker import DockerSandbox

        return DockerSandbox(settings)
    if resolved == "local":
        from tools.sandbox_local import LocalRestrictedSandbox

        return LocalRestrictedSandbox(settings)
    raise ValueError(f"不支持沙箱模式：{mode!r}（可选 docker | local）")


def run_backtest_in_sandbox(
    strategy_code: str,
    df: pd.DataFrame,
    symbol: Symbol,
    settings: Settings,
    mode: str | None = None,
    initial_capital: float = 1_000_000.0,
    train_ratio: float | None = None,
    rules_override: MarketRules | None = None,
    run_id: str = "manual",
) -> tuple[BacktestResult, SandboxResult]:
    """高层 API：把策略代码 + 行情数据送入沙箱执行回测，返回校验后的结果。

    步骤：准备工作区 -> 安检（executor 内部） -> 执行 -> 读 result.json ->
    BacktestResult schema 校验（硬约束 2 的工具侧落实）。

    Args:
        strategy_code: 策略代码文本（须定义 generate_positions(df) -> pd.Series）。
        df: 标准 OHLCV DataFrame。
        symbol: 回测标的。
        settings: 全局配置。
        mode: 沙箱模式（docker | local），缺省用配置默认。
        initial_capital: 初始资金。
        train_ratio: 样本内占比；None 用配置默认。
        rules_override: 覆盖市场默认规则（None 用 get_rules）。
        run_id: 工作区/轨迹 ID。

    Returns:
        BacktestOutput（result / sandbox / details 三合一）。

    Raises:
        SandboxExecutionError: 沙箱执行失败或结果校验失败。
    """
    workdir = settings.sandbox_workdir / run_id
    workdir.mkdir(parents=True, exist_ok=True)

    # ---- 备齐工作区 ----
    df.to_parquet(workdir / "data.parquet", index=False)
    (workdir / "strategy.py").write_text(strategy_code, encoding="utf-8")
    (workdir / "runner.py").write_text(RUNNER_TEMPLATE, encoding="utf-8")

    rules = rules_override or get_rules(symbol.market)
    periods_per_year = 365 if symbol.market == Market.CRYPTO else 252
    spec = {
        "rules": rules.dump(),
        "initial_capital": initial_capital,
        "train_ratio": train_ratio if train_ratio is not None else settings.train_test_split,
        "periods_per_year": periods_per_year,
    }
    (workdir / "spec.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ---- 执行 ----
    executor = get_executor(settings, mode)
    sandbox_result = executor.execute(workdir)

    result_path = workdir / "result.json"
    if sandbox_result.exit_code != 0 or not result_path.exists():
        tail = sandbox_result.stderr[-2000:] if sandbox_result.stderr else "(无 stderr)"
        raise SandboxExecutionError(
            f"沙箱执行失败（mode={executor.mode}, exit={sandbox_result.exit_code}）\n--- stderr 尾部 ---\n{tail}"
        )

    # ---- schema 校验（硬约束 2）----
    details: dict = {}
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        payload["symbol"] = symbol.full
        payload["market"] = symbol.market.value
        # 引擎输出为 metrics 嵌套结构，平铺为 schema 顶层字段
        metrics = payload.pop("metrics", {})
        for key in ("overall", "in_sample", "out_sample"):
            payload[key] = metrics[key]
        # 大体积明细（净值曲线/成交明细）不进 schema，从 payload 提取后随 details 返回
        for name in ("equity_curve", "trades"):
            detail = payload.pop(name, None)
            if detail is not None:
                details[name] = detail
                (result_path.parent / f"{name}.json").write_text(
                    json.dumps(detail, ensure_ascii=False), encoding="utf-8"
                )
        payload.setdefault("engine", "event_engine")
        # Step 6：明细回填 BacktestResult（equity_curve/trades 字段），
        # 供 HTML 可视化报告与回测链路共享同一份数据（不改变既有字段语义）。
        payload.setdefault("equity_curve", details.get("equity_curve", {}))
        payload.setdefault("trades", details.get("trades", []))
        backtest = BacktestResult.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 —— 校验失败统一转为明确异常
        raise SandboxExecutionError(f"回测结果未通过 BacktestResult schema 校验：{exc}") from exc

    # 零成交诊断：策略全程无信号时显式告警，避免「净值恒等于初始资金」被误读为回测成功
    if backtest.overall.n_trades == 0:
        sandbox_result.warnings.append(
            "策略在回测区间内无任何成交（n_trades=0）：请检查信号逻辑，"
            "或策略返回序列是否与 K 线行数对齐"
        )

    return BacktestOutput(
        result=backtest, sandbox=sandbox_result, sandbox_mode=executor.mode, details=details
    )
