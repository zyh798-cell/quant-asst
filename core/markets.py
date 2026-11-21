"""多市场领域模型：市场枚举、统一 symbol 表示与解析。

所有模块（数据适配器、回测引擎、Agent）共享本文件的定义。
symbol 全局统一为 ``<market>:<code>`` 格式，例如::

    cn:600519         贵州茅台（A股）
    us:AAPL           苹果（美股）
    hk:00700          腾讯控股（港股，中国香港市场）
    futures:RB2510    螺纹钢期货合约
    crypto:BTC/USDT   加密货币交易对
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class Market(str, Enum):
    """受支持的市场。"""

    CN_STOCK = "cn_stock"    # 中国 A 股（沪深京）
    US_STOCK = "us_stock"    # 美股
    HK_STOCK = "hk_stock"    # 港股（中国香港市场）
    FUTURES = "futures"      # 商品/金融期货
    CRYPTO = "crypto"        # 加密货币（7x24 交易）


#: symbol 前缀别名表：用户可用缩写，统一归一到 Market 枚举
_MARKET_ALIASES: dict[str, Market] = {
    "cn": Market.CN_STOCK,
    "a": Market.CN_STOCK,
    "cn_stock": Market.CN_STOCK,
    "us": Market.US_STOCK,
    "us_stock": Market.US_STOCK,
    "hk": Market.HK_STOCK,
    "hk_stock": Market.HK_STOCK,
    "futures": Market.FUTURES,
    "fu": Market.FUTURES,
    "crypto": Market.CRYPTO,
    "cc": Market.CRYPTO,
}


class Symbol(BaseModel):
    """统一 symbol 表示：市场 + 代码。"""

    market: Market
    code: str

    @property
    def full(self) -> str:
        """规范化的 ``<market>:<code>`` 字符串，如 ``cn:600519``。"""
        return f"{self.market.value.split('_')[0]}:{self.code}"

    @classmethod
    def parse(cls, raw: str) -> "Symbol":
        """解析 ``<market>:<code>`` 格式字符串。

        Args:
            raw: 如 ``cn:600519``、``crypto:BTC/USDT``。

        Returns:
            Symbol 实例。

        Raises:
            ValueError: 格式错误或市场前缀不支持。
        """
        if ":" not in raw:
            raise ValueError(
                f"symbol 必须为 <market>:<code> 格式（如 cn:600519），收到：{raw!r}"
            )
        market_raw, code = raw.split(":", 1)
        market_raw = market_raw.strip().lower()
        code = code.strip().upper()  # 交易对习惯大写；A 股数字代码不受影响
        if market_raw not in _MARKET_ALIASES:
            supported = sorted({m.value.split("_")[0] for m in Market})
            raise ValueError(
                f"不支持的市场前缀：{market_raw!r}，支持：{supported}"
            )
        return cls(market=_MARKET_ALIASES[market_raw], code=code)
