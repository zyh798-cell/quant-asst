"""HypothesisAgent —— 自然语言 → 结构化量化假设 → 策略代码（Step 3）。

两跳输出：
1. **结构化跳**：自然语言 + 市场 → HypothesisSpec（Pydantic 校验，失败重试 1 次，硬约束 2）；
2. **代码跳**：HypothesisSpec → 策略代码文本（generate_positions 契约 + 静态安检，
   违规把安检结果回灌模型重试，重试次数仍为 settings.llm_max_retries）。

安全红线（安检不通过即拒绝）：
- 禁 import 高危模块（os/subprocess/socket/requests ...，见 tools.sandbox_local 黑名单）；
- 禁 eval/exec/compile/__import__ 与 open() 路径逃逸；
- 必须定义 generate_positions(df) 入口函数。
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, ClassVar

from core.config import Settings
from core.llm import complete
from core.llm import complete_structured
from core.prompts.registry import render_prompt
from core.schemas import HypothesisSpec
from core.state import QuantAsstState
from core.trajectory import TrajectoryRecorder
from tools.sandbox_local import audit_strategy_code

#: 市场中文名（prompt 展示用）
_MARKET_LABELS: dict[str, str] = {
    "cn_stock": "A股", "us_stock": "美股", "hk_stock": "港股（中国香港市场）",
    "futures": "期货", "crypto": "加密货币",
}

#: 代码生成契约（system prompt，固定不模板化）
CODE_CONTRACT_SYSTEM = """\
你是 Quant Asst 的策略代码生成器。只输出一个 Python 模块源码\
（无 markdown 围栏、无解释文字），必须满足以下契约：

1. 定义函数 generate_positions(df, params=None)，返回 pandas.Series：
   - 输入 df：DataFrame，列为 date/open/high/low/close/volume/amount/suspended/\
limit_up/limit_down，date 为 datetime64 且按时间升序；
   - 输出：**逐行对应 df 的每一行**的目标仓位（1=满仓多头，0=空仓；仅当假设明确要求\
做空且市场允许时才输出负值）。返回 Series 的索引可以是 df.index 或 df.date，\
引擎按行序对齐，但长度必须等于 len(df)；
   - **禁止对返回值再做 shift(1)**：信号在 t 日收盘后生成、引擎已统一在 t+1 日开盘\
执行，再 shift 会多滞后一天。直接返回「当日收对应的目标仓位」即可。
2. 禁止未来函数：禁止负 shift、禁止 center=True 等未来对齐、禁止引用 df 之外的任何数据。
3. 策略参数集中定义为模块级字典 PARAMS（如 PARAMS = {"fast_window": 5,\
"slow_window": 20}）；params 为 None 或缺少某键时一律回落 PARAMS 的默认取值。\
同一份代码因此可被参数网格寻优（cli.py optimize）逐组合重复调用而无需改动代码。
4. 允许 import：numpy、pandas；禁止 import os、subprocess、socket、requests、urllib、\
http、ctypes、shutil、sys、importlib、pickle 等任何其他模块（静态安检会拒绝）。
5. 禁止 open() 使用绝对路径或包含 ..；禁止 eval/exec/compile/__import__。
6. 模块顶部 docstring 说明策略逻辑与参数含义。
7. 停牌日（suspended=True 行）不需要你处理，回测引擎会禁止成交。

参考骨架（严格照此风格，只允许 numpy/pandas）：
    import pandas as pd

    PARAMS = {"fast_window": 5, "slow_window": 20}

    def generate_positions(df, params=None):
        p = {**PARAMS, **(params or {})}
        close = df["close"].astype(float)
        fast = close.rolling(p["fast_window"]).mean()
        slow = close.rolling(p["slow_window"]).mean()
        return (fast > slow).astype(float)
"""


def _strip_code_fence(text: str) -> str:
    """剥离 LLM 输出的 markdown 代码围栏与首尾空白。"""
    text = text.strip()
    fence = re.match(r"^```(?:python)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text


class HypothesisAgent:
    """自然语言策略假设 Agent（两跳：Spec -> Code）。

    与后续辩论/风控角色的 BaseAgent 不同，本 Agent 的输出是「schema + 代码」双产物，
    故独立实现 run()；结构化校验与重试复用 core.llm.complete_structured（硬约束 2）。
    """

    role: ClassVar[str] = "hypothesis"
    output_schema: ClassVar[type[HypothesisSpec]] = HypothesisSpec

    def __init__(self, settings: Settings, recorder: TrajectoryRecorder) -> None:
        self.settings = settings
        self.recorder = recorder

    # ---- 跳 1：自然语言 -> 结构化假设 ----

    def build_messages(self, state: QuantAsstState) -> list[dict[str, str]]:
        """组装结构化跳消息（system 模板 + 用户原始描述）。"""
        market = state.get("market") or self.settings.default_market.value
        system = render_prompt(
            self.role,
            today=date.today().strftime("%Y-%m-%d"),
            market=market,
            market_label=_MARKET_LABELS.get(market, market),
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": state.get("user_input", "")},
        ]

    def run(self, state: QuantAsstState) -> dict[str, Any]:
        """LangGraph 节点入口：两跳输出，结果写回 State 增量。"""
        market = state.get("market") or self.settings.default_market.value
        self.recorder.log(
            node=self.role, event="invoke",
            payload={"user_input": state.get("user_input", ""), "market": market},
        )

        # ---- 跳 1：结构化假设（complete_structured 内含校验失败重试 1 次）----
        spec = complete_structured(
            self.build_messages(state), self.output_schema, self.settings, context=self.role
        )
        self.recorder.log(node=self.role, event="spec", payload={"spec": spec.model_dump()})

        # ---- 跳 2：生成策略代码（安检失败回灌重试）----
        code = self._generate_code(spec)
        self.recorder.log(
            node=self.role, event="code_generated",
            payload={
                "code_chars": len(code),
                "sha16": hash(code) & 0xFFFF,
                # 留痕完整代码正文：零成交/异常时可回放定位（硬约束 4）
                "code": code,
            },
        )
        return {"hypothesis": spec.model_dump(), "generated_code": code}

    # ---- 跳 2：假设 -> 策略代码 ----

    def _generate_code(self, spec: HypothesisSpec) -> str:
        """按契约生成代码；静态安检不通过时把违规项回灌模型重试。"""
        user_brief = (
            f"策略名称：{spec.strategy_name}\n"
            f"市场：{spec.market}\n"
            f"策略逻辑：{spec.logic_summary}\n"
            f"开仓规则：{spec.entry_rule}\n"
            f"平仓规则：{spec.exit_rule}\n"
            f"参数：{spec.params}\n"
            "请严格按契约生成完整策略代码。"
        )
        messages = [
            {"role": "system", "content": CODE_CONTRACT_SYSTEM},
            {"role": "user", "content": user_brief},
        ]
        last_violations: list[str] = []
        for attempt in range(self.settings.llm_max_retries + 1):
            code = _strip_code_fence(complete(messages, self.settings))
            violations = audit_strategy_code(code)
            if not violations:
                return code
            last_violations = violations
            self.recorder.log(
                node=self.role, event="code_audit_retry",
                payload={"attempt": attempt + 1, "violations": violations},
            )
            # 回灌违规项，要求修正（硬约束 2 的代码版）
            messages.append({"role": "assistant", "content": code})
            messages.append({
                "role": "user",
                "content": (
                    "你的代码未通过静态安检，违规项：\n- "
                    + "\n- ".join(last_violations)
                    + "\n请修正后重新输出完整代码（仍然只输出源码，无围栏）。"
                ),
            })
        raise ValueError(
            "策略代码连续未通过静态安检（重试 "
            f"{self.settings.llm_max_retries} 次后放弃）：{last_violations}"
        )
