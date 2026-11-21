"""Agent 基类 —— 六个角色的公共骨架。

职责（对应硬约束）：
1. 从 Prompt 注册表加载本角色 system prompt（core/prompts/registry.py）；
2. 统一调用 LLM 并强制结构化输出 + Pydantic 校验 + 失败重试 1 次（硬约束 2）；
3. 每次调用前后写入 trajectory（硬约束 4）；
4. 硬约束 1 的防线：子类组装消息时只允许注入「工具返回的数据」，
   禁止把自由生成的财务数字当作输入 —— 数字类论据一律引用 BacktestResult 等工具产物。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Generic, TypeVar

from core.config import Settings
from core.llm import complete_structured
from core.prompts.registry import render_prompt
from core.schemas import StrictModel
from core.state import QuantSentinelState
from core.trajectory import TrajectoryRecorder

S = TypeVar("S", bound=StrictModel)


class BaseAgent(ABC, Generic[S]):
    """六角色 Agent 基类。子类需声明 role / output_schema / state_key 并实现 build_messages。"""

    role: ClassVar[str]                          # 角色名，对应 prompts/templates/<role>.md
    output_schema: ClassVar[type[StrictModel]]   # 本角色输出的 Pydantic schema
    state_key: ClassVar[str]                     # 结果写回 State 的字段名

    def __init__(self, settings: Settings, recorder: TrajectoryRecorder) -> None:
        self.settings = settings
        self.recorder = recorder

    def run(self, state: QuantSentinelState) -> dict[str, Any]:
        """LangGraph 节点入口：组装消息 -> 结构化输出 -> 落盘 -> 返回 State 增量。

        Args:
            state: 当前全局状态。

        Returns:
            形如 ``{self.state_key: <dict>, **self.merge_keys()}`` 的增量字典。
            默认只写 ``state_key``（值为 schema 的 model_dump）；子类可覆写
            :meth:`merge_keys` 额外写入轮次计数、累积列表等同节点状态。
        """
        self.recorder.log(
            node=self.role,
            event="invoke",
            payload={"user_input": state.get("user_input", "")},
        )
        messages = self.build_messages(state)
        parsed = complete_structured(
            messages, self.output_schema, self.settings, context=self.role
        )
        self.recorder.log(
            node=self.role,
            event="output",
            payload={"result": parsed.model_dump()},
        )
        return {self.state_key: parsed.model_dump(), **self.merge_keys(state)}

    def merge_keys(self, state: QuantSentinelState) -> dict[str, Any]:
        """同节点额外写入的状态字段（缺省无）。"""
        return {}

    @abstractmethod
    def build_messages(self, state: QuantSentinelState) -> list[dict[str, str]]:
        """由子类组装消息：system prompt（模板渲染）+ 上下文（仅工具返回的数据）。"""

    def render_system(self, **ctx: Any) -> str:
        """渲染本角色 system prompt 模板（$var 占位符）。"""
        return render_prompt(self.role, **ctx)
