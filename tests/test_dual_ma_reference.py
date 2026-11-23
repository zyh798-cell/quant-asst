"""硬编码双均线（5/20）参考策略回归测试。

对应 2026-11「零成交」事故：验证 ``examples/dual_ma.py`` 模板 + 回测引擎
在趋势行情下必然产生成交与非零收益。全部使用确定性合成数据，不依赖网络与 LLM。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest.engine import run_event_backtest
from backtest.market_rules import CN_STOCK_RULES
from examples.dual_ma import LONG_WINDOW, SHORT_WINDOW, generate_positions

INITIAL_CAPITAL = 1_000_000.0
N = 160


def make_ohlcv(close: np.ndarray) -> pd.DataFrame:
    arr = np.asarray(close, dtype=float)
    return pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=len(arr)),
        "open": arr,
        "high": arr * 1.01,
        "low": arr * 0.99,
        "close": arr,
        "volume": 1e6,
        "amount": 1e7,
        "suspended": False,
        "limit_up": np.nan,
        "limit_down": np.nan,
    })


def test_template_parameters() -> None:
    """模板参数与假设中的 5/20 双均线一致。"""
    assert SHORT_WINDOW == 5
    assert LONG_WINDOW == 20


def test_dual_ma_rise_then_fall_has_trades_and_nonzero_return() -> None:
    """先涨后跌：至少一次金叉买入 + 一次死叉卖出，总收益非零。"""
    half = N // 2
    prices = np.concatenate([
        np.linspace(100.0, 160.0, half),
        np.linspace(160.0, 90.0, N - half),
    ])
    result = run_event_backtest(
        make_ohlcv(prices), generate_positions, CN_STOCK_RULES,
        initial_capital=INITIAL_CAPITAL,
    )

    buys = [t for t in result["trades"] if t["side"] == "buy"]
    sells = [t for t in result["trades"] if t["side"] == "sell"]
    assert result["signal_nonzero_days"] > 0
    assert len(buys) >= 1, "应出现金叉买入"
    assert len(sells) >= 1, "应出现死叉卖出"
    assert result["metrics"]["overall"]["n_trades"] >= 2
    assert result["metrics"]["overall"]["total_return"] != 0.0


def test_dual_ma_uptrend_is_profitable() -> None:
    """单边上涨：金叉后持有，总收益应为正。"""
    prices = np.linspace(100.0, 220.0, N)
    result = run_event_backtest(
        make_ohlcv(prices), generate_positions, CN_STOCK_RULES,
        initial_capital=INITIAL_CAPITAL,
    )
    assert result["metrics"]["overall"]["n_trades"] >= 1
    assert result["metrics"]["overall"]["total_return"] > 0.0


def test_dual_ma_output_is_row_aligned() -> None:
    """模板输出逐行对应 df（长度一致、非全零），满足引擎契约。"""
    prices = np.linspace(100.0, 220.0, N)
    df = make_ohlcv(prices)
    pos = generate_positions(df)
    assert isinstance(pos, pd.Series)
    assert len(pos) == len(df)
    assert (pos != 0).any()


@pytest.mark.skipif(
    not list((Path(__file__).resolve().parents[1] / "var" / "market").rglob("*.parquet")),
    reason="本地无真实行情缓存（var/market 为空）",
)
def test_dual_ma_on_cached_real_data() -> None:
    """真实缓存数据回归：双均线必须有成交、总收益非零（零成交事故的核心校验）。"""
    cache = sorted((Path(__file__).resolve().parents[1] / "var" / "market").rglob("*.parquet"))
    # var/market 会随本地取数累积任意区间的缓存；本用例验证的是「趋势行情下必成交」，
    # 窗口过短（不足双均线预热 + 一轮交叉）时零成交属正常现象，不应判为回归失败。
    min_bars = SHORT_WINDOW + LONG_WINDOW * 2
    for path in cache:
        df = pd.read_parquet(path)
        if len(df) < min_bars:
            continue
        result = run_event_backtest(
            df, generate_positions, CN_STOCK_RULES, initial_capital=INITIAL_CAPITAL,
        )
        assert result["metrics"]["overall"]["n_trades"] >= 1, f"{path.name} 应产生成交"
        assert result["metrics"]["overall"]["total_return"] != 0.0, f"{path.name} 总收益不应为 0"
