"""绩效指标计算测试：已知序列的精确数值验证。"""

from __future__ import annotations

import pandas as pd

from backtest.metrics import annual_return, compute_metrics, max_drawdown, sharpe, total_return, win_rate


def _nav(values: list[float], start: str = "2024-01-01") -> pd.Series:
    """构造日频净值序列。"""
    idx = pd.bdate_range(start, periods=len(values))
    return pd.Series(values, index=idx, dtype=float)


def test_total_return() -> None:
    assert total_return(_nav([100, 110, 99])) == pytest_approx(-0.01)


def test_max_drawdown_known_series() -> None:
    """100 -> 120 -> 90：最大回撤 = 90/120 - 1 = -25%。"""
    assert max_drawdown(_nav([100, 120, 90])) == pytest_approx(-0.25)


def test_annual_return_one_year() -> None:
    """一年翻倍 -> 年化约 100%（365.25/366 闰年误差在 0.3% 内）。"""
    nav = pd.Series(
        [100.0, 200.0],
        index=pd.DatetimeIndex(["2024-01-01", "2025-01-01"]),
    )
    assert annual_return(nav) == pytest_approx(1.0, tol=0.01)


def test_sharpe_constant_series_is_none() -> None:
    """零波动序列夏普不可计算（返回 None）。"""
    assert sharpe(_nav([100, 100, 100, 100])) is None


def test_win_rate() -> None:
    assert win_rate([50.0, -20.0, 30.0]) == pytest_approx(2 / 3)
    assert win_rate([]) is None


def test_compute_metrics_shape() -> None:
    """compute_metrics 输出与 BacktestMetrics 字段对齐。"""
    m = compute_metrics(_nav([100, 101, 102, 101.5]), [10.0, -5.0])
    expected_keys = {"total_return", "annual_return", "max_drawdown", "sharpe", "win_rate", "n_trades", "n_days"}
    assert expected_keys == set(m.keys())
    assert m["n_trades"] == 2
    assert m["n_days"] == 4


def test_compute_metrics_explicit_n_trades() -> None:
    """显式 n_trades 覆盖默认值：成交笔数（买+卖）与平仓笔数解耦。

    买入后持有到区间结束的策略只有 1 笔平仓的 0 笔，但成交笔数应为 1。
    """
    m = compute_metrics(_nav([100, 110, 120, 130]), [10.0], n_trades=2)
    assert m["n_trades"] == 2          # 显式传入的总成交笔数
    assert m["win_rate"] == 1.0        # 胜率仍按平仓笔样本计算


def pytest_approx(expected: float, tol: float = 1e-9):
    """pytest.approx 的简写别名（保持测试可读）。"""
    import pytest

    return pytest.approx(expected, abs=tol)
