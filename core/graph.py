"""LangGraph 状态机编排。

Step 3 拓扑（当前）::

    START -> hypothesis -> sandbox_backtest -> END

后续 Step 4-6 扩展为::

    hypothesis -> sandbox_backtest -> bull <-> bear (一轮辩论)
                                         -> risk -> redteam -> reviewer -> END

设计约定：
- 每个节点是 BaseAgent 子类或工具闭包，输出「增量字典」由 LangGraph 合并进 State；
- 节点异常不崩溃图：错误写入 State["error"]，条件边短路到 END（trajectory 全程留痕）；
- run_id 贯穿：trajectory 文件、沙箱工作区共用一个 ID（硬约束 4）；
- 红队判定 reject 时的回退重试随 Step 5 加入，iterations 计数防死循环。
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from langgraph.graph import END, START, StateGraph

from agents.hypothesis import HypothesisAgent
from core.config import Settings
from core.markets import Symbol
from core.schemas import HypothesisSpec
from core.state import QuantAsstState
from core.trajectory import TrajectoryRecorder
from tools.backtest_sandbox import run_backtest_in_sandbox
from tools.market_data import get_backtest_frame


def build_graph(
    settings: Settings,
    run_id: str,
    sandbox_mode: str = "local",
    recorder: TrajectoryRecorder | None = None,
):
    """构建编译后的 LangGraph 图。

    Args:
        settings: 全局配置。
        run_id: 本次运行唯一 ID（trajectory / 沙箱工作区共用）。
        sandbox_mode: 沙箱模式 docker | local（local 仅供开发调试）。
        recorder: 外部传入的轨迹记录器（缺省自建）。

    Returns:
        (compiled_graph, recorder) 二元组。
    """
    recorder = recorder or TrajectoryRecorder(run_id, settings.trajectory_dir)
    agent = HypothesisAgent(settings, recorder)

    # ---- 节点 1：HypothesisAgent（自然语言 -> Spec -> 代码）----
    def hypothesis_node(state: QuantAsstState) -> dict[str, Any]:
        try:
            return agent.run(state)
        except Exception as exc:  # noqa: BLE001 —— 节点错误写入 State，图不崩溃
            recorder.log(node="hypothesis", event="error", payload={"error": str(exc)})
            return {"error": f"[hypothesis] {type(exc).__name__}: {exc}"}

    # ---- 节点 2：沙箱回测（工具节点）----
    def backtest_node(state: QuantAsstState) -> dict[str, Any]:
        if state.get("error"):
            return {}
        try:
            spec = HypothesisSpec.model_validate(state["hypothesis"])
            symbol = Symbol.parse(spec.symbols[0])

            # 回测区间兜底：假设缺失/非法时用最近一年
            try:
                start = date.fromisoformat(spec.period_start).strftime("%Y-%m-%d")
            except ValueError:
                start = (date.today() - timedelta(days=365)).strftime("%Y-%m-%d")
            try:
                end = date.fromisoformat(spec.period_end).strftime("%Y-%m-%d")
            except ValueError:
                end = date.today().strftime("%Y-%m-%d")

            recorder.log(node="backtest", event="fetch_data",
                         payload={"symbol": symbol.full, "start": start, "end": end})
            df = get_backtest_frame(symbol, start, end, settings)
            recorder.log(node="backtest", event="data_ready",
                         payload={"n_rows": len(df)})

            output = run_backtest_in_sandbox(
                state["generated_code"], df, symbol, settings,
                mode=sandbox_mode, run_id=run_id,
            )
            recorder.log(
                node="backtest", event="result",
                payload={"overall": output.result.overall.model_dump(),
                         "sandbox_mode": output.sandbox_mode},
            )
            # 净值曲线从工作区明细读取（State 只存可序列化摘要）
            eq_path = settings.sandbox_workdir / run_id / "equity_curve.json"
            equity_curve = (
                json.loads(eq_path.read_text(encoding="utf-8")) if eq_path.exists() else {}
            )
            return {
                "backtest_result": output.result.model_dump(),
                "equity_curve": equity_curve,
            }
        except Exception as exc:  # noqa: BLE001 —— 同上
            recorder.log(node="backtest", event="error", payload={"error": str(exc)})
            return {"error": f"[backtest] {type(exc).__name__}: {exc}"}

    # ---- 条件边：hypothesis 出错则短路 ----
    def route_after_hypothesis(state: QuantAsstState) -> str:
        return END if state.get("error") else "sandbox_backtest"

    graph = StateGraph(QuantAsstState)
    graph.add_node("hypothesis", hypothesis_node)
    graph.add_node("sandbox_backtest", backtest_node)
    graph.add_edge(START, "hypothesis")
    graph.add_conditional_edges(
        "hypothesis", route_after_hypothesis,
        {"sandbox_backtest": "sandbox_backtest", END: END},
    )
    graph.add_edge("sandbox_backtest", END)

    return graph.compile(), recorder
