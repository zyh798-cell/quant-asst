"""行情缓存层测试：Parquet 写读往返、缓存命中、复权口径隔离、DuckDB 查询。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.markets import Market, Symbol
from data.adapters.base import MarketDataAdapter
from data.cache import _cache_path, get_daily, query_parquet


class FakeAdapter(MarketDataAdapter):
    """假适配器：返回合成数据并计数调用次数（验证缓存命中）。"""

    def __init__(self, adjust: str = "", price: float = 42.0) -> None:
        self.calls = 0
        self.ADJUST = adjust
        self.price = price

    def fetch_daily(self, symbol: Symbol, start: str, end: str) -> pd.DataFrame:
        self.calls += 1
        n = 30
        arr = np.full(n, self.price)
        return pd.DataFrame({
            "date": pd.bdate_range("2024-01-01", periods=n),
            "open": arr, "high": arr, "low": arr, "close": arr,
            "volume": 1e6, "amount": 1e7, "suspended": False,
            "limit_up": np.nan, "limit_down": np.nan,
        })


@pytest.fixture()
def fake_adapter(monkeypatch) -> FakeAdapter:
    adapter = FakeAdapter()
    monkeypatch.setattr(
        "data.cache.get_adapter",
        lambda market, crypto_exchange="binance": adapter,
    )
    return adapter


def test_cache_path_includes_adjust_segment(test_settings) -> None:
    """复权口径写入缓存文件名，避免不同口径混入同一文件。"""
    symbol = Symbol.parse("cn:600519")
    bare = _cache_path(test_settings, symbol, "2024-01-01", "2024-03-01", "")
    qfq = _cache_path(test_settings, symbol, "2024-01-01", "2024-03-01", "qfq")

    assert bare.name == "600519__20240101__20240301.parquet"
    assert qfq.name == "600519__20240101__20240301__qfq.parquet"
    assert bare != qfq


def test_adjust_variants_do_not_share_cache(monkeypatch, test_settings) -> None:
    """同一标的同一区间、不同复权口径各自独立缓存，互不命中。"""
    symbol = Symbol.parse("cn:600519")

    bare = FakeAdapter(adjust="", price=10.0)
    monkeypatch.setattr("data.cache.get_adapter", lambda *a, **k: bare)
    df_bare = get_daily(symbol, "2024-01-01", "2024-03-01", test_settings)
    assert bare.calls == 1
    assert df_bare["close"].iloc[0] == 10.0

    # 换成 qfq 口径后必须重新抓取，不得命中无口径的文件
    qfq = FakeAdapter(adjust="qfq", price=20.0)
    monkeypatch.setattr("data.cache.get_adapter", lambda *a, **k: qfq)
    df_qfq = get_daily(symbol, "2024-01-01", "2024-03-01", test_settings)
    assert qfq.calls == 1
    assert df_qfq["close"].iloc[0] == 20.0

    # 回到无口径时仍命中自己那份缓存（不会被另一个口径覆盖）
    fresh = FakeAdapter(adjust="", price=99.0)
    monkeypatch.setattr("data.cache.get_adapter", lambda *a, **k: fresh)
    again = get_daily(symbol, "2024-01-01", "2024-03-01", test_settings)
    assert fresh.calls == 0
    assert again["close"].iloc[0] == 10.0


def test_legacy_cache_file_is_not_reused(monkeypatch, test_settings) -> None:
    """旧版本遗留的无口径缓存文件不得被复权口径命中（自动失效重建）。"""
    symbol = Symbol.parse("cn:600519")
    legacy = _cache_path(test_settings, symbol, "2024-01-01", "2024-03-01", "")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    stale = pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=3),
        "open": [1.0] * 3, "high": [1.0] * 3, "low": [1.0] * 3, "close": [1.0] * 3,
        "volume": [1.0] * 3, "amount": [1.0] * 3, "suspended": [False] * 3,
        "limit_up": [np.nan] * 3, "limit_down": [np.nan] * 3,
    })
    stale.to_parquet(legacy, index=False)

    qfq = FakeAdapter(adjust="qfq")
    monkeypatch.setattr("data.cache.get_adapter", lambda *a, **k: qfq)
    df = get_daily(symbol, "2024-01-01", "2024-03-01", test_settings)

    assert qfq.calls == 1          # 忽略遗留文件，重新抓取
    assert len(df) == 30
    assert legacy.exists()         # 遗留文件保持原样，由用户自行清理


def test_get_daily_writes_cache(fake_adapter: FakeAdapter, test_settings) -> None:
    symbol = Symbol.parse("cn:600519")
    df = get_daily(symbol, "2024-01-01", "2024-03-01", test_settings)
    assert fake_adapter.calls == 1
    assert len(df) == 30

    # 第二次调用命中缓存：适配器不再被抓取
    df2 = get_daily(symbol, "2024-01-01", "2024-03-01", test_settings)
    assert fake_adapter.calls == 1
    pd.testing.assert_frame_equal(df, df2)


def test_get_daily_force_refresh(fake_adapter: FakeAdapter, test_settings) -> None:
    symbol = Symbol.parse("us:AAPL")
    get_daily(symbol, "2024-01-01", "2024-03-01", test_settings)
    get_daily(symbol, "2024-01-01", "2024-03-01", test_settings, force_refresh=True)
    assert fake_adapter.calls == 2


def test_query_parquet_over_cache(fake_adapter: FakeAdapter, test_settings) -> None:
    symbol = Symbol.parse("cn:000001")
    get_daily(symbol, "2024-01-01", "2024-03-01", test_settings)
    out = query_parquet("SELECT COUNT(*) AS n, MAX(close) AS max_close FROM ohlcv", test_settings)
    assert out.iloc[0]["n"] == 30
    assert out.iloc[0]["max_close"] == 42.0
