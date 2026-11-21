"""期货日线适配器（AkShare / 新浪源）。

- 支持具体合约（futures:RB2510 -> ak.futures_zh_daily_sina）
- 保证金杠杆与做空在回测引擎按 MarketRules 处理（margin_rate / allow_short）
- 涨跌停：各品种幅度不同（螺纹钢约 8% 等），默认统一 8% 近似，
  精确限价以交易所规则为准（研究口径）。
"""

from __future__ import annotations

import pandas as pd

from core.markets import Symbol
from data.adapters.base import MarketDataAdapter


class FuturesAdapter(MarketDataAdapter):
    """期货日线适配器：具体合约用新浪源日线。"""

    #: 默认涨跌停近似幅度（品种差异大，联调后可按品种表覆盖）
    DEFAULT_LIMIT_PCT: float = 0.08

    def fetch_daily(self, symbol: Symbol, start: str, end: str) -> pd.DataFrame:
        """抓取期货合约日线并归一为标准 OHLCV schema。"""
        import akshare as ak

        code = symbol.code.upper()
        raw = ak.futures_zh_daily_sina(symbol=code)
        if raw is None or raw.empty:
            raise ValueError(f"期货 {code} 无数据（新浪源，检查合约代码如 RB2510）")

        df = pd.DataFrame({
            "date": pd.to_datetime(raw["date"]),
            "open": raw["open_price"].astype(float),
            "high": raw["high_price"].astype(float),
            "low": raw["low_price"].astype(float),
            "close": raw["close_price"].astype(float),
            "volume": raw["volume"].astype(float),
            "amount": raw["turnover"].astype(float) if "turnover" in raw else float("nan"),
            "suspended": False,
        })
        start_ts = pd.Timestamp(start.replace("-", ""))
        end_ts = pd.Timestamp(end.replace("-", ""))
        df = df[(df["date"] >= start_ts) & (df["date"] <= end_ts)]
        if df.empty:
            raise ValueError(f"期货 {code} 在 {start}-{end} 无数据")

        # 涨跌停：前收 × 品种近似系数
        prev_close = df["close"].shift(1)
        df["limit_up"] = prev_close * (1 + self.DEFAULT_LIMIT_PCT)
        df["limit_down"] = prev_close * (1 - self.DEFAULT_LIMIT_PCT)
        df.loc[0, ["limit_up", "limit_down"]] = float("nan")
        return self._normalize(df)
