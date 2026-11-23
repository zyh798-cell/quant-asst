"""美股日线适配器（AkShare / 新浪源）。

美股无涨跌停机制（limit_up/limit_down 恒 NaN）、无停牌行数据
（缺日按非交易日处理，不补停牌行）、T+0、可做空。

接口名注意：``ak.stock_us_daily`` 自 akshare 1.20.46 起更名为
``ak.stock_us_daily_sina``（旧名已移除），此处固定调用新名；
签名与返回列以 ``ak.interface_info("stock_us_daily_sina")`` 为准。
"""

from __future__ import annotations

import pandas as pd

from core.markets import Symbol
from data.adapters.base import MarketDataAdapter

#: akshare 提供本接口的最低版本（1.20.46 起 ``stock_us_daily`` 更名为 ``stock_us_daily_sina``）
MIN_AKSHARE_VERSION = "1.20.46"


class UsStockAdapter(MarketDataAdapter):
    """美股日线适配器：ak.stock_us_daily_sina（新浪源，前复权）。"""

    def fetch_daily(self, symbol: Symbol, start: str, end: str) -> pd.DataFrame:
        """抓取美股日线并归一为标准 OHLCV schema。"""
        import akshare as ak

        code = symbol.code
        raw = ak.stock_us_daily_sina(symbol=code, adjust="qfq")
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
