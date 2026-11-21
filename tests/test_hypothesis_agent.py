"""HypothesisAgent 测试：mock LLM，验证结构化校验重试与代码安检重试（硬约束 2）。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agents.hypothesis import HypothesisAgent, _strip_code_fence
from core.trajectory import TrajectoryRecorder

SPEC_JSON = {
    "strategy_name": "双均线趋势",
    "market": "cn_stock",
    "symbols": ["cn:600519"],
    "period_start": "2024-01-01",
    "period_end": "2024-12-31",
    "logic_summary": "短均线上穿长均线满仓，下穿清仓",
    "entry_rule": "MA5 > MA20 时满仓",
    "exit_rule": "MA5 < MA20 时清仓",
    "params": {"short_window": 5, "long_window": 20},
    "risk_notes": "震荡市反复止损",
    "assumptions": ["标的为默认假设"],
}

CODE_OK = '''\
import pandas as pd

def generate_positions(df):
    """双均线：MA5 > MA20 满仓。"""
    close = df.set_index("date")["close"]
    return (close.rolling(5).mean() > close.rolling(20).mean()).astype(float)
'''

CODE_BAD = "import os\nos.system('echo hacked')\n"


def _response(content: str) -> SimpleNamespace:
    """构造 LiteLLM 响应形状的 mock 对象。"""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.fixture()
def agent(test_settings) -> HypothesisAgent:
    recorder = TrajectoryRecorder("test-agent", test_settings.trajectory_dir)
    try:
        yield HypothesisAgent(test_settings, recorder)
    finally:
        recorder.close()


def _state() -> dict:
    return {"user_input": "茅台双均线策略", "market": "cn_stock", "run_id": "test-agent", "iterations": 0}


def test_strip_code_fence() -> None:
    """代码围栏剥离。"""
    fenced = "```python\nx = 1\n```"
    assert _strip_code_fence(fenced) == "x = 1"
    assert _strip_code_fence("y = 2") == "y = 2"


def test_run_produces_spec_and_code(agent: HypothesisAgent, monkeypatch) -> None:
    """两跳输出：spec + 合规代码。"""
    responses = [_response(json.dumps(SPEC_JSON, ensure_ascii=False)), _response(CODE_OK)]
    calls = []
    monkeypatch.setattr(
        "litellm.completion",
        lambda **kw: (calls.append(kw), responses.pop(0))[1],
    )
    out = agent.run(_state())

    assert out["hypothesis"]["strategy_name"] == "双均线趋势"
    assert "generate_positions" in out["generated_code"]
    assert len(calls) == 2  # spec 跳 + code 跳各一次
    # 第一次调用带 response_format（JSON 模式）
    assert calls[0].get("response_format") == {"type": "json_object"}


def test_schema_retry_on_bad_json(agent: HypothesisAgent, monkeypatch) -> None:
    """spec 跳：第一次 JSON 不合法 -> 错误回灌 -> 第二次成功（硬约束 2）。"""
    bad = json.dumps({"strategy_name": "缺字段的坏 JSON"}, ensure_ascii=False)
    responses = [_response(bad), _response(json.dumps(SPEC_JSON, ensure_ascii=False)), _response(CODE_OK)]
    calls = []
    monkeypatch.setattr(
        "litellm.completion",
        lambda **kw: (calls.append(kw), responses.pop(0))[1],
    )
    out = agent.run(_state())
    assert out["hypothesis"]["market"] == "cn_stock"
    # 重试消息里包含校验错误反馈
    retry_msgs = [m for m in calls[1]["messages"] if "未通过 JSON Schema 校验" in m["content"]]
    assert retry_msgs


def test_code_audit_retry(agent: HypothesisAgent, monkeypatch) -> None:
    """code 跳：第一次代码 import os 被安检拦截 -> 回灌违规 -> 第二次合规。"""
    responses = [
        _response(json.dumps(SPEC_JSON, ensure_ascii=False)),
        _response(CODE_BAD),
        _response(CODE_OK),
    ]
    monkeypatch.setattr("litellm.completion", lambda **kw: responses.pop(0))
    out = agent.run(_state())
    assert "import os" not in out["generated_code"]
    assert "generate_positions" in out["generated_code"]


def test_code_audit_exhausted(agent: HypothesisAgent, monkeypatch) -> None:
    """安检重试耗尽（默认 1 次）后明确报错。"""
    responses = [
        _response(json.dumps(SPEC_JSON, ensure_ascii=False)),
        _response(CODE_BAD),
        _response(CODE_BAD),  # 重试仍违规
    ]
    monkeypatch.setattr("litellm.completion", lambda **kw: responses.pop(0))
    with pytest.raises(ValueError, match="静态安检"):
        agent.run(_state())
