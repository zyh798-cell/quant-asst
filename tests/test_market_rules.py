"""多市场交易规则测试：默认规则、不可变性、关键约束（硬约束 5 相关）。"""

from __future__ import annotations

import dataclasses

import pytest

from backtest.market_rules import (
    DEFAULT_RULES,
    CN_STOCK_RULES,
    MarketRules,
    get_rules,
)
from core.markets import Market


def test_all_markets_have_rules() -> None:
    """五个市场均有默认规则注册。"""
    assert set(DEFAULT_RULES.keys()) == set(Market)


def test_get_rules_accepts_str() -> None:
    """get_rules 同时接受枚举与字符串（str Enum hash 一致）。"""
    assert get_rules("cn_stock") is CN_STOCK_RULES
    assert get_rules(Market.CRYPTO) is get_rules("crypto")
    with pytest.raises(ValueError, match="未知市场"):
        get_rules("jp_stock")


def test_cn_stock_constraints() -> None:
    """A 股必须满足硬约束 5 的核心交易约束：T+1、涨跌停、停牌感知、双边 0.15% 成本。"""
    r = CN_STOCK_RULES
    assert r.t_plus_1 is True
    assert r.has_price_limit is True
    assert r.suspend_aware is True
    assert r.commission_rate == 0.0015   # 用户规格：双边各 0.15% 总口径
    assert r.slippage_rate == 0.001
    assert r.min_trade_unit == 100       # 一手 100 股


def test_futures_leverage() -> None:
    """期货有保证金杠杆且可做空。"""
    r = get_rules(Market.FUTURES)
    assert r.margin_rate < 1.0
    assert r.allow_short is True


def test_crypto_7x24() -> None:
    """加密货币：T+0、无涨跌停、无停牌约束、允许小数仓位。"""
    r = get_rules(Market.CRYPTO)
    assert r.t_plus_1 is False
    assert r.has_price_limit is False
    assert r.suspend_aware is False
    assert r.min_trade_unit == 0.0


def test_rules_are_frozen() -> None:
    """规则对象不可变（防止运行期篡改成本参数）。"""
    with pytest.raises(dataclasses.FrozenInstanceError):
        CN_STOCK_RULES.commission_rate = 0.0  # type: ignore[misc]


def test_market_rules_accepts_override() -> None:
    """with_overrides 可按品种构建自定义规则（如科创板 20% 涨跌停）。"""
    star = CN_STOCK_RULES.with_overrides(default_limit_pct=0.20)
    assert star.default_limit_pct == 0.20
    assert star.t_plus_1 is True  # 其余字段继承默认


def test_dump_load_roundtrip() -> None:
    """dump/load 往返一致，未知键被忽略（沙箱 runner 反序列化路径）。"""
    data = CN_STOCK_RULES.dump()
    assert data["market"] == "cn_stock"
    data["unknown_field"] = 1  # 模拟旧版本字段
    assert MarketRules.load(data) == CN_STOCK_RULES
