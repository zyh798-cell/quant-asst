"""美股日线适配器（AkShare / 新浪源）。

美股无涨跌停机制（limit_up/limit_down 恒 NaN）、无停牌行数据
（缺日按非交易日处理，不补停牌行）、T+0、可做空。

接口名历史（akshare 多次更名，此处做兼容解析）：

- ``stock_us_daily``：1.20.46 之前；
- ``stock_us_daily_sina``：1.20.46 ~ 1.20.63（旧名已移除）；
- ``stock_us_hist_sina``：1.20.64 起（新增 ``period`` 参数，参数与返回列可能有调整）。

固定调用任一名字都会在某版本失效（CI 全新安装曾装到 1.20.65，而本地锁
1.20.63，导致只在 CI 失败）。这里改为按 ``interface_info`` 探测可用接口名，
优先新名、逐级回退旧名，全部不可用时明确报错（fail-closed，不静默取错数据）。
"""

from __future__ import annotations

import logging

import pandas as pd

from core.markets import Symbol
from data.adapters.base import MarketDataAdapter

logger = logging.getLogger("quant_asst.data.us_stock")

#: akshare 提供本接口的最低版本（1.20.46 起 ``stock_us_daily`` 更名为 ``stock_us_daily_sina``）
MIN_AKSHARE_VERSION = "1.20.46"

#: 候选接口名（新 -> 旧）。调用时按此顺序探测，取第一个真实可用的。
INTERFACE_CANDIDATES: tuple[str, ...] = (
    "stock_us_hist_sina",      # 1.20.64+
    "stock_us_daily_sina",     # 1.20.46 ~ 1.20.63
    "stock_us_daily",          # < 1.20.46
)

#: 归一所需的原始列（缺一不可，否则说明接口形态与预期不符）
REQUIRED_RAW_COLUMNS: frozenset[str] = frozenset({
    "date", "open", "high", "low", "close", "volume",
})

#: 新版接口的周期参数名（如存在则必须传，否则接口可能返回错误粒度）
_PERIOD_PARAM = "period"


def resolve_us_interface(ak) -> str:
    """探测当前 akshare 版本可用的美股接口名（新名优先，逐级回退）。

    Args:
        ak: 已导入的 akshare 模块。

    Returns:
        可用接口名。

    Raises:
        RuntimeError: 所有候选名均不可用（版本不兼容或接口被移除）。
    """
    info_fn = getattr(ak, "interface_info", None)
    for name in INTERFACE_CANDIDATES:
        if not hasattr(ak, name):
            continue
        if info_fn is None:
            return name
        try:
            info_fn(name)
        except Exception:  # noqa: BLE001 —— 该名在当前版本无效，继续探测下一个
            logger.debug("美股接口 %s 在当前 akshare 版本不可用，继续探测", name)
            continue
        return name
    raise RuntimeError(
        f"当前 akshare 未找到可用的美股日线接口（候选：{', '.join(INTERFACE_CANDIDATES)}）；"
        "请确认 akshare 版本与适配器兼容"
    )


class UsStockAdapter(MarketDataAdapter):
    """美股日线适配器：新浪源，前复权。"""

    def fetch_daily(self, symbol: Symbol, start: str, end: str) -> pd.DataFrame:
        """抓取美股日线并归一为标准 OHLCV schema。"""
        import akshare as ak

        interface = resolve_us_interface(ak)
        code = symbol.code

        params = {"symbol": code, "adjust": "qfq"}
        # 新版接口要求 period 参数（缺省可能返回错误粒度），按签名探测注入
        try:
            sig_params = {
                p["name"] for p in ak.interface_info(interface).get("params", [])
            }
        except Exception:  # noqa: BLE001 —— 元信息不可读时不注入，交由接口自身报错
            sig_params = set()
        if _PERIOD_PARAM in sig_params:
            params[_PERIOD_PARAM] = "daily"

        raw = getattr(ak, interface)(**params)
        if raw is None or raw.empty:
            raise ValueError(f"美股 {code} 无数据（新浪源接口 {interface}，检查代码如 AAPL）")

        missing = REQUIRED_RAW_COLUMNS - set(raw.columns)
        if missing:
            raise ValueError(
                f"美股接口 {interface} 返回列缺失 {sorted(missing)}，"
                f"实际列：{list(raw.columns)}；接口形态变更需同步适配器"
            )

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
        logger.info("美股取数：%s -> %s，%d 行", interface, code, len(df))
        return self._normalize(df)
