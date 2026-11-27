"""行情数据适配器抽象基类：定义多市场统一的 OHLCV 输出契约。

标准 Parquet schema（全部适配器必须归一到此格式）::

    date        datetime64[ns]   交易日/自然日（加密货币 7x24 含周末）
    open/high/low/close  float64 复权价（口径由适配器 ADJUST 声明：A 股前复权 qfq，
                                        美股等无复权概念的市场为实际成交价）
    volume      float64          成交量（股/手/张，按市场惯例）
    amount      float64          成交额（无该数据的市场为 NaN）
    suspended   bool             停牌标记（缺失交易日补行；无停牌概念的市场恒 False）
    limit_up    float64          涨停价（无涨跌停机制的市场为 NaN）
    limit_down  float64          跌停价（无涨跌停机制的市场为 NaN）

涨跌停价说明：由前收盘价 × 板块涨跌幅系数推算（A 股主板 10%、创业板/科创板 20%、
北交所 30%、期货默认 8% 近似）。前复权价格下的推算存在近似误差（分红除权日），
精确价以交易所为准 —— 该近似满足研究用途，红队审计时知晓此口径。

缓存隔离：适配器通过 ADJUST 声明复权口径，data.cache 把它写入缓存文件名，
因此不同口径的行情不会互相污染；旧版本缓存文件（不含口径段）不再命中，自动重建。
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

#: 复权口径标识：写入缓存文件名以隔离不同口径（见 data.cache._cache_path）。
#: 空串表示该市场无复权概念（使用实际成交价/原始行情）。
ADJUST_UNADJUSTED = ""
ADJUST_QFQ = "qfq"


class MarketDataAdapter(ABC):
    """市场适配器基类：子类实现 fetch_daily，把原始数据归一为标准 schema。"""

    #: 本市场的复权口径（缓存 key 组成部分）。子类按市场覆盖。
    ADJUST: ClassVar[str] = ADJUST_UNADJUSTED

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
        # 调用方可能在补行之后才推算涨跌停价；此时列尚不存在，需按缺失处理
        has_limits = {"limit_up", "limit_down"} <= set(df.columns)
        df = df.set_index("date").sort_index()
        missing = trading_dates.difference(df.index)
        for d in missing:
            # 只能沿用「该日之前」的最后一个有效交易日：取后续数据会引入前视偏差，
            # 让停牌日价格泄露未来信息。缺失日早于全部数据时回退用最早一行。
            prior = df.loc[df.index < d]
            last = prior.iloc[-1] if not prior.empty else df.iloc[0]
            df.loc[d] = {
                "open": last["close"], "high": last["close"], "low": last["close"],
                "close": last["close"], "volume": 0.0, "amount": 0.0,
                "suspended": True,
                "limit_up": last["limit_up"] if has_limits else float("nan"),
                "limit_down": last["limit_down"] if has_limits else float("nan"),
            }
        return df.sort_index().reset_index().rename(columns={"index": "date"})
