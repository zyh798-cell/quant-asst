"""多空辩论 LangGraph 状态机（Step 4）。

拓扑（每轮 3 个节点，最多 ``debate_rounds`` 轮）::

    START -> round_start -> bull -> bear -> risk_check -> (下一轮 round_start | reviewer) -> END

设计要点：
- **逐轮留痕**：bull_draft / bear_draft 每轮被覆盖，round_transcripts 累积逐轮原文；
- **确定性映射**：risk_check 节点在 bull/bear 写入后执行，LangGraph 按边顺序推进，
  故 State 中 bull_draft/bear_draft 必为当轮草稿，不存在读到旧轮次的歧义；
- **异常不崩溃**：节点异常写入 ``State["error"]``，条件边短路到 reviewer（尽力出裁决）；
- **防死循环**：``debate_round`` 递增 + ``max_rounds`` 上限，超出即进入裁决。

产物：``DebateOutcome``（完整纪要 + 逐轮原文 + 修订策略文本）。
"""

from __future__ import annotations

import json
from typing import Any

from langgraph.graph import END, START, StateGraph

from agents.bear import BearAgent
from agents.bull import BullAgent
from agents.reviewer import ReviewerAgent
from agents.risk_officer import RiskCheckAgent
from core.config import Settings
from core.schemas import DebateOutcome
from core.state import QuantAsstState
from core.trajectory import TrajectoryRecorder


def build_debate_graph(
    settings: Settings,
    run_id: str,
    max_rounds: int = 3,
    recorder: TrajectoryRecorder | None = None,
):
    """构建并编译辩论图。

    Args:
        settings: 全局配置。
        run_id: 本次辩论 run_id（trajectory 共用）。
        max_rounds: 最大辩论轮次（上限 3）。
        recorder: 外部传入的轨迹记录器（缺省自建）。

    Returns:
        (compiled_graph, recorder)。
    """
    recorder = recorder or TrajectoryRecorder(run_id, settings.trajectory_dir)

    bull = BullAgent(settings, recorder)
    bear = BearAgent(settings, recorder)
    risk = RiskCheckAgent(settings, recorder)
    reviewer = ReviewerAgent(settings, recorder)

    def _wrap(agent, node: str):
        """包装节点：异常写入 State['error']，图不崩溃。"""
        def _node(state: QuantAsstState) -> dict[str, Any]:
            try:
                return agent.run(state)
            except Exception as exc:  # noqa: BLE001
                recorder.log(node=node, event="error", payload={"error": str(exc)})
                return {"error": f"[{node}] {type(exc).__name__}: {exc}"}
        return _node

    # ---- 轮次控制 ----
    def round_start(state: QuantAsstState) -> dict[str, Any]:
        round_no = int(state.get("debate_round") or 0) + 1
        recorder.log(node="meta", event="round_start", payload={"round": round_no})
        return {
            "debate_round": round_no,
            "bull_draft": {},
            "bear_draft": {},
            "risk_verdict": {},
        }

    def route_next(state: QuantAsstState) -> str:
        """达到最大轮次或有错误时进入裁决，否则继续下一轮。"""
        if state.get("error"):
            return "reviewer"
        if int(state.get("debate_round") or 0) >= int(state.get("debate_rounds") or max_rounds):
            return "reviewer"
        return "round_start"

    # ---- 各角色节点 ----
    bull_node = _wrap(bull, "bull")
    bear_node = _wrap(bear, "bear")

    def risk_node(state: QuantAsstState) -> dict[str, Any]:
        """风控校验：写报告并累积逐轮原文/留存论据索引（同节点内合并）。

        逐轮原文在此**整体重建**（旧序列 + 本轮草稿 + 当轮报告）：LangGraph 的
        节点增量先读后写，若依赖本节点刚写入的 State 字段会读不到，故以入参为准。
        """
        if state.get("error"):
            return {}
        try:
            result = risk.run(state)
        except Exception as exc:  # noqa: BLE001
            recorder.log(node="risk", event="error", payload={"error": str(exc)})
            return {"error": f"[risk] {type(exc).__name__}: {exc}"}
        report = result[risk.state_key]
        round_no = int(state.get("debate_round") or 1)

        prev_checks = list(state.get("risk_checks") or [])
        prev_transcripts = list(state.get("round_transcripts") or [])
        kept_bull = list(state.get("bull_kept") or [])
        kept_bear = list(state.get("bear_kept") or [])

        # 幂等保护：已记录到本轮则不重复追加
        if not prev_transcripts or int(prev_transcripts[-1].get("round") or 0) < round_no:
            prev_transcripts = [
                *prev_transcripts,
                {
                    "round": round_no,
                    "bull": state.get("bull_draft") or {},
                    "bear": state.get("bear_draft") or {},
                    "risk_check": report,
                },
            ]
            prev_checks = [*prev_checks, report]
            kept_bull.append(list(report.get("kept_bull_points") or []))
            kept_bear.append(list(report.get("kept_bear_points") or []))

        return {
            "risk_draft": report,
            "risk_checks": prev_checks,
            "risk_verdict": report,
            "bull_kept": kept_bull,
            "bear_kept": kept_bear,
            "round_transcripts": prev_transcripts,
        }

    # ---- 裁决与汇总 ----
    def review_node(state: QuantAsstState) -> dict[str, Any]:
        try:
            result = reviewer.run(state)
        except Exception as exc:  # noqa: BLE001
            recorder.log(node="reviewer", event="error", payload={"error": str(exc)})
            return {"error": f"[reviewer] {type(exc).__name__}: {exc}"}
        verdict = result[reviewer.state_key]

        revision_text = ""
        if verdict.get("revision"):
            revision_text = _ensure_symbol_prefix(
                verdict["revision"].get("revised_strategy_text", ""), state.get("symbol") or ""
            )

        outcome = DebateOutcome(
            run_id=run_id,
            symbol=state.get("symbol") or "",
            market=state.get("market") or "",
            user_input=state.get("user_input", ""),
            rounds=int(state.get("debate_round") or 0),
            round_transcripts=list(state.get("round_transcripts") or []),
            bull_final=_last_valid_arg(state.get("round_transcripts"), "bull"),
            bear_final=_last_valid_arg(state.get("round_transcripts"), "bear"),
            risk_checks=list(state.get("risk_checks") or []),
            verdict=verdict,
            revised_strategy_text=revision_text,
        )
        recorder.log(node="reviewer", event="outcome",
                     payload={"credibility_score": verdict.get("credibility_score"),
                              "decision": verdict.get("decision")})
        return {"debate_outcome": outcome.model_dump(), "revised_strategy_text": revision_text}

    graph = StateGraph(QuantAsstState)
    graph.add_node("round_start", round_start)
    graph.add_node("bull", bull_node)
    graph.add_node("bear", bear_node)
    graph.add_node("risk_check", risk_node)
    graph.add_node("reviewer", review_node)

    graph.add_edge(START, "round_start")
    graph.add_edge("round_start", "bull")
    graph.add_edge("bull", "bear")
    graph.add_edge("bear", "risk_check")
    graph.add_conditional_edges(
        "risk_check", route_next,
        {"round_start": "round_start", "reviewer": "reviewer"},
    )
    graph.add_edge("reviewer", END)

    return graph.compile(), recorder


def _last_valid_arg(transcripts: list[dict], side: str) -> dict[str, Any]:
    """从逐轮原文中取最后一轮非空的多/空观点。"""
    for t in reversed(transcripts or []):
        arg = t.get(side)
        if arg and arg.get("points"):
            return arg
    return {}  # type: ignore[return-value]


def _ensure_symbol_prefix(text: str, symbol: str) -> str:
    """确保修订策略文本带标的标识，便于直接作为 ``cli.py run`` 输入被正确解析。

    裁决文本常省略标的（如「宁德时代趋势跟随策略…」），而 run 命令依赖用户描述中的
    代码推断标的。此处在开头补 ``<symbol>`` 前缀，保证回测落到辩论标的上。
    """
    if not text:
        return text
    if symbol and symbol not in text[: len(symbol) + 4]:
        return f"{symbol} {text}"
    return text


def save_outcome(outcome: dict, out_dir) -> str:
    """把 DebateOutcome 落盘为 JSON（供 CLI / 报告模块复用）。"""
    from pathlib import Path

    path = Path(out_dir) / "debate_reports"
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / f"{outcome.get('run_id', 'debate')}.json"
    file_path.write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(file_path)
