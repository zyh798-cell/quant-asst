"""多市场行情适配器路由工厂。

用法::

    from data.adapters import get_adapter

    adapter = get_adapter(Market.CN_STOCK)
    df = adapter.fetch_daily(Symbol.parse("cn:600519"), "2024-01-01", "2024-12-31")
"""

from __future__ import annotations

from core.markets import Market
from data.adapters.base import MarketDataAdapter, OHLCV_COLUMNS
from data.adapters.cn_stock import CnStockAdapter
from data.adapters.crypto import CryptoAdapter
from data.adapters.futures import FuturesAdapter
from data.adapters.hk_stock import HkStockAdapter
from data.adapters.us_stock import UsStockAdapter

__all__ = [
    "OHLCV_COLUMNS",
    "MarketDataAdapter",
    "CnStockAdapter",
    "UsStockAdapter",
    "HkStockAdapter",
    "FuturesAdapter",
    "CryptoAdapter",
    "get_adapter",
]

#: 市场 -> 适配器实例注册表（适配器无状态，可安全复用）
_ADAPTER_REGISTRY: dict[Market, MarketDataAdapter] = {
    Market.CN_STOCK: CnStockAdapter(),
    Market.US_STOCK: UsStockAdapter(),
    Market.HK_STOCK: HkStockAdapter(),
    Market.FUTURES: FuturesAdapter(),
    Market.CRYPTO: CryptoAdapter(),
}


def get_adapter(market: Market, crypto_exchange: str = "binance") -> MarketDataAdapter:
    """按市场取适配器；加密货币可指定交易所 id。"""
    if market == Market.CRYPTO:
        return CryptoAdapter(exchange_id=crypto_exchange)
    return _ADAPTER_REGISTRY[market]
