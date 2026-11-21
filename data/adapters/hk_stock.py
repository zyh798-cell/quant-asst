"""港股日线适配器（AkShare / 东财源）。

港股（中国香港市场）：无涨跌停机制（NaN）、T+0、印花税双边各 0.1%
（费率见 backtest/market_rules.HK_STOCK_RULES）。
"""

from __future__ import annotations

import pandas as pd

from core.markets import Symbol
from data.adapters.base import MarketDataAdapter


class HkStockAdapter(MarketDataAdapter):
    """港股日线适配器：ak.stock_hk_hist（东财源，前复权）。"""

    def fetch_daily(self, symbol: Symbol, start: str, end: str) -> pd.DataFrame:
        """抓取港股日线并归一为标准 OHLCV schema。"""
        import akshare as ak

        code = symbol.code.zfill(5)  # 港股代码补足 5 位（700 -> 00700）
        raw = ak.stock_hk_hist(
            symbol=code, period="daily",
            start_date=start.replace("-", ""), end_date=end.replace("-", ""),
            adjust="qfq",
        )
        if raw is None or raw.empty:
            raise ValueError(f"港股 {code} 在 {start}-{end} 无数据")

        df = pd.DataFrame({
            "date": pd.to_datetime(raw["日期"]),
            "open": raw["开盘"].astype(float),
            "high": raw["最高"].astype(float),
            "low": raw["最低"].astype(float),
            "close": raw["收盘"].astype(float),
            "volume": raw["成交量"].astype(float),
            "amount": raw["成交额"].astype(float),
            "suspended": False,           # 港股缺日按休市处理，不补停牌行
            "limit_up": float("nan"),     # 无涨跌停机制
            "limit_down": float("nan"),
        })
        return self._normalize(df)
