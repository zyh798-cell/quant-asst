"""LangGraph 全链路测试：自然语言 -> 假设 -> 代码 -> local 沙箱回测（Step 3 单链路）。

LLM 与数据源全部 mock，沙箱内执行真实引擎。
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from tests.test_hypothesis_agent import CODE_OK, SPEC_JSON


class FakeAdapter:
    """合成日线数据适配器（替代真实网络源）。"""

    def fetch_daily(self, symbol, start: str, end: str) -> pd.DataFrame:
        n = 120
        rng = np.random.default_rng(7)
        prices = 100 + np.cumsum(rng.normal(0.05, 1.0, n))  # 缓慢上行
        return pd.DataFrame({
            "date": pd.bdate_range("2024-01-01", periods=n),
            "open": prices, "high": prices * 1.01, "low": prices * 0.99,
            "close": prices, "volume": 1e6, "amount": 1e7,
            "suspended": False, "limit_up": np.nan, "limit_down": np.nan,
        })


@pytest.fixture()
def mock_llm(monkeypatch) -> None:
    """mock LiteLLM：依次返回 spec JSON 与合规代码。"""
    from tests.test_hypothesis_agent import _response

    responses = [
        _response(json.dumps(SPEC_JSON, ensure_ascii=False)),
        _response(CODE_OK),
    ]
    monkeypatch.setattr("litellm.completion", lambda **kw: responses.pop(0))


@pytest.fixture()
def mock_data_source(monkeypatch) -> None:
    monkeypatch.setattr(
        "data.cache.get_adapter",
        lambda market, crypto_exchange="binance": FakeAdapter(),
    )


def test_graph_end_to_end(test_settings, mock_llm, mock_data_source) -> None:
    """全链路：NL -> spec -> code -> local 沙箱回测 -> State 汇聚。"""
    from core.graph import build_graph

    run_id = "test-graph"
    graph, recorder = build_graph(test_settings, run_id=run_id, sandbox_mode="local")
    try:
        final_state = graph.invoke({
            "run_id": run_id,
            "user_input": "茅台双均线策略，5日线上穿20日线买入",
            "market": "cn_stock",
            "iterations": 0,
        })
    finally:
        recorder.close()

    assert not final_state.get("error")
    assert final_state["hypothesis"]["strategy_name"] == "双均线趋势"
    assert final_state["generated_code"].count("generate_positions") >= 1

    # 回测结果已写入 State 并通过 schema 校验
    br = final_state["backtest_result"]
    assert br["symbol"] == "cn:600519"
    assert br["out_sample_start"]          # 硬约束 5：样本外切分
    assert br["overall"]["n_days"] == 119  # 120 根 K 线 -> 119 天净值

    # 净值曲线已入 State
    assert len(final_state["equity_curve"]["dates"]) == 119


def test_graph_llm_failure_short_circuits(test_settings, mock_data_source, monkeypatch) -> None:
    """LLM 失败（如密钥无效）时：error 写入 State，回测节点被条件边短路。"""
    from core.graph import build_graph

    def boom(**kw):
        raise RuntimeError("authentication error: invalid api key")

    monkeypatch.setattr("litellm.completion", boom)

    run_id = "test-graph-fail"
    graph, recorder = build_graph(test_settings, run_id=run_id, sandbox_mode="local")
    try:
        final_state = graph.invoke({
            "run_id": run_id,
            "user_input": "随便一个策略",
            "market": "cn_stock",
            "iterations": 0,
        })
    finally:
        recorder.close()

    assert "authentication error" in final_state["error"]
    assert "backtest_result" not in final_state  # 短路：回测节点未执行
