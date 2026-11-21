"""多市场交易规则与成本模型（Step 1 定骨架，Step 2 接入回测引擎）。

硬约束 5 在 A 股上的完整落地：滑点、手续费、涨跌停、停牌、T+1、样本外区间。
其他市场按各自真实规则参数化（数字为默认近似值，Step 2 起可按品种覆盖）：

- **A股**：T+1；涨跌停 ±10%（创业板/科创板 ±20% 以数据层 limit_up/down 精确价为准）；
  用户规格成本：双边各 0.15% 总口径 + 0.1% 滑点；停牌期间禁止成交。
- **美股**：T+0；无涨跌停；佣金与 SEC/TAF 费用近似为费率；可做空。
- **港股**（中国香港市场）：T+0；无涨跌停；印花税买卖双方各 0.1%。
- **期货**：T+0；保证金制度（杠杆）；按品种涨跌停；双边手续费。
- **加密货币**：7x24；T+0；无涨跌停；maker/taker 费率近似；无停牌概念。

统一 OHLCV Parquet 约定（数据层产出）：``date/open/high/low/close/volume/amount/
suspended/limit_up/limit_down``，其中 ``limit_up/limit_down`` 为 None 表示该市场
无涨跌停机制，回测引擎按 MarketRules 决定是否启用约束。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from typing import Any

from core.markets import Market


@dataclass(frozen=True)
class MarketRules:
    """单一市场的可回测交易规则（frozen：运行期不可篡改）。

    注意：本模块刻意不依赖 pydantic —— backtest 包需在 Docker 沙箱内
    随引擎一起运行，沙箱镜像只装纯计算依赖（numpy/pandas/pyarrow）。
    """

    market: str = ""                      # Market 枚举值（字符串，兼容 str/枚举两种传参）
    t_plus_1: bool = False                # 买入当日不可卖出
    has_price_limit: bool = False         # 是否存在涨跌停机制
    default_limit_pct: float | None = None  # 默认涨跌停幅度（如 0.10 = ±10%）；精确价以数据层为准
    commission_rate: float = 0.0003       # 单边佣金费率（占成交额）
    commission_min: float = 0.0           # 单笔最低佣金（如 A 股 5 元）
    stamp_duty_buy: float = 0.0           # 买入印花税
    stamp_duty_sell: float = 0.0          # 卖出印花税
    slippage_rate: float = 0.001          # 滑点（占成交价）
    allow_short: bool = False             # 是否允许做空
    margin_rate: float = 1.0              # 保证金比例（期货 < 1 表示杠杆）
    suspend_aware: bool = True            # 停牌期间禁止成交
    min_trade_unit: float = 1.0           # 最小交易单位：A 股 100（股），期货 1（手），加密 0 表示允许小数

    def dump(self) -> dict[str, Any]:
        """序列化为纯字典（JSON 兼容，供 result.json / trajectory 落盘）。"""
        return asdict(self)

    @classmethod
    def load(cls, data: dict[str, Any]) -> "MarketRules":
        """从字典重建规则（沙箱 runner 反序列化用），忽略未知键。"""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def with_overrides(self, **overrides: Any) -> "MarketRules":
        """按品种覆盖个别参数（如科创板涨跌停 20%），返回新实例。"""
        return replace(self, **overrides)


# ---- 各市场默认规则 ----

#: A股 —— 双边各 0.15% 总成本（用户规格）+ 0.1% 滑点；印花税已并入总口径，避免重复计费
CN_STOCK_RULES = MarketRules(
    market=Market.CN_STOCK,
    t_plus_1=True,
    has_price_limit=True,
    default_limit_pct=0.10,
    commission_rate=0.0015,
    commission_min=0.0,
    slippage_rate=0.001,
    min_trade_unit=100,       # 一手 = 100 股
)

#: 美股 —— T+0、无涨跌停、可做空
US_STOCK_RULES = MarketRules(
    market=Market.US_STOCK,
    t_plus_1=False,
    has_price_limit=False,
    commission_rate=0.0005,   # 佣金 + SEC/TAF 近似
    slippage_rate=0.0005,
    allow_short=True,
    suspend_aware=False,
)

#: 港股 —— T+0、无涨跌停、印花税双边各 0.1%
HK_STOCK_RULES = MarketRules(
    market=Market.HK_STOCK,
    t_plus_1=False,
    has_price_limit=False,
    commission_rate=0.0003,
    stamp_duty_buy=0.001,
    stamp_duty_sell=0.001,
    slippage_rate=0.001,
)

#: 期货 —— T+0、保证金杠杆、按品种涨跌停
FUTURES_RULES = MarketRules(
    market=Market.FUTURES,
    t_plus_1=False,
    has_price_limit=True,
    default_limit_pct=0.08,   # 默认近似；实际按品种由数据层 limit_up/down 精确给定
    commission_rate=0.0001,   # 费率近似（实际多为按手固定费用）
    allow_short=True,
    margin_rate=0.10,         # 默认 10% 保证金（约 10 倍杠杆），按品种可覆盖
)

#: 加密货币 —— 7x24、T+0、无涨跌停、taker 费率近似
CRYPTO_RULES = MarketRules(
    market=Market.CRYPTO,
    t_plus_1=False,
    has_price_limit=False,
    commission_rate=0.001,
    slippage_rate=0.0005,
    allow_short=True,
    suspend_aware=False,
    min_trade_unit=0.0,       # 0 = 允许任意小数仓位
)

#: 市场默认规则注册表
DEFAULT_RULES: dict[Market, MarketRules] = {
    Market.CN_STOCK: CN_STOCK_RULES,
    Market.US_STOCK: US_STOCK_RULES,
    Market.HK_STOCK: HK_STOCK_RULES,
    Market.FUTURES: FUTURES_RULES,
    Market.CRYPTO: CRYPTO_RULES,
}


def get_rules(market: Market | str) -> MarketRules:
    """取某市场默认规则（str Enum 的 hash 与其 value 一致，字符串键可直接查询）。"""
    key = market.value if isinstance(market, Market) else market
    if key not in DEFAULT_RULES:
        raise ValueError(f"未知市场：{key!r}，支持：{[m.value for m in DEFAULT_RULES]}")
    return DEFAULT_RULES[key]
