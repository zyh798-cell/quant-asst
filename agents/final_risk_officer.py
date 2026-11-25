"""风控综合官（FinalRiskOfficerAgent）—— Step 5。

独立于多空辩论。综合「辩论纪要」与「红队审计结果」两份材料，产出最终量化分析
意见（分析部分）：执行摘要、关键风险、改进建议、交易建议草稿。

交易建议是否放行**不由本 Agent 决定**——由流水线的确定性风控门控
（``core.schemas.RiskGate`` + 门控函数）依据审计风险级别判定：
致命风险禁止生成交易建议，高风险在报告顶部显著标注并强制写明约束边界。
输出 FinalAnalysisDraft（Pydantic 校验，失败重试 1 次）。
"""

from __future__ import annotations

from typing import Any, ClassVar

from agents.context import backtest_context, market_label
from core.base import BaseAgent
from core.prompts.registry import render_prompt
from core.schemas import FinalAnalysisDraft
from core.state import QuantAsstState


def _debate_material(state: QuantAsstState) -> str:
    """把辩论纪要（DebateOutcome dump）格式化为可读文本。"""
    outcome = state.get("debate_outcome") or {}
    if not outcome:
        return "（无辩论纪要，仅基于审计与回测结果分析）"
    verdict = outcome.get("verdict") or {}
    bull_final = outcome.get("bull_final") or {}
    bear_final = outcome.get("bear_final") or {}

    lines = [
        f"【裁决】可信度 {verdict.get('credibility_score', 'N/A')}/100 | "
        f"结论 {verdict.get('decision', '')}",
        f"  理由：{verdict.get('rationale', '')}",
    ]
    for label, arg in (("多头最终", bull_final), ("空头最终", bear_final)):
        points = "\n".join(
            f"    - {p.get('claim', '')}（证据类型 {p.get('evidence_type', '')}）"
            for p in arg.get("points", [])
        )
        lines.append(f"【{label}观点】{arg.get('stance', '')}\n{points}")
    if outcome.get("revised_strategy_text"):
        lines.append(f"【修订策略】{outcome['revised_strategy_text']}")
    return "\n".join(lines)


def _audit_material(state: QuantAsstState) -> str:
    """把红队审计意见书（AuditReport dump）格式化为可读文本。"""
    report = state.get("redteam_report") or {}
    if not report:
        return "（未执行红队审计）"
    lines = [
        f"综合风险定级：{report.get('overall_risk_level', '')}"
        f"（{report.get('risk_grade_label', '')}） | "
        f"交易建议可行性：{report.get('tradability', '')}",
        f"审计结论：{report.get('summary', '')}",
    ]
    findings = report.get("findings") or []
    if findings:
        lines.append("审计发现：")
        for f in findings:
            lines.append(
                f"  - [{f.get('severity', '')}] {f.get('category', '')}："
                f"{f.get('title', '')}\n      说明：{f.get('description', '')}"
                f"\n      建议：{f.get('recommendation', '')}"
            )
    else:
        lines.append("（无审计发现）")
    return "\n".join(lines)


class FinalRiskOfficerAgent(BaseAgent[FinalAnalysisDraft]):
    """风控综合官（独立角色，综合辩论 + 审计，输出最终分析意见）。"""

    role: ClassVar[str] = "risk_officer"
    output_schema: ClassVar[type[FinalAnalysisDraft]] = FinalAnalysisDraft
    state_key: ClassVar[str] = "risk_report"

    def build_messages(self, state: QuantAsstState) -> list[dict[str, str]]:
        symbol = state.get("symbol") or ""
        market = state.get("market") or ""

        system = render_prompt(
            self.role,
            symbol=symbol,
            market_label=market_label(market),
            user_input=state.get("user_input", ""),
            period_start=(state.get("hypothesis") or {}).get("period_start", ""),
            period_end=(state.get("hypothesis") or {}).get("period_end", ""),
            backtest_context=backtest_context(state),
            debate_material=_debate_material(state),
            audit_material=_audit_material(state),
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": "请综合辩论纪要与红队审计结果，输出最终量化分析意见。"},
        ]
