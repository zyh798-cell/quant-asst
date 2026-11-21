"""美股日线适配器（AkShare / 新浪源）。

美股无涨跌停机制（limit_up/limit_down 恒 NaN）、无停牌行数据
（缺日按非交易日处理，不补停牌行）、T+0、可做空。
"""

from __future__ import annotations

import pandas as pd

from core.markets import Symbol
from data.adapters.base import MarketDataAdapter


class UsStockAdapter(MarketDataAdapter):
    """美股日线适配器：ak.stock_us_daily（新浪源，不复权）。"""

    def fetch_daily(self, symbol: Symbol, start: str, end: str) -> pd.DataFrame:
        """抓取美股日线并归一为标准 OHLCV schema。"""
        import akshare as ak

        code = symbol.code
        raw = ak.stock_us_daily(symbol=code, adjust="qfq")
        if raw is None or raw.empty:
            raise ValueError(f"美股 {code} 无数据（新浪源接口，检查代码如 AAPL）")

        df = pd.DataFrame({
            "date": pd.to_datetime(raw["date"]),
            "open": raw["open"].astype(float),
            "high": raw["high"].astype(float),
            "low": raw["low"].astype(float),
            "close": raw["close"].astype(float),
            "volume": raw["volume"].astype(float),
            "amount": float("nan"),          # 新浪源无成交额
            "suspended": False,              # 美股不补停牌行
            "limit_up": float("nan"),        # 无涨跌停机制
            "limit_down": float("nan"),
        })
        start_ts = pd.Timestamp(start.replace("-", ""))
        end_ts = pd.Timestamp(end.replace("-", ""))
        df = df[(df["date"] >= start_ts) & (df["date"] <= end_ts)]
        if df.empty:
            raise ValueError(f"美股 {code} 在 {start}-{end} 无数据")
        return self._normalize(df)
