"""LLM 调用统一封装（LiteLLM）。

- 模型通过 ``QUANT_ASST_LLM_MODEL`` 环境变量切换（LiteLLM 格式 provider/model）；
- 密钥由 LiteLLM 从进程环境变量直接读取（DEEPSEEK_API_KEY / OPENAI_API_KEY ...）；
- 硬约束 2：结构化输出统一走「JSON 提示 + Pydantic 校验」，失败带错误反馈重试
  ``settings.llm_max_retries`` 次（默认 1 次）。
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from typing import Any, TypeVar

# ---- 离线开关必须在 import litellm 之前生效（关键）----
# LiteLLM 在 ``import`` 阶段就会后台请求 GitHub 上的 model cost map，
# 失败时按 3 次退避重试并打印冗余告警（见 get_model_cost_map.py 的模块级调用）。
# 该判定读取环境变量 ``LITELLM_OFFLINE_MODE``，因此必须在导入前设置，
# 导入后再改常量已经来不及。mock 离线模式下直接使用本地备份，零网络请求。
#: mock 模式真值集合（与 :func:`is_mock_mode` 保持一致）
_MOCK_TRUE_VALUES = {"1", "true", "yes", "on"}

#: mock 模式开关环境变量（``QUANTSENTINEL_LLM_MOCK`` 为改名前的旧名，包改名后已移除）。
MOCK_ENV_VAR = "QUANT_ASST_LLM_MOCK"


def _mock_flag() -> str:
    """读取 mock 开关（大小写不敏感）。"""
    return (os.getenv(MOCK_ENV_VAR, "") or "").strip().lower()


def _enable_offline_mode_if_mock() -> None:
    """mock 模式下于 litellm 导入前开启 LiteLLM 离线开关。"""
    if _mock_flag() in _MOCK_TRUE_VALUES:
        os.environ["LITELLM_OFFLINE_MODE"] = "true"


_enable_offline_mode_if_mock()

import litellm  # noqa: E402 —— 必须在上面离线开关设置之后导入
from pydantic import BaseModel, ValidationError  # noqa: E402

from core.config import Settings  # noqa: E402
from core.schemas import StrictModel  # noqa: E402

# ---- LiteLLM 静默配置 ----
# 关闭 LiteLLM 的调试噪音输出
litellm.suppress_debug_info = True
# 关闭 LiteLLM 自身的请求/消息日志（保留其异常告警，避免屏蔽真实错误）
try:
    litellm.turn_off_message_logging = True
except Exception:  # noqa: BLE001 —— 旧版本无此开关时忽略
    pass
logging.getLogger("LiteLLM").setLevel(logging.ERROR)


def _silence_litellm_cost_map_fetch() -> None:
    """双保险：把 LiteLLM cost map 拉取重试次数常量置 0。

    主路径是导入前设置 ``LITELLM_OFFLINE_MODE=true``（见上）；
    这里再兜底处理「litellm 已被其他模块先行导入」的情形，
    使后续显式触发的 ``get_model_cost_map`` 不再重试远端请求。
    """
    fn = getattr(litellm, "get_model_cost_map", None)
    if fn is None:
        return
    module = sys.modules.get(getattr(fn, "__module__", ""))
    if module is None:
        return
    if hasattr(module, "MODEL_COST_MAP_FETCH_MAX_ATTEMPTS"):
        try:
            module.MODEL_COST_MAP_FETCH_MAX_ATTEMPTS = 0
        except Exception:  # noqa: BLE001 —— 常量可能被冻结
            pass


_silence_litellm_cost_map_fetch()


# ---------------------------------------------------------------------------
# 可观测 usage 累加器（Step L 多模型对比用；纯旁路，不改单模型调用行为）
# ---------------------------------------------------------------------------
#: 按模型名累计的 token 用量（prompt/completion/calls）。仅用于对比报告展示，
#: 不参与任何判定；多模型编排按模型逐个 :func:`reset_usage` 后再 :func:`usage_for` 读取。
_USAGE: dict[str, dict[str, int]] = {}


def _usage_entry(model: str) -> dict[str, int]:
    return _USAGE.setdefault(
        model, {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
    )


def _estimate_mock_tokens(messages: list[dict[str, str]], content: str) -> tuple[int, int]:
    """mock 下无真实 usage 时的**确定性**近似：按字符数估算（同输入必然同值）。

    真实后端走 ``response.usage``（见下）；mock 后端返回的 content 对同一角色是
    固定字符串，故估算值恒定，保证多模型确定性测试「两次运行一致」。
    """
    prompt_chars = sum(len(m.get("content") or "") for m in messages or [])
    prompt = max(1, prompt_chars // 4)
    completion = max(1, len(content or "") // 4)
    return prompt, completion


def _record_usage(
    model: str, response: Any, messages: list[dict[str, str]], content: str
) -> None:
    """把一次补全的 token 用量累加进 :data:`_USAGE`（旁路，异常吞掉不影响主流程）。"""
    try:
        entry = _usage_entry(model)
        entry["calls"] += 1
        usage = getattr(response, "usage", None)
        if usage is not None:
            entry["prompt_tokens"] += int(getattr(usage, "prompt_tokens", 0) or 0)
            entry["completion_tokens"] += int(getattr(usage, "completion_tokens", 0) or 0)
        else:
            prompt, completion = _estimate_mock_tokens(messages, content)
            entry["prompt_tokens"] += prompt
            entry["completion_tokens"] += completion
    except Exception:  # noqa: BLE001 —— usage 采集失败绝不影响结构化输出
        pass


def reset_usage(model: str | None = None) -> None:
    """清空某模型（缺省全部）的 usage 累计；多模型编排按模型粒度重置。"""
    if model is None:
        _USAGE.clear()
    else:
        _USAGE.pop(model, None)


def usage_for(model: str) -> dict[str, int]:
    """返回某模型已累计的 usage（无记录返回全 0 结构，绝不抛错）。"""
    return dict(_USAGE.get(model, {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}))


def is_mock_mode() -> bool:
    """当前是否处于 mock 离线模式（``QUANT_ASST_LLM_MOCK`` 为真值）。"""
    return _mock_flag() in _MOCK_TRUE_VALUES


T = TypeVar("T", bound=StrictModel)


class SchemaViolationError(RuntimeError):
    """结构化输出连续校验失败（重试次数耗尽）。"""


def _extract_json(raw: str) -> str:
    """从模型回复中提取 JSON 正文。

    部分模型即使要求纯 JSON 也会输出 `` ```json ... ``` `` 代码围栏，此处兜底剥离。
    """
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fence:
        return fence.group(1)
    # 兜底：截取首个 { 到最后一个 } 之间的内容
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _json_instruction(schema: type[BaseModel]) -> str:
    """生成 JSON Schema 注入指令（双保险：对不支持 response_format 的模型仍有效）。"""
    return (
        "你必须只输出一个合法 JSON 对象，禁止输出任何其他文本、解释或代码块标记。\n"
        "JSON 必须严格符合以下 JSON Schema：\n"
        + json.dumps(schema.model_json_schema(), ensure_ascii=False)
    )


def complete(
    messages: list[dict[str, str]],
    settings: Settings,
    **overrides: Any,
) -> str:
    """普通文本补全（Reviewer 生成报告等场景）。"""
    backend = get_completion_backend(settings)
    response = backend.completion(
        model=settings.llm_model,
        messages=messages,
        temperature=settings.llm_temperature,
        **overrides,
    )
    content = response.choices[0].message.content or ""
    _record_usage(settings.llm_model, response, messages, content)
    return content


def complete_structured(
    messages: list[dict[str, str]],
    schema: type[T],
    settings: Settings,
    context: str = "",
) -> T:
    """调用 LLM 并强制返回 ``schema`` 实例。

    失败时把 Pydantic 校验错误反馈给模型要求修正，重试 ``settings.llm_max_retries`` 次
    （默认 1 次，硬约束 2）。

    Args:
        messages: 对话消息（首条应为 system prompt）。
        schema: 期望的输出模型类。
        settings: 全局配置。
        context: 日志用上下文标签（角色名）。

    Returns:
        通过校验的 schema 实例。

    Raises:
        SchemaViolationError: 重试耗尽仍无法通过校验。
    """
    augmented = [dict(m) for m in messages]
    instruction = _json_instruction(schema)
    if augmented and augmented[0].get("role") == "system":
        augmented[0] = {**augmented[0], "content": f"{augmented[0]['content']}\n\n{instruction}"}
    else:
        augmented.insert(0, {"role": "system", "content": instruction})

    last_error: ValidationError | ValueError | None = None
    backend = get_completion_backend(settings)
    for attempt in range(settings.llm_max_retries + 1):
        kwargs: dict[str, Any] = {
            "model": settings.llm_model,
            "messages": augmented,
            # 首次用配置温度，重试时降到 0 增强稳定性
            "temperature": settings.llm_temperature if attempt == 0 else 0.0,
        }
        try:
            response = backend.completion(**kwargs, response_format={"type": "json_object"})
        except Exception:
            # 模型不支持 json_object 模式时降级为普通补全（schema 已注入 system）
            response = backend.completion(**kwargs)
        raw = response.choices[0].message.content or ""
        _record_usage(settings.llm_model, response, augmented, raw)
        try:
            return schema.model_validate_json(_extract_json(raw))
        except ValidationError as exc:
            last_error = exc
            # 将校验错误回灌给模型，要求修正后重新输出
            augmented.append({"role": "assistant", "content": raw})
            errors_preview = json.dumps(exc.errors(include_url=False)[:5], ensure_ascii=False)
            augmented.append(
                {
                    "role": "user",
                    "content": (
                        f"上一次输出未通过 JSON Schema 校验，错误摘要：{errors_preview}。"
                        "请严格按 schema 修正，重新输出完整 JSON。"
                    ),
                }
            )
    raise SchemaViolationError(
        f"[{context or schema.__name__}] 结构化输出校验失败（重试 {settings.llm_max_retries} 次后放弃）"
        f"：{last_error}"
    )


# ---------------------------------------------------------------------------
# Mock 离线后端（CI / 单测用，无需真实 API）
# ---------------------------------------------------------------------------

#: 一个完整的 LiteLLM 响应形状（mock 用）
_MockResponse = Any


def _mock_response(content: str) -> _MockResponse:
    """构造与 litellm.completion 返回兼容的最小响应对象。"""
    from types import SimpleNamespace

    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


#: 角色特征词 -> 角色名：每个角色的 prompt **首行**固定包含该标识，据此做确定性映射，
#: 与后文材料内容解耦（材料里出现「风控」等字样不会误判）。
_ROLE_MARKERS: tuple[tuple[str, str], ...] = (
    ("hypothesis", "策略假设分析师"),
    ("bull", "多头分析师"),
    ("bear", "空头分析师"),
    ("risk", "风控核验"),
    ("redteam", "红队审计"),
    ("risk_officer", "风控综合官"),
    ("reviewer", "最终裁决员"),
)

#: 代码生成契约的独有标识（agents/hypothesis.py CODE_CONTRACT_SYSTEM）
_CODE_MARKER = "策略代码生成器"


class MockCompletionBackend:
    """脚本化 LLM 后端：按 **prompt 特征词**返回确定性 JSON，供离线测试与 CI。

    触发：环境变量 ``QUANT_ASST_LLM_MOCK`` 取真值（1/true/yes/on）。
    仅用于辩论模块等离线场景；真实密钥存在时默认仍走 LiteLLM，不改变既有链路行为。

    用法::

        backend = get_completion_backend(settings)
        response = backend.completion(model=..., messages=[...], ...)

    角色判定：拼接所有 system 文本后按 :data:`_ROLE_MARKERS` 首次匹配；
    未匹配但含代码生成契约关键词时判为 code 跳，否则 unknown。
    """

    def __init__(self) -> None:
        self.call_count = 0
        self.roles_seen: list[str] = []

    @classmethod
    def infer_role(cls, messages: list[dict[str, str]]) -> str:
        """从消息中推断目标角色（只看 system 文本前若干字符的首行声明）。"""
        for msg in messages:
            if msg.get("role") != "system":
                continue
            text = (msg.get("content") or "").strip()
            # 只取前 60 字符：角色声明固定在 prompt 首行，避免后文材料字样干扰
            head = text[:60]
            for role, marker in _ROLE_MARKERS:
                if marker in head:
                    return role
            if _CODE_MARKER in head:
                return "code"
        return "unknown"

    # ---- 脚本化语料：每个角色一份确定性 payload ----

    def _payload_for(self, role: str, messages: list[dict[str, str]]) -> dict:
        """按角色返回 mock 输出（值均为占位但满足 schema 约束）。"""
        symbol = _extract_symbol(messages)
        if role == "hypothesis":
            return _mock_hypothesis_payload(symbol)
        if role == "bull":
            return _mock_bull_payload(symbol)
        if role == "bear":
            return _mock_bear_payload(symbol)
        if role == "risk":
            return _mock_risk_payload(messages)
        if role == "redteam":
            return _mock_redteam_payload(messages)
        if role == "risk_officer":
            return _mock_risk_officer_payload(messages)
        if role == "reviewer":
            return _mock_verdict_payload(messages)
        # code 跳（策略代码生成）与普通补全：返回合规模板
        if role == "code":
            return {
                "__raw__":
                    "import pandas as pd\n\n"
                    "def generate_positions(df):\n"
                    "    close = df['close'].astype(float)\n"
                    "    fast = close.rolling(5).mean()\n"
                    "    slow = close.rolling(20).mean()\n"
                    "    return (fast > slow).astype(float)\n"
            }
        return {}

    def completion(self, **kwargs: Any) -> _MockResponse:
        """兼容 ``litellm.completion`` 的最小签名。"""
        messages = kwargs.get("messages") or []
        role = self.infer_role(messages)
        self.roles_seen.append(role)
        self.call_count += 1

        payload = self._payload_for(role, messages)
        # code 跳：complete() 需要原始文本而非 JSON 包裹
        if isinstance(payload, dict) and "__raw__" in payload:
            return _mock_response(payload["__raw__"])
        return _mock_response(json.dumps(payload, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Mock 语料构造（确定性、schema 合法）
# ---------------------------------------------------------------------------
_SYMBOL_RE = re.compile(r"(cn|us|hk|futures|crypto):([A-Za-z0-9/\.]+)")


def _extract_symbol(messages: list[dict[str, str]]) -> str:
    """从消息文本中解析标的（缺省回退到贵州茅台）。"""
    for msg in messages:
        found = _SYMBOL_RE.search(msg.get("content", ""))
        if found:
            return f"{found.group(1)}:{found.group(2)}"
    return "cn:600519"


def _mock_hypothesis_payload(symbol: str) -> dict:
    return {
        "strategy_name": "双均线趋势（mock）",
        "market": symbol.split(":", 1)[0],
        "symbols": [symbol],
        "period_start": "2024-11-17",
        "period_end": "2026-11-17",
        "logic_summary": "MA5 上穿 MA20 满仓，下穿清仓",
        "entry_rule": "MA5 > MA20 时满仓",
        "exit_rule": "MA5 < MA20 时清仓",
        "params": {"short_window": 5, "long_window": 20},
        "risk_notes": "震荡市反复止损",
        "assumptions": ["标的为默认假设"],
    }


def _mock_bull_payload(symbol: str) -> dict:
    return {
        "stance": f"看多 {symbol}：趋势跟随策略在明确上升趋势中可捕捉主要波段。",
        "points": [
            {
                "claim": "均线多头排列阶段策略满仓，吃到主升浪",
                "evidence": "backtest_metric: overall.total_return 为正且 out_sample 未显著劣化",
                "evidence_type": "backtest_metric",
            },
            {
                "claim": "标的中长期景气度支撑趋势延续",
                "evidence": "public_data: 行业景气指数与营收增速处于上行区间",
                "evidence_type": "public_data",
            },
        ],
        "assumptions": ["市场存在可持续的中期趋势", "流动性正常、无系统性冲击"],
        "scenario_gain_pct": 25.0,
        "strategy_profit_source": "趋势跟踪：让利润奔跑、截断亏损",
    }


def _mock_bear_payload(symbol: str) -> dict:
    return {
        "stance": f"看空 {symbol}：双均线在震荡市反复假突破，成本侵蚀收益。",
        "points": [
            {
                "claim": "震荡行情频繁交叉导致高买低卖",
                "evidence": "backtest_metric: win_rate 偏低且 total_cost 相对净值占比高",
                "evidence_type": "backtest_metric",
            },
            {
                "claim": "参数固定缺乏自适应，样本外可能失效",
                "evidence": "logic: 固定 5/20 窗口对波动率变化不敏感，存在过拟合风险",
                "evidence_type": "logic",
            },
        ],
        "failure_scenarios": ["横盘震荡 3 个月以上", "突发利空跳空跌破均线"],
        "scenario_drawdown_pct": 30.0,
        "historical_failure_cases": ["2018 年 A 股震荡市同类均线策略普遍负收益"],
    }


def _mock_risk_payload(messages: list[dict[str, str]]) -> dict:
    """风控报告：round_no 从待校验材料中解析，缺省第 1 轮。"""
    text = "\n".join(m.get("content", "") for m in messages)
    round_no = 1
    found = re.search(r"第\s*(\d)\s*轮", text)
    if found:
        round_no = int(found.group(1))
    return {
        "stance": "neutral",
        "round_no": round_no,
        "data_validity": "样本量约 484 个交易日，满足统计需要；前复权口径已消除除权跳空影响",
        "findings": [
            {
                "target_side": "both",
                "issue": "双方均引用回测指标但未区分样本内/样本外，存在过拟合解读风险",
                "severity": "medium",
                "falsifiable": True,
            },
            {
                "target_side": "bear",
                "issue": "「必然反复假突破」缺乏量化证据，属主观猜想",
                "severity": "low",
                "falsifiable": False,
            },
        ],
        "kept_bull_points": [0, 1],
        "kept_bear_points": [0],
        "recommendation": "保留有回测指标支撑的论点，剔除不可证伪的主观判断后再裁决",
    }


def _mock_redteam_payload(messages: list[dict[str, str]]) -> dict:
    """红队审计意见书（AuditReport 形状）：默认 medium 风险，含一条 overfitting 发现。"""
    symbol = _extract_symbol(messages)
    return {
        "symbol": symbol,
        "market": symbol.split(":", 1)[0],
        "strategy_name": "双均线趋势（mock 审计）",
        "audit_run_id": "audit-mock",
        "source_run_id": "debate-mock",
        "overall_risk_level": "medium",
        "risk_grade_label": "中",
        "findings": [
            {
                "category": "overfitting",
                "title": "固定 5/20 参数对波动率不敏感，样本外劣化风险",
                "description": "样本内表现依赖固定窗口，未做波动率自适应，存在过拟合迹象",
                "severity": "medium",
                "evidence": "backtest_metric: in_sample 与 out_sample total_return 差距需关注",
                "recommendation": "加入 ATR 自适应过滤与样本外滚动验证",
            },
        ],
        "summary": "策略逻辑基本成立，主要风险为参数过拟合；未发现致命缺陷。",
        "tradability": "allowed",
    }


def _mock_risk_officer_payload(messages: list[dict[str, str]]) -> dict:
    """风控综合官草稿（FinalAnalysisDraft 形状）：medium 风险，给出交易建议。"""
    symbol = _extract_symbol(messages)
    return {
        "symbol": symbol,
        "market": symbol.split(":", 1)[0],
        "strategy_name": "双均线趋势（mock）",
        "debate_run_id": "debate-mock",
        "audit_run_id": "audit-mock",
        "credibility_score": 58,
        "overall_risk_level": "medium",
        "executive_summary": "辩论共识为趋势市有效，审计提示参数过拟合风险；综合可信度中等。",
        "key_findings": [
            "固定 5/20 窗口在样本外可能劣化，需波动率自适应过滤",
        ],
        "recommendations": [
            "加入 ATR(14) 波动率过滤，仅在波动充足时交易",
            "做样本外滚动验证以确认参数稳健性",
        ],
        "trade_advisory": (
            f"{symbol} 双均线（修订版）：MA5>MA20 且 ATR(14)>MA(ATR(14),20) 时满仓，"
            "死叉或波动不足时清仓。"
        ),
    }


def _mock_verdict_payload(messages: list[dict[str, str]]) -> dict:
    symbol = _extract_symbol(messages)
    return {
        "credibility_score": 62,
        "consensus": ["双均线在趋势市有效", "需警惕震荡市反复止损"],
        "disagreements": ["收益来源是否可持续", "固定参数是否过拟合"],
        "decision": "revise",
        "rationale": "策略逻辑成立但固定参数易过拟合，采纳风控意见加入波动率自适应过滤。",
        "revision": {
            "revised_strategy_text": (
                f"{symbol} 双均线策略（修订版）：以 MA5 上穿 MA20 为金叉买入信号，"
                "死叉卖出；增加过滤条件——仅在 ATR(14) 高于其 20 日均值（波动充足）时交易，"
                "并在持仓期间加入 MA20 斜率为正的趋势确认，减少震荡市假信号。"
            ),
            "entry_rule": "MA5 > MA20 且 ATR(14) > MA(ATR(14),20) 且 MA20 斜率为正",
            "exit_rule": "MA5 < MA20 或 ATR(14) 回落至其 20 日均值下方",
            "params": {"short_window": 5, "long_window": 20, "atr_window": 14, "atr_ma_window": 20},
            "expected_effect": "降低震荡市交易频次与成本，代价是可能错过部分早期趋势",
        },
    }


def get_completion_backend(settings: Settings | None = None):
    """返回 LLM 补全后端：mock 模式（环境变量开启）或真实 LiteLLM。

    mock 判据：``QUANT_ASST_LLM_MOCK`` 为真值（1/true/yes/on，大小写不敏感）。
    关闭时返回一个转发到 ``litellm.completion`` 的轻量适配器，保持调用侧代码不变。

    mock 模式同时设置 ``LITELLM_OFFLINE_MODE=true``，禁止 LiteLLM 拉取任何远端
    目录（模型价格表 / tokenizer / catalog），确保完全离线、无网络重试告警。
    """
    if _mock_flag() in _MOCK_TRUE_VALUES:
        # 强制开启（覆盖可能的外部注入），确保 LiteLLM 完全离线
        os.environ["LITELLM_OFFLINE_MODE"] = "true"
        return MockCompletionBackend()

    class _LiteLLMBackend:
        def completion(self, **kwargs: Any) -> _MockResponse:
            return litellm.completion(**kwargs)

        @property
        def call_count(self) -> int:
            return 0

    return _LiteLLMBackend()
