"""多空辩论模块测试：mock 离线后端、全链路、错误短路、报告渲染。

全部使用 ``QUANT_ASST_LLM_MOCK=1``，不发起任何网络请求。
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch) -> None:
    monkeypatch.setenv("QUANT_ASST_LLM_MOCK", "1")


@pytest.fixture()
def base_input() -> dict:
    return {
        "run_id": "test-debate",
        "user_input": "宁德时代双均线策略，5日线上穿20日线买入，死叉卖出，测近两年",
        "market": "cn_stock",
        "symbol": "cn:300750",
        "iterations": 0,
        "debate_rounds": 2,
        "hypothesis": {"period_start": "2024-11-17", "period_end": "2026-11-17"},
    }


# ---------------------------------------------------------------------------
# Mock 后端
# ---------------------------------------------------------------------------

def test_mock_backend_role_inference() -> None:
    """按 prompt 首行特征词识别角色。"""
    from core.llm import MockCompletionBackend

    def msgs(marker: str) -> list[dict[str, str]]:
        return [{"role": "system", "content": f"你是 QuantSentinel 的{marker}。"}]

    assert MockCompletionBackend.infer_role(msgs("多头分析师")) == "bull"
    assert MockCompletionBackend.infer_role(msgs("空头分析师")) == "bear"
    assert MockCompletionBackend.infer_role(msgs("风控核验员")) == "risk"
    assert MockCompletionBackend.infer_role(msgs("最终裁决员")) == "reviewer"


def test_mock_backend_payload_validates() -> None:
    """mock 输出能通过对应 schema 校验（说明占位语料与 schema 未脱节）。"""
    from core.llm import get_completion_backend
    from core.schemas import BearArgument, BullArgument, DebateVerdict, RiskCheckReport

    backend = get_completion_backend()
    cases = [
        ("你是 QuantSentinel 的多头分析师。", BullArgument),
        ("你是 QuantSentinel 的空头分析师。", BearArgument),
        ("你是 QuantSentinel 的风控核验员。", RiskCheckReport),
        ("你是 QuantSentinel 的最终裁决员。", DebateVerdict),
    ]
    for text, schema in cases:
        resp = backend.completion(
            model="mock", messages=[{"role": "system", "content": text}], temperature=0.0
        )
        payload = json.loads(resp.choices[0].message.content)
        schema.model_validate(payload)  # 不通过即抛异常


# ---------------------------------------------------------------------------
# 全链路
# ---------------------------------------------------------------------------

def test_debate_graph_full_run(test_settings, base_input) -> None:
    """两轮辩论全链路：逐轮原文累积、风控报告、裁决与修订策略齐备。"""
    from core.debate_graph import build_debate_graph

    graph, recorder = build_debate_graph(test_settings, run_id="test-debate", max_rounds=2)
    try:
        state = graph.invoke(dict(base_input))
    finally:
        recorder.close()

    assert not state.get("error"), state.get("error")
    outcome = state["debate_outcome"]
    assert outcome["rounds"] == 2
    assert len(outcome["round_transcripts"]) == 2
    assert [t["round"] for t in outcome["round_transcripts"]] == [1, 2]
    assert len(outcome["risk_checks"]) == 2

    verdict = outcome["verdict"]
    assert 0 <= verdict["credibility_score"] <= 100
    assert verdict["decision"] in {"adopt", "reject", "revise"}
    assert outcome["revised_strategy_text"]


def test_debate_single_round(test_settings, base_input) -> None:
    """单轮：只跑一次 bull/bear/risk，仍产出完整裁决。"""
    from core.debate_graph import build_debate_graph

    base_input["debate_rounds"] = 1
    graph, recorder = build_debate_graph(test_settings, run_id="test-debate-1", max_rounds=1)
    try:
        state = graph.invoke(dict(base_input))
    finally:
        recorder.close()

    outcome = state["debate_outcome"]
    assert outcome["rounds"] == 1
    assert len(outcome["round_transcripts"]) == 1
    assert outcome["bull_final"]["stance"]
    assert outcome["bear_final"]["stance"]


def test_revised_strategy_has_symbol_prefix() -> None:
    """修订策略必须带标的标识，便于直接作为 cli.py run 输入。"""
    from core.debate_graph import _ensure_symbol_prefix

    text = _ensure_symbol_prefix("双均线策略修订版", "cn:300750")
    assert text.startswith("cn:300750")
    # 已包含标的时不重复添加
    again = _ensure_symbol_prefix(text, "cn:300750")
    assert again.count("cn:300750") == 1


# ---------------------------------------------------------------------------
# 报告渲染
# ---------------------------------------------------------------------------

def test_markdown_report_is_plain_and_complete(test_settings, base_input) -> None:
    """报告含各必要小节，且不含 emoji / 装饰符号。"""
    from core.debate_graph import build_debate_graph
    from report.markdown import render_debate_markdown

    graph, recorder = build_debate_graph(test_settings, run_id="test-md", max_rounds=1)
    try:
        state = graph.invoke({**dict(base_input), "debate_rounds": 1})
    finally:
        recorder.close()

    md = render_debate_markdown(state["debate_outcome"])
    assert "## 逐轮辩论原文" in md
    assert "第 1 轮" in md
    assert "## 裁决结论" in md
    assert "## 策略修订建议" in md
    assert "可信度打分" in md

    # 禁用 emoji 与常见装饰符号
    banned = ["\U0001F525", "\u2705", "\u26A0", "\u2714", "\u2718", "✔", "⚠"]
    assert not any(ch in md for ch in banned), f"报告中出现禁用符号：{banned}"


def test_report_written_to_output_dir(test_settings, base_input, tmp_path) -> None:
    """write_debate_report 自动创建目录并落盘。"""
    from core.debate_graph import build_debate_graph
    from report.markdown import write_debate_report

    graph, recorder = build_debate_graph(test_settings, run_id="test-write", max_rounds=1)
    try:
        state = graph.invoke({**dict(base_input), "debate_rounds": 1})
    finally:
        recorder.close()

    out = tmp_path / "nested" / "output"
    path = write_debate_report(state["debate_outcome"], out)
    assert path.endswith("test-write.md")
    with open(path, encoding="utf-8") as fh:
        content = fh.read()
    assert "# 多空辩论报告" in content
