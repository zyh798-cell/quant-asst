"""行情缓存层测试：Parquet 写读往返、缓存命中、DuckDB 查询。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.markets import Market, Symbol
from data.adapters.base import MarketDataAdapter
from data.cache import get_daily, query_parquet


class FakeAdapter(MarketDataAdapter):
    """假适配器：返回合成数据并计数调用次数（验证缓存命中）。"""

    def __init__(self) -> None:
        self.calls = 0

    def fetch_daily(self, symbol: Symbol, start: str, end: str) -> pd.DataFrame:
        self.calls += 1
        n = 30
        arr = np.full(n, 42.0)
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
