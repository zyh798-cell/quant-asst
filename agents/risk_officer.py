"""风控核验员（RiskCheckAgent）—— Step 4。

中立角色，不站队多空。逐轮校验多头/空头草稿：核查数据有效性、逻辑矛盾、假设是否
脱离现实；识别幸存者偏差、参数偏差、流动性陷阱与回测过拟合；剔除不可证伪的主观猜想。
输出 RiskCheckReport（Pydantic 校验，失败重试 1 次）。
"""

from __future__ import annotations

from typing import Any, ClassVar

from agents.context import backtest_context, debate_material, market_label
from core.base import BaseAgent
from core.prompts.registry import render_prompt
from core.schemas import RiskCheckReport
from core.state import QuantSentinelState


class RiskCheckAgent(BaseAgent[RiskCheckReport]):
    """风控核验员（每轮对多空双方做一次独立校验）。

    累积型状态（risk_checks / round_transcripts / bull_kept / bear_kept）由辩论图的
    ``risk_check`` 节点在同节点内合并写入 —— ``BaseAgent.run()`` 只返回
    ``{state_key: dump}``，此时同节点其他字段尚未落 State，故累积不能放在 run() 里。
    """

    role: ClassVar[str] = "risk"
    output_schema: ClassVar[type[RiskCheckReport]] = RiskCheckReport
    state_key: ClassVar[str] = "risk_draft"

    def build_messages(self, state: QuantSentinelState) -> list[dict[str, str]]:
        symbol = state.get("symbol") or ""
        market = state.get("market") or ""
        round_no = int(state.get("debate_round") or 1)

        material = debate_material(
            {"bull_draft": state.get("bull_draft"),
             "bear_draft": state.get("bear_draft"),
             "bull_kept": state.get("bull_kept"),
             "bear_kept": state.get("bear_kept")},
            side="both",
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
            debate_material=material,
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": f"请对第 {round_no} 轮多空论点做独立风控核验。"},
        ]
