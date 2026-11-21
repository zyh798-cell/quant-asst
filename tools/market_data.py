"""行情数据 MCP 工具：Agent 获取行情的唯一入口（硬约束 1 的数字来源）。

所有财务数字必须从本模块（或回测工具）取得 —— Agent 的 prompt 与上下文
组装只允许注入这里返回的数据，从源头杜绝「自由文本编造数字」。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from core.config import Settings
from core.markets import Symbol
from data.cache import get_daily


def fetch_daily_dict(
    symbol: Symbol,
    start: str,
    end: str,
    settings: Settings,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """抓取日线并返回 JSON 可序列化形式（trajectory / Agent 上下文友好）。

    Returns:
        {"symbol", "market", "rows": [{date, open, high, low, close, volume,
        amount, suspended, limit_up, limit_down}...], "n_rows", "start", "end"}
    """
    df = get_daily(symbol, start, end, settings, force_refresh=force_refresh)
    rows = df.copy()
    rows["date"] = rows["date"].dt.strftime("%Y-%m-%d")
    for col in ("limit_up", "limit_down", "amount"):
        rows[col] = rows[col].where(rows[col].notna(), None)
    return {
        "symbol": symbol.full,
        "market": symbol.market.value,
        "start": start,
        "end": end,
        "n_rows": len(rows),
        "rows": rows.to_dict(orient="records"),
    }


def get_backtest_frame(
    symbol: Symbol,
    start: str,
    end: str,
    settings: Settings,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """取回测用标准 OHLCV DataFrame（缓存优先）。"""
    return get_daily(symbol, start, end, settings, force_refresh=force_refresh)
