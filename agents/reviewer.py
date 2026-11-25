"""最终裁决员（ReviewerAgent）—— Step 4。

中立汇总裁决：整合多头、空头与全部轮次的风控核验材料；对策略可信度打分（0~100）；
总结共识与分歧；给出 adopt / reject / revise 结论；输出可直接送入回测引擎的
StrategyRevision。输出 DebateVerdict（Pydantic 校验，失败重试 1 次）。
"""

from __future__ import annotations

from typing import Any, ClassVar

from agents.context import backtest_context, market_label
from core.base import BaseAgent
from core.prompts.registry import render_prompt
from core.schemas import DebateVerdict
from core.state import QuantAsstState


def _fmt_risk(checks: list[dict]) -> str:
    """把各轮风控报告格式化为可读文本。"""
    if not checks:
        return "（无风控核验记录）"
    blocks = []
    for c in checks:
        findings = "\n".join(
            f"    - [{f.get('severity')}] {f.get('target_side')}: {f.get('issue')}"
            for f in c.get("findings", [])
        )
        blocks.append(
            f"  第 {c.get('round_no')} 轮：数据有效性 —— {c.get('data_validity', '')}\n"
            f"{findings}\n    留存多头索引 {c.get('kept_bull_points')} | "
            f"留存空头索引 {c.get('kept_bear_points')}\n"
            f"    建议：{c.get('recommendation', '')}"
        )
    return "\n".join(blocks)


class ReviewerAgent(BaseAgent[DebateVerdict]):
    """最终裁决员。"""

    role: ClassVar[str] = "reviewer"
    output_schema: ClassVar[type[DebateVerdict]] = DebateVerdict
    state_key: ClassVar[str] = "verdict"

    def build_messages(self, state: QuantAsstState) -> list[dict[str, str]]:
        symbol = state.get("symbol") or ""
        market = state.get("market") or ""
        bull_final = state.get("bull_draft") or {}
        bear_final = state.get("bear_draft") or {}

        bull_text = (
            f"观点：{bull_final.get('stance', '')}\n"
            + "\n".join(
                f"  - {p.get('claim')} | 证据({p.get('evidence_type')})：{p.get('evidence')}"
                for p in bull_final.get("points", [])
            )
        )
        bear_text = (
            f"观点：{bear_final.get('stance', '')}\n"
            + "\n".join(
                f"  - {p.get('claim')} | 证据({p.get('evidence_type')})：{p.get('evidence')}"
                for p in bear_final.get("points", [])
            )
        )
        risk_text = _fmt_risk(state.get("risk_checks") or [])

        material = (
            f"【多头最终观点】\n{bull_text}\n\n"
            f"【空头最终观点】\n{bear_text}\n\n"
            f"【各轮风控核验】\n{risk_text}"
        )

        system = render_prompt(
            self.role,
            symbol=symbol,
            market_label=market_label(market),
            user_input=state.get("user_input", ""),
            period_start=(state.get("hypothesis") or {}).get("period_start", ""),
            period_end=(state.get("hypothesis") or {}).get("period_end", ""),
            backtest_context=backtest_context(state),
            debate_material=material,
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": "请汇总三方材料并给出最终裁决。"},
        ]
