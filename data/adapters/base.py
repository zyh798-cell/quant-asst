"""行情数据适配器抽象基类：定义多市场统一的 OHLCV 输出契约。

标准 Parquet schema（全部适配器必须归一到此格式）::

    date        datetime64[ns]   交易日/自然日（加密货币 7x24 含周末）
    open/high/low/close  float64 复权价（A 股默认前复权 qfq）
    volume      float64          成交量（股/手/张，按市场惯例）
    amount      float64          成交额（无该数据的市场为 NaN）
    suspended   bool             停牌标记（缺失交易日补行；无停牌概念的市场恒 False）
    limit_up    float64          涨停价（无涨跌停机制的市场为 NaN）
    limit_down  float64          跌停价（无涨跌停机制的市场为 NaN）

涨跌停价说明：由前收盘价 × 板块涨跌幅系数推算（A 股主板 10%、创业板/科创板 20%、
北交所 30%、期货默认 8% 近似）。前复权价格下的推算存在近似误差（分红除权日），
精确价以交易所为准 —— 该近似满足研究用途，红队审计时知晓此口径。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

import pandas as pd

from core.markets import Symbol

#: 标准 OHLCV 列顺序（写入 Parquet 的最终形态）
OHLCV_COLUMNS: ClassVar[list[str]] = [
    "date", "open", "high", "low", "close", "volume", "amount",
    "suspended", "limit_up", "limit_down",
]


class MarketDataAdapter(ABC):
    """市场适配器基类：子类实现 fetch_daily，把原始数据归一为标准 schema。"""

    def __init__(self, cache_dir: str | None = None) -> None:
        """cache_dir 预留（缓存统一由 data.cache 层负责，适配器保持无状态）。"""

    @abstractmethod
    def fetch_daily(self, symbol: Symbol, start: str, end: str) -> pd.DataFrame:
        """抓取日线数据并归一为标准 OHLCV schema。

        Args:
            symbol: 统一 symbol（market + code）。
            start: 起始日 YYYYMMDD 或 YYYY-MM-DD（按子类适配源接口）。
            end: 结束日。

        Returns:
            按 date 升序、列齐全的 DataFrame（见模块 docstring 的 schema）。
        """

    # ---- 公共归一工具（子类复用）----

    @staticmethod
    def _normalize(df: pd.DataFrame) -> pd.DataFrame:
        """对适配器产出的 DataFrame 做最终整形：列序、类型、排序。"""
        df = df[OHLCV_COLUMNS].copy()
        df["date"] = pd.to_datetime(df["date"])
        df["suspended"] = df["suspended"].astype(bool)
        return df.sort_values("date").reset_index(drop=True)

    @staticmethod
    def _fill_missing_trading_days(
        df: pd.DataFrame,
        trading_dates: pd.DatetimeIndex,
    ) -> pd.DataFrame:
        """用交易日历补齐缺失日（标记为停牌），价格沿用前值。

        A 股停牌日在行情接口中通常整行缺失；回测引擎需要显式的停牌行
        才能正确禁止成交。补行规则：suspended=True，OHLC 沿用最后有效值，
        volume/amount=0，涨跌停价基于前收继续推算。
        """
        if df.empty:
            return df
        df = df.set_index("date")
        missing = trading_dates.difference(df.index)
        for d in missing:
            last = df.iloc[-1]
            df.loc[d] = {
                "open": last["close"], "high": last["close"], "low": last["close"],
                "close": last["close"], "volume": 0.0, "amount": 0.0,
                "suspended": True, "limit_up": last["limit_up"],
                "limit_down": last["limit_down"],
            }
        return df.sort_index().reset_index().rename(columns={"index": "date"})
