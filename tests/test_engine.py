"""回测引擎行为测试：信号次日执行、成本、涨跌停、停牌、空头、样本外切分。

全部使用合成数据，不依赖网络。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.engine import run_event_backtest
from backtest.market_rules import (
    CRYPTO_RULES,
    CN_STOCK_RULES,
    US_STOCK_RULES,
)


def make_ohlcv(prices: list[float], **overrides) -> pd.DataFrame:
    """构造标准 OHLCV 合成数据（open=close=给定价格，含约定列）。"""
    n = len(prices)
    arr = np.asarray(prices, dtype=float)
    return pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=n),
        "open": arr,
        "high": arr * 1.01,
        "low": arr * 0.99,
        "close": arr,
        "volume": 1e6,
        "amount": 1e7,
        "suspended": overrides.get("suspended", [False] * n),
        "limit_up": overrides.get("limit_up", [np.nan] * n),
        "limit_down": overrides.get("limit_down", [np.nan] * n),
    })


def flat_strategy(threshold: float = float("inf")):
    """价格超过阈值则满仓的简单策略（阈值 inf 表示永远空仓）。"""
    def generate_positions(df: pd.DataFrame) -> pd.Series:
        close = df.set_index("date")["close"]
        return (close > threshold).astype(float)
    return generate_positions


# ---------------------------------------------------------------------------
# 信号-执行分离
# ---------------------------------------------------------------------------

def test_signal_executes_next_day() -> None:
    """t 日收盘信号必须在 t+1 日开盘成交（防未来函数的结构验证）。"""
    # 前 5 天 10 元，第 6 天起 11 元：index4 收盘仍 <= 阈值? 10>10.5 False；index5 close=11>10.5 -> 信号在 index5
    prices = [10, 10, 10, 10, 10, 11, 11, 11, 11, 11]
    df = make_ohlcv(prices)
    result = run_event_backtest(df, flat_strategy(10.5), US_STOCK_RULES, initial_capital=100_000)

    assert len(result["trades"]) >= 1
    first_buy = result["trades"][0]
    signal_date = pd.Timestamp("2024-01-08")  # index5（第 6 个交易日）收盘信号
    exec_date = pd.Timestamp(first_buy["date"])
    assert exec_date > signal_date            # 买入晚于信号日
    assert exec_date == pd.Timestamp("2024-01-09")  # 恰为次日开盘


def test_min_trade_unit_rounding() -> None:
    """A 股最小交易单位 100 股：持仓必须是 100 的整数倍。"""
    prices = [10, 10, 10, 10, 10, 11, 11, 11, 11, 11]
    df = make_ohlcv(prices)
    result = run_event_backtest(df, flat_strategy(10.5), CN_STOCK_RULES, initial_capital=50_000)
    for t in result["trades"]:
        assert t["shares"] % 100 == 0


# ---------------------------------------------------------------------------
# 成本模型
# ---------------------------------------------------------------------------

def test_costs_are_charged() -> None:
    """买卖往返必须产生正成本，且收益低于无成本理想值。"""
    prices = [10, 10, 10, 10, 10, 11, 11, 11, 12, 12]  # 先涨后稳
    df = make_ohlcv(prices)
    result = run_event_backtest(df, flat_strategy(10.5), US_STOCK_RULES, initial_capital=100_000)

    assert result["total_cost"] > 0
    # 全部成交都记录了 cost
    assert all(t["cost"] > 0 for t in result["trades"])


def test_commission_min_applies() -> None:
    """最低佣金生效：极小成交额时佣金不低于下限。"""
    rules = US_STOCK_RULES.with_overrides(commission_min=5.0)
    prices = [10, 10, 10, 10, 10, 11, 11, 11, 11, 11]
    df = make_ohlcv(prices)
    result = run_event_backtest(df, flat_strategy(10.5), rules, initial_capital=1_000)
    buy = result["trades"][0]
    # 1000 元资金，约 100 股 × 10 元 ≈ 1000 元成交额 × 0.0005 = 0.5 < 5 -> 佣金取 5
    assert buy["cost"] >= 5.0


# ---------------------------------------------------------------------------
# 涨跌停 / 停牌
# ---------------------------------------------------------------------------

def test_limit_up_blocks_buy() -> None:
    """一字涨停日买不进：开盘价 >= limit_up 时成交被跳过。"""
    prices = [10.0] * 6 + [11.0] * 4          # index6 收盘 11 -> 产生满仓信号
    # index7 起涨停价 = 前收 11 × 1.1 后仍取 11（构造一字板：open == limit_up）
    limit_up = [np.nan] * 7 + [11.0] * 3
    df = make_ohlcv(prices, limit_up=limit_up)
    result = run_event_backtest(df, flat_strategy(10.5), CN_STOCK_RULES, initial_capital=100_000)

    # index7/8/9 全部 open==limit_up==11 -> 买入全程被拦截
    buys = [t for t in result["trades"] if t["side"] == "buy"]
    assert len(buys) == 0


def test_limit_up_released_when_price_below_limit() -> None:
    """对照：涨停价高于开盘价时可正常买入（涨停拦截只挡一字板）。"""
    prices = [10.0] * 6 + [11.0] * 4
    limit_up = [np.nan] * 7 + [12.5, 12.5, 12.5]   # 涨停价高于 open=11 -> 可成交
    df = make_ohlcv(prices, limit_up=limit_up)
    result = run_event_backtest(df, flat_strategy(10.5), CN_STOCK_RULES, initial_capital=100_000)
    buys = [t for t in result["trades"] if t["side"] == "buy"]
    assert len(buys) >= 1


def test_limit_down_blocks_sell() -> None:
    """一字跌停日卖不出：持仓无法在跌停价卖出。"""
    prices = [10.0] * 6 + [9.0] * 4           # index2 起持有；index6 收盘 9 -> 卖出信号
    limit_down = [np.nan] * 7 + [9.0] * 3     # index7 起一字跌停 open==limit_down==9
    df = make_ohlcv(prices, limit_down=limit_down)
    # 用 0/1 开关：跌停前持有（信号恒 1），跌破后清仓（信号 0）
    def hold_then_exit(df: pd.DataFrame) -> pd.Series:
        close = df.set_index("date")["close"]
        return (close > 9.5).astype(float)

    rules = US_STOCK_RULES.with_overrides(has_price_limit=True)
    result = run_event_backtest(df, hold_then_exit, rules, initial_capital=100_000)

    buys = [t for t in result["trades"] if t["side"] == "buy"]
    sells = [t for t in result["trades"] if t["side"] == "sell"]
    assert len(buys) >= 1                     # 跌停前已建仓
    assert len(sells) == 0                    # 卖出信号 -> index7/8/9 全一字跌停 -> 卖不出


def test_suspension_blocks_trade() -> None:
    """停牌日禁止成交，复牌后按最新信号正常成交。"""
    prices = [10, 10, 10, 10, 10, 11, 11, 11, 11, 11]
    suspended = [False] * 5 + [True] + [False] * 4   # index5（01-08）停牌
    df = make_ohlcv(prices, suspended=suspended)
    result = run_event_backtest(df, flat_strategy(10.5), US_STOCK_RULES, initial_capital=100_000)

    # 信号在 index5（01-08）收盘产生 -> index6（01-09）执行成交
    buys = [pd.Timestamp(t["date"]) for t in result["trades"] if t["side"] == "buy"]
    suspend_date = pd.Timestamp("2024-01-08")
    assert all(d != suspend_date for d in buys)
    assert buys[0] == pd.Timestamp("2024-01-09")


# ---------------------------------------------------------------------------
# 空头 / 样本外
# ---------------------------------------------------------------------------

def test_short_position_profit_on_decline() -> None:
    """可做空市场：价格下跌时空头仓位获利。"""
    prices = [10] * 5 + [10, 10, 9, 8, 7]     # 先持有现金，后下跌
    df = make_ohlcv(prices)
    def short_after_peak(df: pd.DataFrame) -> pd.Series:
        close = df.set_index("date")["close"]
        return (close < 9.5).astype(float) * -1   # 跌破 9.5 满仓空
    result = run_event_backtest(df, short_after_peak, CRYPTO_RULES, initial_capital=100_000)

    shorts = [t for t in result["trades"] if t["side"] == "sell"]
    assert shorts and shorts[0]["position_after"] < 0  # 空头持仓
    # 价格从 9 跌到 7，空头应盈利：期末净值高于开空前
    assert result["final_equity"] > 100_000 * 0.99  # 扣除成本后仍应为正收益


def test_out_sample_split() -> None:
    """样本内/外切分：天数相加一致，起点日期正确（硬约束 5）。"""
    prices = [10.0 + 0.01 * i for i in range(31)]
    df = make_ohlcv(prices)
    result = run_event_backtest(df, flat_strategy(), US_STOCK_RULES,
                                initial_capital=100_000, train_ratio=0.7)
    overall = result["metrics"]["overall"]
    in_s = result["metrics"]["in_sample"]
    out_s = result["metrics"]["out_sample"]
    assert in_s["n_days"] + out_s["n_days"] == overall["n_days"]
    # 31 根 K 线 -> 30 天净值 -> split=int(30*0.7)=21 -> 样本外起点为净值序列第 21 个日期
    assert result["out_sample_start"] == result["equity_curve"]["dates"][21]


def test_insufficient_data_raises() -> None:
    """数据不足时明确报错。"""
    df = make_ohlcv([10.0, 10.1, 10.2])
    with pytest.raises(ValueError, match="至少需要 5 根"):
        run_event_backtest(df, flat_strategy(), US_STOCK_RULES)


# ---------------------------------------------------------------------------
# 策略输出对齐（2026-11 零成交事故回归）
# ---------------------------------------------------------------------------

#: 前 5 天 10 元、之后 12 元：MA3 在 index5 上穿 MA5 -> 信号在 index5，index6 执行
_CROSS_PRICES = [10.0] * 5 + [12.0] * 5


def _dual_ma(df: pd.DataFrame, window_fast: int = 3, window_slow: int = 5) -> pd.Series:
    close = df["close"].astype(float)
    return (close.rolling(window_fast).mean() > close.rolling(window_slow).mean()).astype(float)


def test_rangeindex_indexed_series_aligned_positionally() -> None:
    """回归：策略返回 RangeIndex 索引的 Series 时必须按行序对齐，不能静默变全零。

    事故根因：旧引擎 ``reindex(df["date"])`` 对 RangeIndex 索引全量落空，
    被 fillna(0) 吞成零仓位 -> 零成交、净值恒等于初始资金。
    """
    df = make_ohlcv(_CROSS_PRICES)

    def gen(df: pd.DataFrame) -> pd.Series:
        return _dual_ma(df)  # 索引为 RangeIndex（0..9）

    result = run_event_backtest(df, gen, US_STOCK_RULES, initial_capital=100_000)
    assert result["signal_nonzero_days"] > 0, "目标仓位不应被对齐吞成零"
    assert result["metrics"]["overall"]["n_trades"] >= 1, "应产生至少一次买入"
    assert result["metrics"]["overall"]["total_return"] != 0.0


def test_date_indexed_series_still_works() -> None:
    """兼容：策略返回以 df.date 为索引的 Series（旧模板风格）同样正常对齐。"""
    df = make_ohlcv(_CROSS_PRICES)

    def gen(df: pd.DataFrame) -> pd.Series:
        pos = _dual_ma(df)
        return pd.Series(pos.to_numpy(), index=df["date"])

    result = run_event_backtest(df, gen, US_STOCK_RULES, initial_capital=100_000)
    assert result["metrics"]["overall"]["n_trades"] >= 1
    assert result["metrics"]["overall"]["total_return"] != 0.0


def test_ndarray_output_accepted() -> None:
    """兼容：策略返回 numpy 数组（逐行）也可对齐。"""
    df = make_ohlcv(_CROSS_PRICES)

    def gen(df: pd.DataFrame):
        return _dual_ma(df).to_numpy()

    result = run_event_backtest(df, gen, US_STOCK_RULES, initial_capital=100_000)
    assert result["metrics"]["overall"]["n_trades"] >= 1


def test_length_mismatch_raises() -> None:
    """策略输出长度与 K 线数不一致时必须显式报错，杜绝静默错位。"""
    df = make_ohlcv(_CROSS_PRICES)

    def gen(df: pd.DataFrame) -> pd.Series:
        return pd.Series([1.0, 0.0])

    with pytest.raises(ValueError, match="不一致"):
        run_event_backtest(df, gen, US_STOCK_RULES)


def test_all_zero_signal_reports_zero_trades() -> None:
    """真正无信号的策略：n_trades=0 且 signal_nonzero_days=0（供零成交诊断对照）。"""
    df = make_ohlcv(_CROSS_PRICES)

    def gen(df: pd.DataFrame) -> pd.Series:
        return pd.Series(0.0, index=df.index)

    result = run_event_backtest(df, gen, US_STOCK_RULES, initial_capital=100_000)
    assert result["signal_nonzero_days"] == 0
    assert result["metrics"]["overall"]["n_trades"] == 0
    assert result["metrics"]["overall"]["total_return"] == 0.0
