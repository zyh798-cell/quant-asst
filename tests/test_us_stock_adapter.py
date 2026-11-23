"""美股适配器回归测试（data/adapters/us_stock.py）。

背景：akshare 1.20.46 起 ``stock_us_daily`` 更名为 ``stock_us_daily_sina``
（旧名已移除）。本文件锁定：
1. 适配器调用的接口名是新名；
2. 返回列处理兼容新接口（含/不含 qfq_factor、adjust 列两种形态）；
3. 归一后 schema 正确。

不联网：以 monkeypatch 替换 akshare 的函数，注入确定性样本。
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pandas as pd
import pytest

from core.markets import Symbol
from data.adapters.us_stock import MIN_AKSHARE_VERSION, UsStockAdapter

#: 新接口在部分版本会额外返回前复权因子列，部分版本只返回 OHLCV
SAMPLE_COLS_WITH_EXTRA = ["date", "open", "high", "low", "close", "volume", "qfq_factor", "adjust"]
SAMPLE_COLS_PLAIN = ["date", "open", "high", "low", "close", "volume"]


def _fake_akshare(captured: dict[str, Any], columns: list[str]) -> types.ModuleType:
    """构造假的 akshare 模块，记录调用参数并返回样本 DataFrame。"""
    mod = types.ModuleType("akshare")

    def stock_us_daily_sina(symbol: str, adjust: str = "") -> pd.DataFrame:
        captured["symbol"] = symbol
        captured["adjust"] = adjust
        dates = pd.bdate_range("2024-01-01", "2024-01-10")
        n = len(dates)
        data: dict[str, Any] = {
            "date": dates,
            "open": [100.0 + i for i in range(n)],
            "high": [101.0 + i for i in range(n)],
            "low": [99.0 + i for i in range(n)],
            "close": [100.5 + i for i in range(n)],
            "volume": [1_000_000.0 + i for i in range(n)],
        }
        if "qfq_factor" in columns:
            data["qfq_factor"] = [1.0] * n
        if "adjust" in columns:
            data["adjust"] = [1.0] * n
        return pd.DataFrame({c: data[c] for c in columns})

    def interface_info(name: str) -> dict[str, Any]:
        captured.setdefault("interface_queries", []).append(name)
        if name != "stock_us_daily_sina":
            raise AssertionError(f"查询了非目标接口：{name}")
        return {"name": name}

    mod.stock_us_daily_sina = stock_us_daily_sina
    mod.interface_info = interface_info
    return mod


@pytest.mark.parametrize("columns", [SAMPLE_COLS_PLAIN, SAMPLE_COLS_WITH_EXTRA])
def test_fetch_daily_uses_renamed_interface(monkeypatch: pytest.MonkeyPatch, columns: list[str]) -> None:
    """适配器必须调用新接口名，并正确归一返回列。"""
    captured: dict[str, Any] = {}
    monkeypatch.setitem(sys.modules, "akshare", _fake_akshare(captured, columns))

    df = UsStockAdapter().fetch_daily(Symbol.parse("us:AAPL"), "2024-01-01", "2024-01-31")

    assert captured["symbol"] == "AAPL"
    assert captured["adjust"] == "qfq"
    # 标准 schema：列齐全、按日期升序
    assert list(df.columns) == [
        "date", "open", "high", "low", "close", "volume", "amount",
        "suspended", "limit_up", "limit_down",
    ]
    assert df["date"].is_monotonic_increasing
    # 美股无成交额字段、无涨跌停机制
    assert df["amount"].isna().all()
    assert df["limit_up"].isna().all()
    assert df["limit_down"].isna().all()
    assert (~df["suspended"]).all()


def test_fetch_daily_filters_to_requested_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """适配器只保留请求区间内的交易日。"""
    captured: dict[str, Any] = {}

    mod = _fake_akshare(captured, SAMPLE_COLS_PLAIN)

    def wide_range(symbol: str, adjust: str = "") -> pd.DataFrame:
        dates = pd.bdate_range("2023-01-01", "2024-03-31")
        n = len(dates)
        return pd.DataFrame({
            "date": dates,
            "open": [100.0] * n, "high": [101.0] * n, "low": [99.0] * n,
            "close": [100.5] * n, "volume": [1_000_000.0] * n,
        })

    mod.stock_us_daily_sina = wide_range
    monkeypatch.setitem(sys.modules, "akshare", mod)

    df = UsStockAdapter().fetch_daily(Symbol.parse("us:ANT"), "2024-01-01", "2024-01-31")
    assert df["date"].min() >= pd.Timestamp("2024-01-01")
    assert df["date"].max() <= pd.Timestamp("2024-01-31")


def test_fetch_daily_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """接口返回空数据时明确报错，不静默产出空表。"""
    mod = _fake_akshare({}, SAMPLE_COLS_PLAIN)
    mod.stock_us_daily_sina = lambda symbol, adjust="": pd.DataFrame(columns=SAMPLE_COLS_PLAIN)
    monkeypatch.setitem(sys.modules, "akshare", mod)

    with pytest.raises(ValueError, match="无数据"):
        UsStockAdapter().fetch_daily(Symbol.parse("us:ANT"), "2024-01-01", "2024-01-31")


def test_minimum_akshare_version_is_declared() -> None:
    """声明的最低版本应覆盖更名节点，避免旧版安装后运行期 AttributeError。"""
    parts = tuple(int(p) for p in MIN_AKSHARE_VERSION.split("."))
    assert parts >= (1, 20, 46)


def test_interface_name_matches_akshare_contract() -> None:
    """用真实 akshare 的 interface_info 核对签名与输出列（不拉数据，仅读元信息）。"""
    ak = pytest.importorskip("akshare")
    info = ak.interface_info("stock_us_daily_sina")
    params = {p["name"] for p in info["params"]}
    outputs = {o["name"] for o in info["outputs"]}
    assert {"symbol", "adjust"} <= params
    # 代码按这些列名取值，缺一不可
    assert {"date", "open", "high", "low", "close", "volume"} <= outputs
    # 确认适配器不会误用已废弃的旧名
    assert not hasattr(ak, "stock_us_daily") or hasattr(ak, "stock_us_daily_sina")
