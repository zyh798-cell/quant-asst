"""多头分析师（BullAgent）—— Step 4。

仅从看多维度分析标的与策略：基本面 / 技术面 / 宏观 / 资金面构建看多逻辑，
识别策略收益来源与盈利情景。输出 BullArgument（Pydantic 校验，失败重试 1 次）。

继承 :class:`core.base.BaseAgent`，复用统一的 LLM 调用 + schema 校验 + trajectory 留痕。
"""

from __future__ import annotations

from typing import Any, ClassVar

from agents.context import backtest_context, debate_material, market_label
from core.base import BaseAgent
from core.prompts.registry import render_prompt
from core.schemas import BullArgument
from core.state import QuantSentinelState


class BullAgent(BaseAgent[BullArgument]):
    """多头分析师。"""

    role: ClassVar[str] = "bull"
    output_schema: ClassVar[type[BullArgument]] = BullArgument
    state_key: ClassVar[str] = "bull_draft"

    def build_messages(self, state: QuantSentinelState) -> list[dict[str, str]]:
        symbol = state.get("symbol") or ""
        market = state.get("market") or ""
        round_no = int(state.get("debate_round") or 1)
        max_rounds = int(state.get("debate_rounds") or 3)

        # 对手/历史材料：第 1 轮为空，之后附上空头草稿与既有留存论据
        opponent = (
            debate_material({"bear_draft": state.get("bear_draft"),
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
            {"role": "user", "content": f"请给出第 {round_no} 轮的多头论点。"},
        ]
