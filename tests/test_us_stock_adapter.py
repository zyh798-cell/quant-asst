"""美股适配器回归测试（data/adapters/us_stock.py）。

背景：akshare 1.20.46 起 ``stock_us_daily`` 更名为 ``stock_us_daily_sina``
（旧名已移除）。本文件锁定：
1. 适配器调用的接口名是新名；
2. 返回列处理兼容新接口（含/不含 qfq_factor、adjust 列两种形态）；
3. 归一后 schema 正确；
4. **价格口径为实际成交价**：适配器不得传 ``adjust`` 做前复权（美股无复权概念，
   与 A 股的 qfq 口径隔离）。

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

    def stock_us_daily_sina(symbol: str, **kwargs: Any) -> pd.DataFrame:
        captured["symbol"] = symbol
        # 记录实际传入的关键字参数，用于断言适配器未做复权
        captured["kwargs"] = dict(kwargs)
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
    # 实际成交价口径：不得传 adjust 做前复权
    assert "adjust" not in captured["kwargs"]
    assert UsStockAdapter.ADJUST == ""
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

    def wide_range(symbol: str, **_kw: Any) -> pd.DataFrame:
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
    mod.stock_us_daily_sina = lambda symbol, **_kw: pd.DataFrame(columns=SAMPLE_COLS_PLAIN)
    monkeypatch.setitem(sys.modules, "akshare", mod)

    with pytest.raises(ValueError, match="无数据"):
        UsStockAdapter().fetch_daily(Symbol.parse("us:ANT"), "2024-01-01", "2024-01-31")


def test_minimum_akshare_version_is_declared() -> None:
    """声明的最低版本应覆盖更名节点，避免旧版安装后运行期 AttributeError。"""
    parts = tuple(int(p) for p in MIN_AKSHARE_VERSION.split("."))
    assert parts >= (1, 20, 46)


def test_interface_name_matches_akshare_contract() -> None:
    """用真实 akshare 的 interface_info 核对解析出的接口签名与输出列。

    背景（CI 修复）：akshare 1.20.64 起 ``stock_us_daily_sina`` 再次更名为
    ``stock_us_hist_sina``，CI 全新安装装到 1.20.65 而本地锁 1.20.63，
    导致原先硬编码接口名的用例只在 CI 失败。现改为校验**解析结果**而非固定名。
    """
    ak = pytest.importorskip("akshare")
    from data.adapters.us_stock import INTERFACE_CANDIDATES, resolve_us_interface

    resolved = resolve_us_interface(ak)
    assert resolved in INTERFACE_CANDIDATES

    info = ak.interface_info(resolved)
    params = {p["name"] for p in info["params"]}
    outputs = {o["name"] for o in info["outputs"]}
    # symbol 必传；接口签名中的 adjust 保留但不使用（实际成交价口径）
    assert "symbol" in params
    assert "adjust" in params
    # 代码按这些列名取值，缺一不可
    assert {"date", "open", "high", "low", "close", "volume"} <= outputs


@pytest.mark.parametrize("usable,expected", [
    # (当前版本真实可用的接口名集合, 期望解析结果)
    ({"stock_us_daily"}, "stock_us_daily"),
    ({"stock_us_hist_sina"}, "stock_us_hist_sina"),
    ({"stock_us_daily_sina"}, "stock_us_daily_sina"),
    # 新旧同时可用时优先新名
    ({"stock_us_hist_sina", "stock_us_daily_sina"}, "stock_us_hist_sina"),
])
def test_resolve_prefers_newest_available(usable, expected) -> None:
    """新名优先、逐级回退；interface_info 拒绝的名字不算可用。"""
    from data.adapters.us_stock import INTERFACE_CANDIDATES, resolve_us_interface

    mod = types.ModuleType("akshare_fake")
    for name in usable:
        setattr(mod, name, lambda **kw: None)

    def interface_info(name: str) -> dict:
        if name not in usable:
            raise RuntimeError(f"{name} 不存在")
        return {"name": name}

    mod.interface_info = interface_info
    assert resolve_us_interface(mod) == expected
    assert expected in INTERFACE_CANDIDATES


def test_resolve_raises_when_no_candidate_usable(monkeypatch) -> None:
    """所有候选均不可用时明确报错（fail-closed，不静默取错数据）。"""
    import pytest as _pytest

    from data.adapters.us_stock import resolve_us_interface

    mod = types.ModuleType("akshare_fake")
    with _pytest.raises(RuntimeError, match="未找到可用的美股日线接口"):
        resolve_us_interface(mod)


def test_fetch_daily_rejects_unexpected_columns(monkeypatch) -> None:
    """接口返回列与预期不符时直接报错，不做静默错位归一。"""
    from data.adapters.us_stock import UsStockAdapter

    captured: dict[str, Any] = {}
    mod = _fake_akshare(captured, SAMPLE_COLS_PLAIN)
    # 抹掉 close 列，模拟接口形态变更
    mod.stock_us_daily_sina = lambda symbol, **_kw: pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", "2024-01-05"),
        "open": [1.0] * 5, "high": [1.0] * 5, "low": [1.0] * 5,
        "volume": [1.0] * 5,
    })
    monkeypatch.setitem(sys.modules, "akshare", mod)

    with pytest.raises(ValueError, match="返回列缺失"):
        UsStockAdapter().fetch_daily(Symbol.parse("us:AAPL"), "2024-01-01", "2024-01-31")
