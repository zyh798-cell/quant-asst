"""红队审计 + 风控综合流水线（Step 5）。

拓扑::

    START -> redteam -> gate -> risk_officer -> END

- ``redteam``：RedTeamAgent 产出 AuditReport（写 ``redteam_report`` / ``redteam_verdict``）。
- ``gate``：确定性风控门控（``core.risk_gate.apply_risk_gate``，不依赖 LLM，可复现），
  写 ``risk_gate``；致命风险拦截交易建议。
- ``risk_officer``：FinalRiskOfficerAgent 产出分析草稿（写 ``risk_report``），
  再与门控结论合并为 ``FinalAnalysisReport``（写 ``final_report``）。

产物：``AuditReport``（审计报告 md 载体）与 ``FinalAnalysisReport``（最终报告载体）。
本图独立于辩论图，在「辩论完成 -> 辩论报告 md 落盘」之后被调用。
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from agents.final_risk_officer import FinalRiskOfficerAgent
from agents.redteam import RedTeamAgent
from core.config import Settings
from core.risk_gate import advisory_for_decision, apply_risk_gate, final_decision
from core.schemas import FinalAnalysisReport, normalize_risk_level
from core.state import QuantAsstState
from core.trajectory import TrajectoryRecorder


def build_audit_graph(
    settings: Settings,
    run_id: str,
    source_run_id: str = "",
    threshold: str = "high",
    recorder: TrajectoryRecorder | None = None,
):
    """构建并编译红队审计 + 风控综合图。

    Args:
        settings: 全局配置。
        run_id: 本次审计 run_id（trajectory 文件名，写 ``redteam_report.audit_run_id``）。
        source_run_id: 被审计的辩论 run_id（写 ``redteam_report.source_run_id``）。
        threshold: 风险门控阈值（默认 high；可收紧为 medium）。
        recorder: 外部传入的轨迹记录器（缺省自建）。

    Returns:
        (compiled_graph, recorder)。
    """
    recorder = recorder or TrajectoryRecorder(run_id, settings.trajectory_dir)

    redteam = RedTeamAgent(settings, recorder)
    officer = FinalRiskOfficerAgent(settings, recorder)

    # ---- redteam 节点：审计意见书 + 填充 run_id 标识 ----
    def redteam_node(state: QuantAsstState) -> dict[str, Any]:
        try:
            result = redteam.run(state)
        except Exception as exc:  # noqa: BLE001
            recorder.log(node="redteam", event="error", payload={"error": str(exc)})
            return {"error": f"[redteam] {type(exc).__name__}: {exc}"}
        report = dict(result[redteam.state_key])
        # 用真实 run_id 覆盖 LLM 输出中的占位标识，保证可追溯
        report["audit_run_id"] = run_id
        report["source_run_id"] = source_run_id or report.get("source_run_id", "")
        level = normalize_risk_level(report.get("overall_risk_level"))
        recorder.log(node="redteam", event="output",
                     payload={"overall_risk_level": level,
                              "n_findings": len(report.get("findings", []))})
        return {"redteam_report": report, "redteam_verdict": level}

    # ---- gate 节点：确定性门控（不依赖 LLM）----
    def gate_node(state: QuantAsstState) -> dict[str, Any]:
        if state.get("error"):
            return {}
        gate = apply_risk_gate(state.get("redteam_report") or {}, threshold)
        recorder.log(node="gate", event="gate",
                     payload={"risk_level": gate.risk_level,
                              "trade_suggestion_allowed": gate.trade_suggestion_allowed,
                              "threshold": threshold})
        return {"risk_gate": gate.model_dump()}

    # ---- risk_officer 节点：分析草稿 + 合并为最终报告 ----
    def officer_node(state: QuantAsstState) -> dict[str, Any]:
        if state.get("error"):
            return {}
        try:
            result = officer.run(state)
        except Exception as exc:  # noqa: BLE001
            recorder.log(node="risk_officer", event="error", payload={"error": str(exc)})
            return {"error": f"[risk_officer] {type(exc).__name__}: {exc}"}
        draft = result[officer.state_key]
        gate = state.get("risk_gate") or {}
        outcome = state.get("debate_outcome") or {}

        decision = final_decision(state.get("redteam_report") or {},
                                  (outcome.get("verdict") or {}))
        # blocked 一致性：凡 final_decision == blocked（无论 critical 还是
        # tradability=prohibited），trade_advisory 必须清空并写入拦截说明文案，
        # 不能出现「决策已拦截、建议文本仍在输出」的不一致。
        trade_advisory = advisory_for_decision(decision, draft.get("trade_advisory", ""))

        final = FinalAnalysisReport(
            symbol=draft.get("symbol") or state.get("symbol") or "",
            market=draft.get("market") or state.get("market") or "",
            strategy_name=draft.get("strategy_name", ""),
            debate_run_id=source_run_id or outcome.get("run_id", ""),
            audit_run_id=run_id,
            final_decision=decision,
            credibility_score=draft.get("credibility_score", 0),
            overall_risk_level=normalize_risk_level(
                gate.get("risk_level") or draft.get("overall_risk_level")
            ),
            risk_gate=gate,
            executive_summary=draft.get("executive_summary", ""),
            key_findings=list(draft.get("key_findings") or []),
            recommendations=list(draft.get("recommendations") or []),
            trade_advisory=trade_advisory,
        )
        recorder.log(node="risk_officer", event="final",
                     payload={"final_decision": decision,
                              "overall_risk_level": final.overall_risk_level})
        return {
            "risk_report": draft,
            "final_report": final.model_dump(),
        }

    graph = StateGraph(QuantAsstState)
    graph.add_node("redteam", redteam_node)
    graph.add_node("gate", gate_node)
    graph.add_node("risk_officer", officer_node)
    graph.add_edge(START, "redteam")
    graph.add_edge("redteam", "gate")
    graph.add_edge("gate", "risk_officer")
    graph.add_edge("risk_officer", END)

    return graph.compile(), recorder
