"""复权口径回归：除权跳空不得制造假信号。

背景：A 股分红除权会在未复权价格上留下向下跳空。双均线这类只看价格序列的
策略会把该跳空读成趋势反转（假死叉），从而在除权日错误清仓。前复权（qfq）
通过把除权前的价格按因子下调，使收益率序列保持连续，从数据源头消除该假信号。

本文件全部使用合成序列，不联网、不依赖本地缓存。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.engine import run_event_backtest
from backtest.market_rules import CN_STOCK_RULES


def _frame(close: list[float]) -> pd.DataFrame:
    """把收盘价序列包装成标准 OHLCV（开高低收相同，无涨跌停约束）。"""
    n = len(close)
    arr = np.asarray(close, dtype=float)
    return pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=n),
        "open": arr, "high": arr, "low": arr, "close": arr,
        "volume": np.full(n, 1_000_000.0),
        "amount": np.full(n, 1.0e8),
        "suspended": np.zeros(n, dtype=bool),
        "limit_up": np.full(n, np.nan),
        "limit_down": np.full(n, np.nan),
    })


def _dual_ma(df: pd.DataFrame, fast: int = 5, slow: int = 20) -> pd.Series:
    close = df["close"].astype(float)
    short = close.rolling(fast).mean()
    long = close.rolling(slow).mean()
    return (short > long).astype(float)


def _with_ex_dividend_split(path: list[float], at: int, factor: float) -> list[float]:
    """在未复权序列上模拟除权：at 日之前的价格放大 factor 倍，形成向下跳空。"""
    out = list(path)
    for i in range(at):
        out[i] *= factor
    return out


def test_forward_adjusted_series_keeps_trend_signal() -> None:
    """qfq（连续）序列全程多头，不因除权产生死叉。"""
    steady = [100.0 + 0.5 * i for i in range(60)]
    pos = _dual_ma(_frame(steady))

    assert (pos.loc[19:] == 1.0).all()   # 长均线暖机后恒为多头


def test_unadjusted_ex_dividend_gap_creates_false_signal() -> None:
    """对照：同一趋势的未复权序列会因除权跳空触发假死叉。"""
    steady = [100.0 + 0.5 * i for i in range(60)]
    raw = _with_ex_dividend_split(steady, at=30, factor=2.0)

    pos_raw = _dual_ma(_frame(raw))
    pos_qfq = _dual_ma(_frame(steady))

    assert (pos_qfq.loc[19:] == 1.0).all()
    assert (pos_raw == 0.0).any(), "未复权序列应出现假空仓信号"


def test_engine_records_false_sell_on_ex_dividend_gap() -> None:
    """端到端：未复权序列在除权日附近产生卖出成交，qfq 序列不产生。"""
    steady = [100.0 + 0.5 * i for i in range(60)]
    raw = _with_ex_dividend_split(steady, at=30, factor=2.0)

    def pos_fn(df: pd.DataFrame) -> pd.Series:
        return _dual_ma(df)

    res_qfq = run_event_backtest(_frame(list(steady)), pos_fn, CN_STOCK_RULES,
                                 initial_capital=1_000_000.0)
    res_raw = run_event_backtest(_frame(raw), pos_fn, CN_STOCK_RULES,
                                 initial_capital=1_000_000.0)

    sells_qfq = [t for t in res_qfq["trades"] if t["side"] == "sell"]
    sells_raw = [t for t in res_raw["trades"] if t["side"] == "sell"]

    assert not sells_qfq, "qfq 序列不应因除权产生卖出"
    assert sells_raw, "对照口径应产生卖出（否则本用例失去对照意义）"


def test_limit_ratio_stable_across_adjustments() -> None:
    """涨跌停边界按百分比推算：复权口径切换后，相对前收的比例保持不变。

    这是「qfq 改变绝对价、但不改变涨跌幅口径」的直接验证，也是引擎
    绝对价比较仍然成立的依据。
    """
    tick = 0.01
    pct = 0.10

    steady = [100.0 + 0.5 * i for i in range(60)]
    raw = _with_ex_dividend_split(steady, at=30, factor=2.0)

    def limits(close: list[float]) -> tuple[np.ndarray, np.ndarray]:
        prev = pd.Series(close).shift(1).to_numpy()
        up = np.ceil(prev * (1 + pct) / tick) * tick
        down = np.floor(prev * (1 - pct) / tick) * tick
        return up, down

    up_q, down_q = limits(steady)
    up_r, down_r = limits(raw)

    ratio_up_q = up_q[1:] / np.asarray(steady[:-1])
    ratio_up_r = up_r[1:] / np.asarray(raw[:-1])
    # 比例口径在两种复权下都贴近理论值；最小报价单位量化只会把边界推向保守侧
    assert np.allclose(ratio_up_q, 1.10, atol=0.001)
    assert np.allclose(ratio_up_r, 1.10, atol=0.001)
    assert (ratio_up_q >= 1.10 - 1e-9).all()
    assert (ratio_up_r >= 1.10 - 1e-9).all()

    ratio_down_q = down_q[1:] / np.asarray(steady[:-1])
    ratio_down_r = down_r[1:] / np.asarray(raw[:-1])
    assert np.allclose(ratio_down_q, 0.90, atol=0.001)
    assert np.allclose(ratio_down_r, 0.90, atol=0.001)
    assert (ratio_down_q <= 0.90 + 1e-9).all()
    assert (ratio_down_r <= 0.90 + 1e-9).all()


def test_lock_limit_detection_same_in_both_adjustments() -> None:
    """一字涨停判定：两种口径下「开盘即涨停 ⇒ 买不进」结论一致。"""
    tick = 0.01
    pct = 0.10
    steady = [100.0 + 0.5 * i for i in range(60)]
    raw = _with_ex_dividend_split(steady, at=30, factor=2.0)

    def day_open_equals_limit(close: list[float], idx: int) -> bool:
        prev = close[idx - 1]
        limit_up = np.ceil(prev * (1 + pct) / tick) * tick
        open_price = close[idx]
        return bool(open_price >= limit_up)

    # 构造：第 40 日开盘价等于当日涨停价
    def with_locked_open(close: list[float]) -> list[float]:
        out = list(close)
        prev = out[39]
        out[40] = float(np.ceil(prev * (1 + pct) / tick) * tick)
        return out

    assert day_open_equals_limit(with_locked_open(steady), 40)
    assert day_open_equals_limit(with_locked_open(raw), 40)
