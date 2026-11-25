"""空头分析师（BearAgent）—— Step 4。

仅从看空维度分析标的与策略：识别策略缺陷、标的利空、失效场景、尾部风险与过拟合；
指出逻辑漏洞与历史失效案例。输出 BearArgument（Pydantic 校验，失败重试 1 次）。
"""

from __future__ import annotations

from typing import Any, ClassVar

from agents.context import backtest_context, debate_material, market_label
from core.base import BaseAgent
from core.prompts.registry import render_prompt
from core.schemas import BearArgument
from core.state import QuantAsstState


class BearAgent(BaseAgent[BearArgument]):
    """空头分析师。"""

    role: ClassVar[str] = "bear"
    output_schema: ClassVar[type[BearArgument]] = BearArgument
    state_key: ClassVar[str] = "bear_draft"

    def build_messages(self, state: QuantAsstState) -> list[dict[str, str]]:
        symbol = state.get("symbol") or ""
        market = state.get("market") or ""
        round_no = int(state.get("debate_round") or 1)
        max_rounds = int(state.get("debate_rounds") or 3)

        opponent = (
            debate_material({"bull_draft": state.get("bull_draft"),
                             "bull_kept": state.get("bull_kept"),
                             "bear_kept": state.get("bear_kept"),
                             "risk_verdict": state.get("risk_verdict")})
            if round_no > 1 else "（首轮，无对手材料）"
        )
        system = render_prompt(
            self.role,
            symbol=symbol,
            market_label=market_label(market),
            user_input=state.get("user_input", ""),
            period_start=(state.get("hypothesis") or {}).get("period_start", ""),
            period_end=(state.get("hypothesis") or {}).get("period_end", ""),
            backtest_context=backtest_context(state),
            round_no=round_no,
            max_rounds=max_rounds,
            opponent_context=f"【本轮需回应的对手材料与历史】\n{opponent}",
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": f"请给出第 {round_no} 轮的空头论点。"},
        ]
