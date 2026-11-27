"""A 股日线适配器回归测试（data/adapters/cn_stock.py）。

锁定三条口径：
1. **前复权 qfq**：东财主源与新浪回退源都必须以 ``adjust="qfq"`` 抓取，
   避免除权跳空制造假金叉/死叉；
2. **涨跌停边界保守**：涨停上取整、跌停下取整到最小报价单位，防止舍入误差
   把一字板误判为可成交；
3. **停牌补齐**：交易日历中的缺失日补行并标记 suspended。

不联网：以 monkeypatch 替换 akshare 模块，注入确定性样本。
"""

from __future__ import annotations

import sys
import types
from typing import Any

import numpy as np
import pandas as pd
import pytest

from core.markets import Symbol
from data.adapters.cn_stock import CnStockAdapter, _limit_pct


def _fake_akshare(captured: dict[str, Any], *, empty: bool = False) -> types.ModuleType:
    """构造假的 akshare 模块：记录调用参数，返回含中文列名的东财样本。"""
    mod = types.ModuleType("akshare")

    def stock_zh_a_hist_em(**kwargs: Any) -> pd.DataFrame:
        captured["em_kwargs"] = dict(kwargs)
        if empty:
            return pd.DataFrame(
                columns=["日期", "开盘", "最高", "最低", "收盘", "成交量", "成交额"]
            )
        dates = pd.bdate_range("2024-01-01", "2024-01-10")
        # 故意缺 2024-01-05，模拟停牌日整行缺失
        dates = dates[dates != pd.Timestamp("2024-01-05")]
        n = len(dates)
        base = 100.0 + np.arange(n)
        return pd.DataFrame({
            "日期": dates,
            "开盘": base,
            "最高": base + 1.0,
            "最低": base - 1.0,
            "收盘": base + 0.5,
            "成交量": [1_000_000.0] * n,
            "成交额": [1.0e8] * n,
        })

    def stock_zh_a_daily_sina(**kwargs: Any) -> pd.DataFrame:
        captured["sina_kwargs"] = dict(kwargs)
        dates = pd.bdate_range("2023-12-01", "2024-02-01")
        n = len(dates)
        base = 50.0 + np.arange(n)
        return pd.DataFrame({
            "date": dates,
            "open": base, "high": base + 1.0, "low": base - 1.0,
            "close": base + 0.5, "volume": [1_000_000.0] * n,
            "amount": [1.0e8] * n,
        })

    def calendar_trade_date_hist_sina() -> pd.DataFrame:
        # 覆盖样本区间并故意多给一天（2024-01-11 无行情 → 应补为停牌行）
        return pd.DataFrame({"trade_date": pd.bdate_range("2024-01-01", "2024-01-11")})

    mod.stock_zh_a_hist_em = stock_zh_a_hist_em
    mod.stock_zh_a_daily_sina = stock_zh_a_daily_sina
    mod.calendar_trade_date_hist_sina = calendar_trade_date_hist_sina
    return mod


@pytest.fixture()
def installed(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}
    monkeypatch.setitem(sys.modules, "akshare", _fake_akshare(captured))
    return captured


def test_fetch_daily_requests_forward_adjustment(installed: dict[str, Any]) -> None:
    """东财主源必须以前复权抓取，且 ADJUST 与缓存口径一致。"""
    df = CnStockAdapter().fetch_daily(Symbol.parse("cn:600519"), "2024-01-01", "2024-01-31")

    assert installed["em_kwargs"]["adjust"] == "qfq"
    assert CnStockAdapter.ADJUST == "qfq"
    assert list(df.columns) == [
        "date", "open", "high", "low", "close", "volume", "amount",
        "suspended", "limit_up", "limit_down",
    ]
    assert df["date"].is_monotonic_increasing


def test_sina_fallback_also_uses_qfq(installed: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """限流回退到新浪源时同样保持 qfq 口径。"""

    def boom(**_kw: Any) -> pd.DataFrame:
        raise ConnectionError("push2 rate limited")

    ak = sys.modules["akshare"]
    monkeypatch.setattr(ak, "stock_zh_a_hist_em", boom)

    df = CnStockAdapter().fetch_daily(Symbol.parse("cn:600519"), "2024-01-01", "2024-01-31")

    assert installed["sina_kwargs"]["symbol"] == "sh600519"
    assert installed["sina_kwargs"]["adjust"] == "qfq"
    assert not df.empty


def test_missing_trading_day_is_filled_as_suspended(installed: dict[str, Any]) -> None:
    """交易日历中缺失的交易日补行并标记停牌（价格沿用前值，成交量为 0）。"""
    df = CnStockAdapter().fetch_daily(Symbol.parse("cn:600519"), "2024-01-01", "2024-01-31")

    # 假数据缺 01-05，交易日历应把它补成停牌行
    assert pd.Timestamp("2024-01-05") in set(df["date"])
    assert len(df) == len(pd.bdate_range("2024-01-01", "2024-01-10"))
    row = df[df["date"] == pd.Timestamp("2024-01-05")].iloc[0]
    assert bool(row["suspended"]) is True
    assert row["volume"] == 0.0
    # 停牌日价格沿用前一交易日收盘价
    prev = df[df["date"] == pd.Timestamp("2024-01-04")].iloc[0]
    assert row["close"] == prev["close"]
    assert not df.loc[df["date"] != pd.Timestamp("2024-01-05"), "suspended"].any()


def test_limit_prices_use_conservative_ticks(installed: dict[str, Any]) -> None:
    """涨跌停价按最小报价单位取保守边界：涨停向上、跌停向下。"""
    # 前收 100.5，主板 ±10% → 理论 110.55 / 90.45。
    # 保守方向：涨停价不低于理论值（宁可漏拦不可误放），跌停价不高于理论值；
    # 且偏差不超过一个最小报价单位。
    df = CnStockAdapter().fetch_daily(Symbol.parse("cn:600519"), "2024-01-01", "2024-01-31")
    first = df.iloc[1]
    theoretical_up = 100.5 * 1.10
    theoretical_down = 100.5 * 0.90
    assert first["limit_up"] >= theoretical_up - 1e-9
    assert first["limit_up"] <= theoretical_up + 0.01 + 1e-9
    assert first["limit_down"] <= theoretical_down + 1e-9
    assert first["limit_down"] >= theoretical_down - 0.01 - 1e-9
    # 边界必须落在 0.01 的整数倍上（A 股报价精度）
    for value in (first["limit_up"], first["limit_down"]):
        assert abs(value * 100 - round(value * 100)) < 1e-6


@pytest.mark.parametrize("code,expected", [
    ("600519", 0.10),   # 沪主板
    ("000001", 0.10),   # 深主板
    ("300750", 0.20),   # 创业板
    ("301234", 0.20),   # 创业板
    ("688981", 0.20),   # 科创板
    ("830799", 0.30),   # 北交所
])
def test_limit_pct_by_board(code: str, expected: float) -> None:
    """板块系数映射正确（ST 股的 5% 为已知近似，不在本函数处理）。"""
    assert _limit_pct(code) == expected


def test_first_row_has_no_limit_reference(installed: dict[str, Any]) -> None:
    """首日无前收，涨跌停价应为 NaN。"""
    df = CnStockAdapter().fetch_daily(Symbol.parse("cn:600519"), "2024-01-01", "2024-01-31")
    assert pd.isna(df.iloc[0]["limit_up"])
    assert pd.isna(df.iloc[0]["limit_down"])


def test_empty_result_raises(installed: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """接口返回空数据时明确报错，不静默产出空表。"""
    monkeypatch.setitem(sys.modules, "akshare", _fake_akshare({}, empty=True))

    with pytest.raises(ValueError, match="无数据"):
        CnStockAdapter().fetch_daily(Symbol.parse("cn:600519"), "2024-01-01", "2024-01-31")
