"""红队审计员（RedTeamAgent）—— Step 5。

独立于多空辩论，对量化观点、回测参数、信号逻辑做反向压力审计：
挖掘策略逻辑漏洞、过拟合风险、未来函数、幸存者偏差、流动性陷阱，
输出独立审计意见书（只做风险定级低/中/高/致命，不参与多空辩论、不下交易结论）。
输出 AuditReport（Pydantic 校验，失败重试 1 次）。

继承 :class:`core.base.BaseAgent`，复用统一的 LLM 调用 + schema 校验 + trajectory 留痕。
"""

from __future__ import annotations

from typing import Any, ClassVar

from agents.context import backtest_context, market_label
from core.base import BaseAgent
from core.prompts.registry import render_prompt
from core.schemas import AuditReport
from core.state import QuantSentinelState


def _audit_material(state: QuantSentinelState) -> str:
    """组装被审计材料：辩论纪要 + 修订策略文本 + 回测上下文。

    红队审计针对的是「辩论输出」，故材料以 debate_outcome 为主；
    若仅有 backtest_result（单独对回测结果审计）则退化为回测上下文。
    """
    outcome = state.get("debate_outcome") or {}
    parts: list[str] = []

    if outcome:
        verdict = outcome.get("verdict") or {}
        parts.append(
            f"【辩论裁决】可信度 {verdict.get('credibility_score', 'N/A')}/100 | "
            f"结论 {verdict.get('decision', '')}\n"
            f"  理由：{verdict.get('rationale', '')}"
        )
        consensus = verdict.get("consensus") or []
        disagreements = verdict.get("disagreements") or []
        if consensus:
            parts.append("  共识：" + "；".join(consensus))
        if disagreements:
            parts.append("  分歧：" + "；".join(disagreements))

        bull_final = outcome.get("bull_final") or {}
        bear_final = outcome.get("bear_final") or {}
        for label, arg in (("多头", bull_final), ("空头", bear_final)):
            if arg:
                points = "\n".join(
                    f"    - {p.get('claim', '')}（证据类型 {p.get('evidence_type', '')}）"
                    for p in arg.get("points", [])
                )
                parts.append(f"【{label}最终观点】{arg.get('stance', '')}\n{points}")

        if outcome.get("revised_strategy_text"):
            parts.append(f"【修订后策略文本】{outcome['revised_strategy_text']}")
        parts.append(
            f"【标的 {outcome.get('symbol', '')} | 轮次 {outcome.get('rounds', 0)}"
            f" | 原始描述：{outcome.get('user_input', '')}】"
        )
    else:
        parts.append("（无辩论纪要，仅就回测结果与策略描述审计）")

    return "\n\n".join(parts)


class RedTeamAgent(BaseAgent[AuditReport]):
    """红队审计员（独立角色，不站队多空，只做风险定级）。"""

    role: ClassVar[str] = "redteam"
    output_schema: ClassVar[type[AuditReport]] = AuditReport
    state_key: ClassVar[str] = "redteam_report"

    def build_messages(self, state: QuantSentinelState) -> list[dict[str, str]]:
        symbol = state.get("symbol") or ""
        market = state.get("market") or ""
        material = _audit_material(state)

        # 审计 run_id 由图节点在调用前写入 state（见 audit_graph）
        system = render_prompt(
            self.role,
            symbol=symbol,
            market_label=market_label(market),
            user_input=state.get("user_input", ""),
            period_start=(state.get("hypothesis") or {}).get("period_start", ""),
            period_end=(state.get("hypothesis") or {}).get("period_end", ""),
            backtest_context=backtest_context(state),
            audit_material=material,
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": "请对上述材料做反向压力审计，输出审计意见书。"},
        ]
