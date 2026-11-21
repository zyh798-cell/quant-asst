"""多市场领域模型测试：symbol 解析、别名归一、非法输入。"""

from __future__ import annotations

import pytest

from core.markets import Market, Symbol


@pytest.mark.parametrize(
    ("raw", "expected_market", "expected_code"),
    [
        ("cn:600519", Market.CN_STOCK, "600519"),
        ("a:000001", Market.CN_STOCK, "000001"),
        ("us:AAPL", Market.US_STOCK, "AAPL"),
        ("hk:00700", Market.HK_STOCK, "00700"),
        ("futures:RB2510", Market.FUTURES, "RB2510"),
        ("crypto:BTC/USDT", Market.CRYPTO, "BTC/USDT"),
        ("CC:eth/usdt", Market.CRYPTO, "ETH/USDT"),  # 别名 + 自动大写
    ],
)
def test_parse_symbol(raw: str, expected_market: Market, expected_code: str) -> None:
    """合法 symbol 解析与别名归一。"""
    s = Symbol.parse(raw)
    assert s.market == expected_market
    assert s.code == expected_code


def test_full_format() -> None:
    """full 属性输出规范化 <market>:<code>。"""
    assert Symbol.parse("cn:600519").full == "cn:600519"
    assert Symbol.parse("us_stock:msft").full == "us:MSFT"


def test_parse_missing_colon_raises() -> None:
    """缺少冒号时明确报错。"""
    with pytest.raises(ValueError, match="<market>:<code>"):
        Symbol.parse("600519")


def test_parse_unknown_market_raises() -> None:
    """不支持的市场前缀明确报错。"""
    with pytest.raises(ValueError, match="不支持的市场前缀"):
        Symbol.parse("jp:7203")
