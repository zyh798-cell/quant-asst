"""加密货币日线适配器（ccxt，7x24 交易）。

- 交易所默认 binance（可经 QUANT_ASST_CRYPTO_EXCHANGE 配置，如 okx / gate）；
- 7x24 无停牌（suspended 恒 False）、无涨跌停（NaN）、T+0、可做空；
- 日期为 UTC 自然日（对齐加密市场惯例）。
"""

from __future__ import annotations

import pandas as pd

from core.markets import Symbol
from data.adapters.base import MarketDataAdapter

#: 单次请求最大 K 线数（binance 上限 1000，按日频一次拉一年足够）
_MAX_CANDLES_PER_REQ = 1000


class CryptoAdapter(MarketDataAdapter):
    """加密货币日线适配器：ccxt 统一接口。"""

    def __init__(self, exchange_id: str = "binance") -> None:
        """Args:
            exchange_id: ccxt 交易所 id（binance / okx / gate ...）。
        """
        super().__init__()
        self.exchange_id = exchange_id

    def fetch_daily(self, symbol: Symbol, start: str, end: str) -> pd.DataFrame:
        """抓取加密货币日线并归一为标准 OHLCV schema。"""
        import ccxt

        exchange = getattr(ccxt, self.exchange_id)({"enableRateLimit": True})
        if not exchange.markets:
            exchange.load_markets()
        ccxt_symbol = symbol.code  # ccxt 统一格式如 BTC/USDT
        if ccxt_symbol not in exchange.markets:
            raise ValueError(f"{self.exchange_id} 无交易对 {ccxt_symbol}")

        since = int(pd.Timestamp(start.replace("-", ""), tz="UTC").timestamp() * 1000)
        end_ms = int(pd.Timestamp(end.replace("-", ""), tz="UTC").timestamp() * 1000)
        rows: list[list] = []
        while since < end_ms:
            batch = exchange.fetch_ohlcv(ccxt_symbol, timeframe="1d", since=since,
                                         limit=_MAX_CANDLES_PER_REQ)
            if not batch:
                break
            rows.extend(batch)
            since = batch[-1][0] + 86_400_000  # 下一日
            if len(batch) < _MAX_CANDLES_PER_REQ:
                break

        if not rows:
            raise ValueError(f"加密 {ccxt_symbol} 在 {start}-{end} 无数据")

        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_localize(None)
        df["amount"] = float("nan")
        df["suspended"] = False
        df["limit_up"] = float("nan")
        df["limit_down"] = float("nan")
        df = df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))]
        return self._normalize(df)
